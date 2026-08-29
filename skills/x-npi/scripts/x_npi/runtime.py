"""Runtime setup helpers for Synopsys Python NPI scripts."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import IO, Iterator, Sequence


def verdi_home(explicit: str | None = None) -> str:
    home = explicit or os.environ.get("VERDI_HOME")
    if not home:
        raise RuntimeError("VERDI_HOME is required for pynpi")
    path = Path(home).expanduser().resolve()
    py_dir = path / "share" / "NPI" / "python"
    if not path.is_dir():
        raise RuntimeError(f"VERDI_HOME does not exist or is not a directory: {path}")
    if not py_dir.is_dir():
        raise RuntimeError(f"pynpi Python directory does not exist: {py_dir}")
    return str(path)


def configure_pynpi(explicit_verdi_home: str | None = None) -> str:
    home = verdi_home(explicit_verdi_home)
    py_dir = str((Path(home) / "share" / "NPI" / "python").resolve())
    if py_dir not in sys.path:
        sys.path.insert(0, py_dir)
    return home


@contextlib.contextmanager
def json_stdout_quarantine() -> Iterator[IO[str]]:
    """Keep native FD1 output away from a single machine-readable JSON stream.

    FD1 deliberately remains redirected to stderr after this context exits.  JSON
    is written through a duplicate of the original FD1, so delayed native-library
    flushes cannot append text to the JSON document.
    """

    saved_fd = os.dup(1)
    os.dup2(2, 1)
    stream = os.fdopen(saved_fd, "w", encoding="utf-8", closefd=True)
    try:
        yield stream
        stream.flush()
    finally:
        stream.close()


@contextlib.contextmanager
def redirect_stdout_to_stderr() -> Iterator[None]:
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        yield
    finally:
        os.dup2(saved, 1)
        os.close(saved)


@contextlib.contextmanager
def pynpi_lifecycle(argv: Sequence[str], load_design: bool = False, verdi_home_path: str | None = None) -> Iterator[object]:
    configure_pynpi(verdi_home_path)
    from pynpi import npisys  # type: ignore

    args = list(argv)
    with redirect_stdout_to_stderr():
        if npisys.init(args) != 1:
            raise RuntimeError("npisys.init failed")
        try:
            if load_design and npisys.load_design(args) != 1:
                raise RuntimeError("npisys.load_design failed")
            yield npisys
        finally:
            npisys.end()
