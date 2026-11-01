from fastapi import APIRouter

from app.core.errors import error
from app.services.device_presets import get_preset, list_presets

router = APIRouter()


@router.get("/device-presets")
async def device_presets():
    return list_presets()


@router.get("/device-presets/{device_type}")
async def device_preset(device_type: str):
    preset = get_preset(device_type)
    if not preset:
        raise error(404, "PRESET_NOT_FOUND", "Тип устройства не найден")
    return preset