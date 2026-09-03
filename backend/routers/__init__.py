"""
routers package
"""

from routers.alerts import router as alerts_router
from routers.export import router as export_router
from routers.gateway import router as gateway_router
from routers.health import router as health_router
from routers.logs import router as logs_router
from routers.metrics import router as metrics_router
from routers.models_router import router as models_router
from routers.providers import router as providers_router
from routers.realtime import router as realtime_router

__all__ = [
    "alerts_router",
    "export_router",
    "gateway_router",
    "health_router",
    "logs_router",
    "metrics_router",
    "models_router",
    "providers_router",
    "realtime_router",
]
