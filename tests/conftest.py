# Every fixture module is loaded for the whole suite, so any test can use any fixture.
pytest_plugins = [
    "tests.fixtures.app",
    "tests.fixtures.auth",
    "tests.fixtures.projects",
    "tests.fixtures.documents",
    "tests.fixtures.sharing",
    "tests.fixtures.internal",
]
