from fastapi import APIRouter

from app.api.v1 import devices, events, generic, health, live, presets, scenarios, ws

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(presets.router)
api_router.include_router(devices.router)
api_router.include_router(generic.router)
api_router.include_router(scenarios.router)
api_router.include_router(events.router)
api_router.include_router(live.router)

ws_router = APIRouter()
ws_router.include_router(ws.router)