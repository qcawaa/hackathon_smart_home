from app.bootstrap import wiring


def get_manager():
    return wiring.manager


def get_storage():
    return wiring.storage


def get_bus():
    return wiring.bus


def get_engine():
    return wiring.engine


def get_bridge():
    return wiring.bridge


def get_ujin():
    return wiring.ujin