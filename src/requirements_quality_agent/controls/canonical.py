"""Canonical JSON and domain-separated SHA-256 helpers."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel


def canonical_text(value: str) -> str:
    """Normalize transport differences without changing meaningful spacing."""

    return unicodedata.normalize("NFC", value.removeprefix("\ufeff").replace("\r\n", "\n"))


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def canonical_json(value: BaseModel | Mapping[str, Any] | Sequence[Any]) -> bytes:
    payload = _json_value(value)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(canonical_text(value).encode("utf-8"))


def domain_digest(domain: str, value: BaseModel | Mapping[str, Any] | Sequence[Any]) -> str:
    prefix = f"requirements-quality-agent/{domain}/v1\0".encode()
    return sha256_bytes(prefix + canonical_json(value))
