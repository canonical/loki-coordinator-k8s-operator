# Copyright 2024 Ubuntu
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import os
import unittest

from charm import LokiCoordinatorK8SOperatorCharm
from ops.model import BlockedStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        os.environ["JUJU_VERSION"] = "3.0.3"
        self.harness = Harness(LokiCoordinatorK8SOperatorCharm)
        self.harness.set_can_connect("nginx", True)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()

    def test_simple(self):
        self.harness.evaluate_status()
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)