import unittest
from unittest.mock import MagicMock, PropertyMock

import pytest
from coordinated_workers.coordinator import Coordinator
from deepdiff import DeepDiff

from src.loki_config import LokiConfig


@pytest.fixture(scope="module")
def loki_config() -> LokiConfig:
    return LokiConfig()


@pytest.fixture(scope="module")
def coordinator():
    coord = MagicMock()
    coord.topology = MagicMock()
    coord.cluster = MagicMock()
    coord.cluster.gather_addresses_by_role = MagicMock(
        return_value={
            "read": ["http://some.loki.worker.0:8080"],
            "write": ["http://some.loki.worker.0:8080"],
            "backend": ["http://some.loki.worker.0:8080", "http://some.loki.worker.1:8080"],
        }
    )
    coord.cluster.gather_addresses = MagicMock(
        return_value=["http://some.loki.worker.0:8080", "http://some.loki.worker.1:8080"]
    )
    coord.s3_ready = MagicMock(return_value=True)
    type(coord)._s3_config = PropertyMock(
        return_value={
            "endpoint": "s3.com:port",
            "access_key_id": "your_access_key",
            "secret_access_key": "your_secret_key",
            "bucket_name": "your_bucket",
            "region": "your_region",
            "insecure": "true",
        }
    )
    coord.nginx = MagicMock()
    coord.nginx.are_certificates_on_disk = MagicMock(return_value=True)
    return coord


@pytest.fixture(scope="module")
def topology():
    top = MagicMock()
    top.as_dict = MagicMock(
        return_value={
            "model": "some-model",
            "model_uuid": "some-uuid",
            "application": "loki",
            "unit": "loki-0",
            "charm_name": "loki-coordinator-k8s",
        }
    )
    return top


def test_build_chunk_store_config(loki_config: LokiConfig):
    chunk_store_config = loki_config._chunk_store_config()
    expected_config = {"chunk_cache_config": {"embedded_cache": {"enabled": True}}}
    assert DeepDiff(chunk_store_config, expected_config) == {}


@pytest.mark.parametrize(
    "addresses_by_role, replication",
    [
        ({"backend": ["address.one"]}, 1),
        ({"backend": ["address.one", "address.two"]}, 1),
        ({"backend": ["address.one", "address.two", "address.three"]}, 3),
    ],
)
def test_build_common_config(loki_config, coordinator, addresses_by_role, replication):
    coordinator.cluster.gather_addresses_by_role.return_value = addresses_by_role
    common_config = loki_config._common_config(coordinator)
    expected_config_http = {
        "path_prefix": "/loki",
        "replication_factor": replication,
        "compactor_grpc_address": coordinator._external_url,
        "storage": {
            "s3": {
                "bucketnames": "your_bucket",
                "endpoint": "s3.com:port",
                "region": "your_region",
                "access_key_id": "your_access_key",
                "secret_access_key": "your_secret_key",
                "insecure": "true",
                "http_config": {
                    "idle_conn_timeout": "90s",
                    "response_header_timeout": "0s",
                    "insecure_skip_verify": False,
                },
                "s3forcepathstyle": True,
            }
        },
    }
    assert common_config == expected_config_http


@pytest.mark.parametrize(
    "retention, expected",
    [
        (0, False),
        (1, True),
        (10, True),
    ],
)
def test_build_compactor_config(loki_config: LokiConfig, retention: int, expected: bool, coordinator: Coordinator):
    compactor_config = loki_config._compactor_config(retention, coordinator)

    # If retention is enabled, we should see the delete_request_store key in the returned dict and its value should be S3 from the Coordinator
    # Else, there should be no delete_request_store in the returned config
    expected_config = {"retention_enabled": expected, "working_directory": "/loki/compactor"}
    if retention > 0:
        expected_config["delete_request_store"] = "aws"
    assert compactor_config == expected_config


def test_build_frontend_config(loki_config: LokiConfig):
    frontend_config = loki_config._frontend_config()
    expected_config = {"max_outstanding_per_tenant": 8192, "compress_responses": True}
    assert frontend_config == expected_config


def test_build_ingester_config(loki_config: LokiConfig):
    ingester_config = loki_config._ingester_config()
    expected_config = {
        "wal": {"dir": "/loki/chunks/wal", "enabled": True, "flush_on_shutdown": True}
    }
    assert ingester_config == expected_config


@pytest.mark.parametrize(
    "rate, burst_size, retention",
    [
        (0, 0, 0),
        (1, 2, 3),
        (10, 20, 30),
    ],
)
def test_build_limits_config(loki_config: LokiConfig, rate: int, burst_size: int, retention: int):
    limits_config = loki_config._limits_config(rate, burst_size, retention)
    expected_config = {
        "ingestion_rate_mb": float(rate),
        "ingestion_burst_size_mb": float(burst_size),
        "per_stream_rate_limit": f"{rate}MB",
        "per_stream_rate_limit_burst": f"{burst_size}MB",
        "split_queries_by_interval": "0",
        "retention_period": f"{retention}d",
    }
    assert limits_config == expected_config


def test_build_memberlist_config(loki_config, topology, coordinator):
    cluster_label = "some-model_some-uuid_loki"
    worker_addresses = coordinator.cluster.gather_addresses()
    memberlist_config = loki_config._memberlist_config(cluster_label, worker_addresses)
    expected_config = {
        "cluster_label": cluster_label,
        "join_members": ["http://some.loki.worker.0:8080", "http://some.loki.worker.1:8080"],
    }
    assert memberlist_config == expected_config


def test_build_querier_config(loki_config: LokiConfig):
    querier_config = loki_config._querier_config()
    expected_config = {"max_concurrent": 20}
    assert querier_config == expected_config


def test_build_query_range_config(loki_config: LokiConfig):
    query_range_config = loki_config._query_range_config()
    expected_config = {
        "parallelise_shardable_queries": False,
        "results_cache": {"cache": {"embedded_cache": {"enabled": True}}},
    }
    assert query_range_config == expected_config


# TODO: add test_build_ruler_config


def test_build_schema_config(loki_config: LokiConfig):
    schema_config = loki_config._schema_config()
    expected_config = {
        "configs": [
            {
                "from": "2024-08-06",
                "object_store": "s3",
                "schema": "v13",
                "store": "tsdb",
                "index": {"period": "24h", "prefix": "index_"},
            }
        ]
    }
    assert schema_config == expected_config


def test_build_storage_config(loki_config: LokiConfig, coordinator):
    storage_config = loki_config._storage_config(coordinator)
    expected_config = {
        "tsdb_shipper": {
            "active_index_directory": "/loki/index",
            "cache_location": "/loki/index_cache",
        },
        "aws": {
            "bucketnames": "your_bucket",
            "endpoint": "s3.com:port",
            "region": "your_region",
            "access_key_id": "your_access_key",
            "secret_access_key": "your_secret_key",
            "insecure": "true",
            "http_config": {
                "idle_conn_timeout": "90s",
                "response_header_timeout": "0s",
                "insecure_skip_verify": False,
            },
            "s3forcepathstyle": True,
        },
    }
    assert storage_config == expected_config


def test_build_server_config(loki_config: LokiConfig, coordinator):
    server_config = loki_config._server_config(coordinator)
    expected_config = {
        "http_listen_address": "0.0.0.0",
        "http_listen_port": 3100,
        "http_tls_config": {
            "cert_file": "/etc/worker/server.cert",
            "key_file": "/etc/worker/private.key",
        },
    }
    assert server_config == expected_config

@pytest.mark.parametrize(
    "reporting_enabled",
    [
        True,
        False
    ],
)
def test_build_analytics_config(loki_config: LokiConfig, reporting_enabled):
    analytics_config = loki_config._analytics_config(reporting_enabled)
    assert analytics_config["reporting_enabled"] == reporting_enabled

if __name__ == "__main__":
    unittest.main()
