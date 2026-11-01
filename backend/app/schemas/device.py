from __future__ import annotations

from pydantic import BaseModel, Field


class CommandBody(BaseModel):
    signal: str = ""
    value: object


class SimulateBody(BaseModel):
    signal: str
    value: object


class CreatePresetBody(BaseModel):
    type: str
    title: str = Field(min_length=2, max_length=80)


class RenameDeviceBody(BaseModel):
    title: str = Field(min_length=2, max_length=80)