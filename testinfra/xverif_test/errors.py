from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExternalSuiteFailure(Exception):
    suite_id: str
    message: str
    error_layer: str
    returncode: int | None = None
    timed_out: bool = False

    def __str__(self) -> str:
        details = [self.message, f"error_layer={self.error_layer}"]
        if self.returncode is not None:
            details.append(f"returncode={self.returncode}")
        if self.timed_out:
            details.append("timed_out=true")
        return "; ".join(details)
