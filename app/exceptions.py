from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    status_code: int
    detail: str

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.status_code}: {self.detail}"
