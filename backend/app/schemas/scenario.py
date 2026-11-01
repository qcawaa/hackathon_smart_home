from pydantic import BaseModel, Field


class Predicate(BaseModel):
    device_id: str
    signal: str
    operator: str = "=="
    value: object


class Action(BaseModel):
    device_id: str
    signal: str
    value: object


class Scenario(BaseModel):
    id: str | None = None
    title: str = Field(min_length=2, max_length=100)
    enabled: bool = True
    execution_mode: str = "local"
    trigger: Predicate
    conditions: list[Predicate] = []
    actions: list[Action] = Field(min_length=1)
    graph: dict = Field(default_factory=dict)