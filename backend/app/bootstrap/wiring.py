from app.core.config import DATA
from app.services.device_manager import DeviceManager
from app.services.event_bus import EventBus
from app.services.scenario_engine import ScenarioEngine
from app.services.storage import Storage
from app.services.ujin_adapter import UjinAdapter
from app.services.ujin_bridge import UjinBridge

storage, bus, ujin = Storage(DATA), EventBus(), UjinAdapter()
manager = DeviceManager(storage, bus)
engine = ScenarioEngine(manager, storage, bus)
bridge = UjinBridge(manager, storage, bus, ujin)