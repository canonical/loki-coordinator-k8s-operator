import logging
from typing import Any, Dict

import requests
import yaml
from juju.application import Application
from juju.unit import Unit
from minio import Minio
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


def charm_resources(metadata_file="charmcraft.yaml") -> Dict[str, str]:
    with open(metadata_file, "r") as file:
        metadata = yaml.safe_load(file)
    resources = {}
    for res, data in metadata["resources"].items():
        resources[res] = data["upstream-source"]
    return resources


async def configure_minio(ops_test: OpsTest):
    bucket_name = "loki"
    minio_addr = await get_unit_address(ops_test, "minio", 0)
    mc_client = Minio(
        f"{minio_addr}:9000",
        access_key="access",
        secret_key="secretsecret",
        secure=False,
    )
    # create bucket
    found = mc_client.bucket_exists(bucket_name)
    if not found:
        mc_client.make_bucket(bucket_name)


async def configure_s3_integrator(ops_test: OpsTest):
    assert ops_test.model is not None
    bucket_name = "loki"
    config = {
        "access-key": "access",
        "secret-key": "secretsecret",
    }
    s3_integrator_app: Application = ops_test.model.applications["s3"]  # type: ignore
    s3_integrator_leader: Unit = s3_integrator_app.units[0]

    await s3_integrator_app.set_config(
        {
            "endpoint": f"minio-0.minio-endpoints.{ops_test.model.name}.svc.cluster.local:9000",
            "bucket": bucket_name,
        }
    )
    action = await s3_integrator_leader.run_action("sync-s3-credentials", **config)
    action_result = await action.wait()
    assert action_result.status == "completed"


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_no: int):
    assert ops_test.model is not None
    status = await ops_test.model.get_status()
    app = status["applications"][app_name]
    if app is None:
        assert False, f"no app exists with name {app_name}"
    unit = app["units"].get(f"{app_name}/{unit_no}")
    if unit is None:
        assert False, f"no unit exists in app {app_name} with index {unit_no}"
    return unit["address"]


@retry(wait=wait_fixed(10), stop=stop_after_attempt(10))
async def check_data_in_loki(
    ops_test: OpsTest, coordinator_app: str, target_app: str
) -> Dict[str, Any]:
    loki_url = await get_unit_address(ops_test, coordinator_app, 0)
    response = requests.get(f"http://{loki_url}:8080/status")
    assert response.status_code == 200

    response = requests.get(f"http://{loki_url}:8080/loki/api/v1/series")
    assert response.status_code == 200
    assert response.json()["status"] == "success"  # the query was successful

    # {data: [..., ..., {juju_charm: "grafana-agent-k8s"}, ...]}
    loki_series = response.json()["data"]
    assert len([s for s in loki_series if s["juju_application"] == target_app]) > 0