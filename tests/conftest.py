# conftest.py
def pytest_addoption(parser):
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run slow tests" "--testrelays",
        action="store_true",
        default=False,
        help="checks all relays",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")
    config.addinivalue_line("markers", "testrelays: checks all relays")
