from fastapi import APIRouter, Depends

from app.api.deps import get_bridge, get_manager, get_storage
from app.api.v1._helpers import scenarios_using_device
from app.core.errors import error
from app.schemas.device import CommandBody, CreatePresetBody, RenameDeviceBody, SimulateBody
from app.services.device_manager import DeviceManager
from app.services.device_presets import PRESETS
from app.services.storage import Storage
from app.services.ujin_bridge import UjinBridge

router = APIRouter()


@router.post("/devices")
async def create_device(body: CreatePresetBody, manager: DeviceManager = Depends(get_manager)):
    if body.type not in PRESETS:
        raise error(400, "INVALID_DEVICE_TYPE", "Выберите тип устройства из списка")
    try:
        return manager.create_preset(body.type, body.title.strip())
    except ValueError as exc:
        raise error(400, "INVALID_DEVICE", str(exc))


@router.get("/devices")
async def devices(manager: DeviceManager = Depends(get_manager)):
    return manager.list()


@router.get("/devices/{device_id}")
async def device(device_id: str, manager: DeviceManager = Depends(get_manager)):
    try:
        return manager.details(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@router.put("/devices/{device_id}")
async def update_device(device_id: str, body: RenameDeviceBody,
                        manager: DeviceManager = Depends(get_manager)):
    try:
        if device_id in manager.user_devices:
            return manager.update_preset(device_id, body.title.strip())
        if manager.devices.get(device_id) and manager.devices[device_id].model == "generic_device":
            return manager.rename_generic(device_id, body.title.strip())
        raise KeyError(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено или его нельзя редактировать")


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, manager: DeviceManager = Depends(get_manager),
                        storage: Storage = Depends(get_storage),
                        bridge: UjinBridge = Depends(get_bridge)):
    affected = scenarios_using_device(device_id, storage)
    if affected:
        titles = "», «".join(row.get("title", "Без названия") for row in affected)
        raise error(409, "DEVICE_IN_USE", f"Устройство используется в сценарии «{titles}». Сначала измените или удалите этот сценарий.")
    try:
        manager.remove_device(device_id)
        await bridge.unbind(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено или его нельзя удалить")
    return {"ok": True}


@router.get("/devices/{device_id}/state")
async def device_state(device_id: str, manager: DeviceManager = Depends(get_manager)):
    try:
        return manager.get_state(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@router.get("/devices/{device_id}/declaration")
async def device_declaration(device_id: str, manager: DeviceManager = Depends(get_manager)):
    try:
        return manager.get(device_id).declaration()
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@router.post("/devices/{device_id}/command")
async def device_command(device_id: str, body: CommandBody,
                         manager: DeviceManager = Depends(get_manager)):
    try:
        return await manager.command(device_id, body.signal, body.value)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except PermissionError as exc:
        raise error(400, "SIGNAL_READ_ONLY", str(exc))
    except ValueError as exc:
        raise error(400, "INVALID_COMMAND", str(exc))


@router.post("/devices/{device_id}/command/{signal_name}")
async def device_command_signal(device_id: str, signal_name: str, body: CommandBody,
                                manager: DeviceManager = Depends(get_manager)):
    try:
        return await manager.command(device_id, signal_name, body.value)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except PermissionError as exc:
        raise error(400, "SIGNAL_READ_ONLY", str(exc))
    except ValueError as exc:
        raise error(400, "INVALID_COMMAND", str(exc))


@router.post("/devices/{device_id}/simulate")
async def device_simulate(device_id: str, body: SimulateBody,
                          manager: DeviceManager = Depends(get_manager)):
    try:
        return await manager.simulate(device_id, body.signal, body.value)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except ValueError as exc:
        raise error(400, "SIMULATION_NOT_SUPPORTED", str(exc))