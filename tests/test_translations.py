"""Consistency checks for translations and manifest (no Home Assistant needed)."""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).parents[1] / "custom_components" / "alcedo_nvr"


def _keys(data: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        out |= _keys(value, path) if isinstance(value, dict) else {path}
    return out


def test_translations_match_strings():
    strings = _keys(json.loads((BASE / "strings.json").read_text(encoding="utf-8")))
    for lang in ("en", "de"):
        data = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        assert _keys(data) == strings, lang


def test_no_html_in_strings():
    for file in [BASE / "strings.json", *(BASE / "translations").glob("*.json")]:
        text = file.read_text(encoding="utf-8")
        assert "<" not in text and ">" not in text, file.name


def test_manifest():
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "alcedo_nvr"
    assert list(manifest)[:2] == ["domain", "name"]
    assert list(manifest)[2:] == sorted(list(manifest)[2:])
    assert (BASE / "brand" / "icon.png").is_file()
