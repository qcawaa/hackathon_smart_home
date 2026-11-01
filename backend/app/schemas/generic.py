from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class GenericSignal(BaseModel):
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

    @field_validator("control")
    @classmethod
    def validate_control(cls, value):
        if value not in ("switch", "range", "number", "counter", "list", "text", "push_time", "graph"):
            raise ValueError("Неизвестный тип сигнала")
        return value

    @field_validator("management")
    @classmethod
    def validate_management(cls, value):
        if value not in ("r", "rw", "w"):
            raise ValueError("Неизвестный режим управления")
        return value


class GenericBody(BaseModel):
    id: str | None = None
    title: str = Field(min_length=2, max_length=80)
    signals: list[GenericSignal] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_signal_names(self):
        names = [signal.name for signal in self.signals]
        if len(names) != len(set(names)):
            raise ValueError("Имена сигналов должны быть уникальными")
        return self