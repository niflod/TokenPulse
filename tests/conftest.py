import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import pytest
from config import settings


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """
    Default test environment:
    Keeps gateway_require_auth False for legacy functional tests that simulate
    raw upstream requests without auth headers. Security tests explicitly enable it.
    """
    monkeypatch.setattr(settings, "gateway_require_auth", False)
