from __future__ import annotations

from typing import TypeAlias, cast

JsonDict: TypeAlias = dict[str, object]
JsonList: TypeAlias = list[JsonDict]


def as_json_dict(value: object) -> JsonDict:
    if not isinstance(value, dict):
        raise ValueError("expected_json_object")
    return cast(JsonDict, value)
