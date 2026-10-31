from pydantic import BaseModel, Field


class SignalDefinition(BaseModel):
    name: str
    title: str
    control: str = "switch"
    management: str = "rw"
    kind: str = "capability"
    value: object = 0
    measure: str = ""
    min: float | None = None
    max: float | None = None
    layout: dict | None = None


class GenericDeviceDefinition(BaseModel):
    id: str | None = None
    title: str = Field(min_length=2, max_length=80)
    signals: list[SignalDefinition] = Field(min_length=1, max_length=30)
