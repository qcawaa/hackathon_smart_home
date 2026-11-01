from fastapi import APIRouter, Depends

from app.api.deps import get_bridge, get_manager
from app.services.device_manager import DeviceManager
from app.services.ujin_bridge import UjinBridge

router = APIRouter()


@router.get("/health")
async def health():
    return {"ok": True, "service": "ujin-smart-lab"}


@router.get("/status")
async def status(manager: DeviceManager = Depends(get_manager),
                 bridge: UjinBridge = Depends(get_bridge)):
    return {"mode": bridge.status()["mode"], "devices": len(manager.devices), "live": bridge.status()}