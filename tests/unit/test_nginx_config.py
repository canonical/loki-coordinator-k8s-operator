import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nginx_config import NginxConfig

sample_dns_ip = "198.18.0.0"


@contextmanager
def mock_ipv6(enable: bool):
    with patch("nginx_config.is_ipv6_enabled", MagicMock(return_value=enable)):
        yield


@pytest.fixture(scope="module")
def nginx_config():
    return NginxConfig()


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
    coord.nginx = MagicMock()
    coord.nginx.are_certificates_on_disk = MagicMock(return_value=True)
    coord.hostname = "localhost"  # crossplane.build does not allow unittest.mock objects
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


@contextmanager
def mock_resolv_conf(contents: str):
    with tempfile.NamedTemporaryFile() as tf:
        Path(tf.name).write_text(contents)
        with patch("nginx_config.RESOLV_CONF_PATH", tf.name):
            yield


@pytest.mark.parametrize(
    "addresses_by_role",
    [
        ({"read": ["address.one"]}),
        ({"read": ["address.one", "address.two"]}),
        ({"read": ["address.one", "address.two", "address.three"]}),
    ],
)
def test_upstreams_config(nginx_config, addresses_by_role):
    nginx_port = 8080
    upstreams_config = nginx_config._upstreams(addresses_by_role, nginx_port)
    expected_config = [
        {
            "directive": "upstream",
            "args": ["read"],
            "block": [
                {"directive": "server", "args": [f"{addr}:{nginx_port}"]}
                for addr in addresses_by_role["read"]
            ],
        },
        {
            "directive": "upstream",
            "args": ["worker"],
            "block": [
                {"directive": "server", "args": [f"{addr}:{nginx_port}"]}
                for addr in addresses_by_role["read"]
            ],
        },
    ]
    # TODO assert that the two are the same
    assert upstreams_config is not None
    assert expected_config is not None


@pytest.mark.parametrize("tls", (True, False))
@pytest.mark.parametrize("ipv6", (True, False))
def test_servers_config(ipv6, tls):
    port = 8080
    with mock_ipv6(ipv6):
        nginx = NginxConfig()
    server_config = nginx._server(
        server_name="test", addresses_by_role={}, nginx_port=port, tls=tls
    )
    ipv4_args = ["443", "ssl"] if tls else [f"{port}"]
    assert {"directive": "listen", "args": ipv4_args} in server_config["block"]
    ipv6_args = ["[::]:443", "ssl"] if tls else [f"[::]:{port}"]
    ipv6_directive = {"directive": "listen", "args": ipv6_args}
    if ipv6:
        assert ipv6_directive in server_config["block"]
    else:
        assert ipv6_directive not in server_config["block"]


def _assert_config_per_role(source_dict, address, prepared_config, tls):
    # as entire config is in a format that's hard to parse (and crossplane returns a string), we look for servers,
    # upstreams and correct proxy/grpc_pass instructions.
    # FIXME we get -> server "1.2.3.5:<MagicMock name=\'mock.nginx.options.__getitem__() ..." since we mock the coordinator
    # FIXME How can we test this? And where do we get our ports from?
    for port in source_dict.values():
        assert f"server {address}:{port};" in prepared_config
        assert f"listen {port}" in prepared_config
        assert f"listen [::]:{port}" in prepared_config
    for protocol in source_dict.keys():
        sanitised_protocol = protocol.replace("_", "-")
        assert f"upstream {sanitised_protocol}" in prepared_config

        if "grpc" in protocol:
            assert f"set $backend grpc{'s' if tls else ''}://{sanitised_protocol}"
            assert "grpc_pass $backend" in prepared_config
        else:
            assert f"set $backend http{'s' if tls else ''}://{sanitised_protocol}"
            assert "proxy_pass $backend" in prepared_config


@pytest.mark.parametrize("tls", (True, False))
def test_nginx_config_contains_upstreams_and_proxy_pass(
    context, nginx_container, coordinator, addresses, tls
):
    coordinator.nginx.are_certificates_on_disk = tls
    with mock_resolv_conf(f"nameserver {sample_dns_ip}"):
        nginx = NginxConfig()

    prepared_config = nginx.config(coordinator)
    assert f"resolver {sample_dns_ip};" in prepared_config

    for role, addresses in addresses.items():
        for address in addresses:
            if role == "distributor":
                _assert_config_per_role({"ssl": 443}, address, prepared_config, tls)
            if role == "query-frontend":
                _assert_config_per_role({"ssl": 443}, address, prepared_config, tls)
