from fastapi import APIRouter, Depends

from app.api.deps import get_engine
from app.services.scenario_engine import ScenarioEngine

router = APIRouter()


@router.get("/events")
async def events(engine: ScenarioEngine = Depends(get_engine)):
    return engine.logs