import pytest


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False, help="run slow tests")
    parser.addoption(
        "--testrelays", action="store_true", default=False, help="Check if sending a DM over all relays works"
    )
    parser.addoption(
        "--preferred_relays",
        action="store_true",
        default=False,
        help="Check if sending a DM over preferred_relays works",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")
    config.addinivalue_line("markers", "testrelays: checks all relays")
    config.addinivalue_line("markers", "preferred_relays: checks preferred_relays")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--runslow"):
        # Skip tests marked as 'slow' unless --runslow is specified
        skip_slow = pytest.mark.skip(reason="Need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)

    if not config.getoption("--testrelays"):
        # Skip tests marked as 'testrelays' unless --testrelays is specified
        skip_testrelays = pytest.mark.skip(reason="Need --testrelays option to run")
        for item in items:
            if "testrelays" in item.keywords:
                item.add_marker(skip_testrelays)

    if not config.getoption("--preferred_relays"):
        # Skip tests marked as 'preferred_relays' unless --preferred_relays is specified
        skip_testrelays = pytest.mark.skip(reason="Need --preferred_relays option to run")
        for item in items:
            if "preferred_relays" in item.keywords:
                item.add_marker(skip_testrelays)
