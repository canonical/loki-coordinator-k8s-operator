from contextlib import contextmanager
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from cosl.coordinated_workers.nginx import NginxConfig

from nginx_config import (
    LOKI_PORT,
    LOKI_TLS_PORT,
    NginxHelper,
)


@contextmanager
def mock_ipv6(enable: bool):
    with patch("cosl.coordinated_workers.nginx.is_ipv6_enabled", MagicMock(return_value=enable)):
        yield


@pytest.fixture(scope="module")
def nginx_config():
    def _nginx_config(tls=False, ipv6=True):
        with mock_ipv6(ipv6):
            with patch.object(NginxHelper, "_tls_available", new=PropertyMock(return_value=tls)):
                nginx_helper = NginxHelper(MagicMock())
                return NginxConfig(server_name="localhost",
                                    upstream_configs=nginx_helper.upstreams(),
                                    server_ports_to_locations=nginx_helper.server_ports_to_locations())
    return _nginx_config


@pytest.mark.parametrize(
    "addresses_by_role",
    [
        ({"read": ["address.one"]}),
        ({"read": ["address.one", "address.two"]}),
        ({"read": ["address.one", "address.two", "address.three"]}),
    ],
)
def test_upstreams_config(nginx_config, addresses_by_role):
    upstreams_config = nginx_config(tls=False).get_config(addresses_by_role, False)
    expected_config = [
        {
            "directive": "upstream",
            "args": ["read"],
            "block": [
                {"directive": "server", "args": [f"{addr}:{LOKI_PORT}"]}
                for addr in addresses_by_role["read"]
            ],
        },
        {
            "directive": "upstream",
            "args": ["worker"],
            "block": [
                {"directive": "server", "args": [f"{addr}:{LOKI_PORT}"]}
                for addr in addresses_by_role["read"]
            ],
        },
    ]
    # TODO assert that the two are the same
    assert upstreams_config is not None
    assert expected_config is not None


@pytest.mark.parametrize("tls", (True, False))
@pytest.mark.parametrize("ipv6", (True, False))
def test_servers_config(ipv6, tls, nginx_config):

    server_config = nginx_config(tls=tls, ipv6=ipv6).get_config(
        addresses_by_role={"read": ["address.one"]}, tls=tls
    )
    ipv4_args = f"{LOKI_TLS_PORT} ssl" if tls else f"{LOKI_PORT}"
    assert f"listen {ipv4_args}" in  server_config
    ipv6_args = f"[::]:{LOKI_TLS_PORT} ssl" if tls else f"[::]:{LOKI_PORT}"
    if ipv6:
        assert f"listen {ipv6_args}" in server_config
    else:
        assert f"listen {ipv6_args}" not in server_config
