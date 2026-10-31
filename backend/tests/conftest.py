"""Keep tests offline even when the developer has enabled a real Ujin account."""
import pytest


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    for key in ("UJIN_UST", "UJIN_LOGIN", "UJIN_PASSWORD", "UJIN_ACCESS_FILE"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("APP_MODE", "local")
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "boot-data"))
