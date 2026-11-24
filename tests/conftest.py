import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    # The CLI keeps its downloads and loaded graph in ./data. Run every test
    # from an empty folder so a real load on this machine can't change results.
    monkeypatch.chdir(tmp_path)
