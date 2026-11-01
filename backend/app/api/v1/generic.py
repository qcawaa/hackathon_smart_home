from fastapi import APIRouter, Depends

from app.api.deps import get_bridge, get_manager, get_storage
from app.api.v1._helpers import scenarios_using_device
from app.core.errors import error
from app.schemas.generic import GenericBody
from app.services.device_manager import DeviceManager
from app.services.storage import Storage
from app.services.ujin_bridge import UjinBridge

router = APIRouter()


@router.get("/generic-devices")
async def generic_devices(manager: DeviceManager = Depends(get_manager)):
    return [row for row in manager.list() if row["model"] == "generic_device"]


@router.post("/generic-devices")
async def create_generic(body: GenericBody, manager: DeviceManager = Depends(get_manager)):
    try:
        return manager.create_generic(body.model_dump())
    except ValueError as exc:
        raise error(400, "INVALID_DEVICE", str(exc))


@router.delete("/generic-devices/{device_id}")
async def delete_generic(device_id: str, manager: DeviceManager = Depends(get_manager),
                         storage: Storage = Depends(get_storage),
                         bridge: UjinBridge = Depends(get_bridge)):
    try:
        affected = scenarios_using_device(device_id, storage)
        if affected:
            titles = "», «".join(row.get("title", "Без названия") for row in affected)
            raise error(409, "DEVICE_IN_USE", f"Устройство используется в сценарии «{titles}». Сначала измените или удалите этот сценарий.")
        manager.remove_generic(device_id)
        await bridge.unbind(device_id)
        return {"ok": True}
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@router.put("/generic-devices/{device_id}")
async def update_generic(device_id: str, body: GenericBody,
                         manager: DeviceManager = Depends(get_manager)):
    try:
        return manager.update_generic(device_id, body.model_dump())
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except ValueError as exc:
        raise error(400, "INVALID_DEVICE", str(exc))