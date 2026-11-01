from __future__ import annotations

from pydantic import BaseModel, Field


class BindingBody(BaseModel):
    # Serial numbers exceed JavaScript's safe integer range. Keep them as strings.
    serialnumber: str = Field(pattern=r"^[0-9]+$", max_length=40)
    ext_guid: str = Field(pattern=r"^[A-Za-z0-9_]+$", max_length=100)
    signal_map: dict[str, str] = Field(default_factory=dict)