import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from config import settings
from security import auth_rate_limiter, gateway_rate_limiter


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """
    Default test environment:
    Keeps gateway_require_auth False for legacy functional tests that simulate
    raw upstream requests without auth headers. Security tests explicitly enable it.
    Clears in-memory rate limiters between tests.
    """
    monkeypatch.setattr(settings, "gateway_require_auth", False)
    auth_rate_limiter.reset()
    gateway_rate_limiter.reset()
