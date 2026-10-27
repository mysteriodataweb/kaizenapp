from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_LANG_RE = re.compile(r"^[a-z]{2,3}$")


def _country(v: str) -> str:
    v = v.strip().upper()
    if not _COUNTRY_RE.match(v):
        raise ValueError("Code pays ISO 3166-1 alpha-2 attendu (ex. FR, SN, DE).")
    return v


def _lang(v: str) -> str:
    v = v.strip().lower()
    if not _LANG_RE.match(v):
        raise ValueError("Code langue ISO 639-1 attendu (ex. fr, en).")
    return v


def _clean_tags(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for raw in values:
        item = " ".join(raw.split())
        if item and item.lower() not in seen:
            seen[item.lower()] = item
    return list(seen.values())


CountryCode = Annotated[str, AfterValidator(_country)]
LanguageCode = Annotated[str, AfterValidator(_lang)]
TagList = Annotated[list[Annotated[str, Field(max_length=120)]], Field(max_length=100), AfterValidator(_clean_tags)]
ShortText = Annotated[str, Field(max_length=300)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))


class Message(BaseModel):
    message: str
