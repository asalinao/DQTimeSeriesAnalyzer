from fastapi import APIRouter

from app.api import anomalies, auth, connections, dashboard, health, monitors, series

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(connections.router, prefix="/connections", tags=["connections"])
api_router.include_router(monitors.router, prefix="/monitors", tags=["monitors"])
api_router.include_router(series.router, tags=["series"])
api_router.include_router(anomalies.router, prefix="/anomalies", tags=["anomalies"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
