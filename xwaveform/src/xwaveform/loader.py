from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SignalData:
    signal: str
    time_tick: np.ndarray
    value_words: np.ndarray
    known_words: np.ndarray
    width: int
    word_count: int
    row_count: int


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["_manifest_path"] = str(manifest_path)
    manifest["_base_dir"] = str(manifest_path.parent)
    return manifest


def _signal_entry(manifest: dict[str, Any], signal_or_index: str | int) -> dict[str, Any]:
    signals = manifest.get("signals") or []
    if isinstance(signal_or_index, int):
        return signals[signal_or_index]
    for item in signals:
        if item.get("signal") == signal_or_index:
            return item
    raise KeyError(f"signal not found in manifest: {signal_or_index}")


def load_signal(manifest: dict[str, Any], signal_or_index: str | int) -> SignalData:
    entry = _signal_entry(manifest, signal_or_index)
    fmt = str(manifest.get("format", ""))
    if fmt != "u64bin.v1":
        raise ValueError(f"fast loader requires u64bin.v1, got {fmt}")
    base = Path(manifest.get("_base_dir") or Path(manifest["_manifest_path"]).parent)
    path = base / entry["file"]
    row_count = int(entry.get("row_count", 0))
    word_count = int(entry.get("word_count", 1))
    columns = 1 + word_count * 2
    raw = np.memmap(path, dtype="<u8", mode="r", shape=(row_count, columns))
    time_tick = raw[:, 0]
    value_words = raw[:, 1:1 + word_count]
    known_words = raw[:, 1 + word_count:1 + word_count * 2]
    return SignalData(
        signal=str(entry.get("signal", "")),
        time_tick=time_tick,
        value_words=value_words,
        known_words=known_words,
        width=int(entry.get("width", word_count * 64)),
        word_count=word_count,
        row_count=row_count,
    )
