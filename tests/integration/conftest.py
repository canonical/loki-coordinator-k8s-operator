#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Union

import pytest
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)
store = defaultdict(str)


@pytest.fixture(scope="session")
def cos_channel():
    return "2/edge"


def timed_memoizer(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        fname = func.__qualname__
        logger.info("Started: %s" % fname)
        start_time = datetime.now()
        if fname in store.keys():
            ret = store[fname]
        else:
            logger.info("Return for {} not cached".format(fname))
            ret = await func(*args, **kwargs)
            store[fname] = ret
        logger.info("Finished: {} in: {} seconds".format(fname, datetime.now() - start_time))
        return ret

    return wrapper


@pytest.fixture(scope="module")
@timed_memoizer
async def loki_charm(ops_test: OpsTest) -> Union[str, Path]:
    """Loki charm used for integration testing."""
    # Use the specified charm if set (used for testing the worker)
    if charm_file := os.environ.get("CHARM_PATH"):
        return Path(charm_file)

    charm = await ops_test.build_charm(".", verbosity="verbose")
    assert charm
    return str(charm)
