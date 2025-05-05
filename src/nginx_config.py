# Copyright 2023 Canonical
# See LICENSE file for licensing details.
"""Nginx workload."""

import logging
from typing import Dict, List

from cosl.coordinated_workers.nginx import (
    CA_CERT_PATH,
    CERT_PATH,
    KEY_PATH,
    NginxLocationConfig,
    NginxLocationModifier,
    NginxUpstream,
)
from ops import Container

from loki_config import ROLES

logger = logging.getLogger(__name__)

LOKI_PORT = 3100
NGINX_PORT = 8080
NGINX_TLS_PORT = 443

LOCATIONS_WRITE: List[NginxLocationConfig] = [
    NginxLocationConfig(path="/loki/api/v1/push", backend="write",modifier= NginxLocationModifier(NginxLocationModifier("="))),
]

LOCATIONS_BACKEND: List[NginxLocationConfig] = [
    NginxLocationConfig(path="/loki/api/v1/rules", backend="backend",modifier=NginxLocationModifier("=")),
    NginxLocationConfig(path="/prometheus", backend="backend",modifier=NginxLocationModifier("=")),
    NginxLocationConfig(path="/api/v1/rules", backend="backend", backend_url="/loki/api/v1/rules",modifier=NginxLocationModifier("=")),
]
LOCATIONS_READ: List[NginxLocationConfig] = [
    NginxLocationConfig(path="/loki/api/v1/tail", backend="read", modifier=NginxLocationModifier("=")),
    NginxLocationConfig(path="/loki/api/.*", backend="read", modifier=NginxLocationModifier("~"),headers={"Upgrade": "$http_upgrade", "Connection": "upgrade"})
]
# Locations shared by all the workers, regardless of the role
LOCATIONS_WORKER: List[NginxLocationConfig] = [
    NginxLocationConfig(path="/loki/api/v1/format_query", backend="worker",modifier=NginxLocationModifier("=")),
    NginxLocationConfig(path="/loki/api/v1/status/buildinfo", backend="worker",modifier=NginxLocationModifier("=")),
    NginxLocationConfig(path="/ring", backend="worker",modifier=NginxLocationModifier("=")),
]

class NginxHelper:
    """Helper class to manage the nginx workload."""
    def __init__(
        self,
        container: Container,
    ):
        self._container = container

    def upstreams(self) -> List[NginxUpstream]:
        """Generate the list of Nginx upstream metadata configurations."""
        upstreams = []
        for role in [*ROLES, "worker"]:
            upstreams.append(NginxUpstream(role, LOKI_PORT, role))
        return upstreams

    def server_ports_to_locations(self) -> Dict[int, List[NginxLocationConfig]]:
        """Generate a mapping from server ports to a list of Nginx location configurations."""
        return {
            NGINX_TLS_PORT if self._tls_available else NGINX_PORT: LOCATIONS_WRITE + LOCATIONS_BACKEND + LOCATIONS_READ + LOCATIONS_WORKER
        }

    @property
    def _tls_available(self) -> bool:
        return (
                self._container.can_connect()
                and self._container.exists(CERT_PATH)
                and self._container.exists(KEY_PATH)
                and self._container.exists(CA_CERT_PATH)
            )




