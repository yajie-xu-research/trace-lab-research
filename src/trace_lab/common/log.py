"""Run log writer.

Each run writes a plain-text log of the steps taken, counts, and any
rejections. Log lines carry logical (not wall-clock) timestamps so historical
runs are reproducible artifacts.
"""

from __future__ import annotations

from pathlib import Path


class RunLog:
    def __init__(self, path: str | Path, logical_utc: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.logical_utc = logical_utc
        self._lines: list[str] = []
        self._lines.append(f"[{self.logical_utc}] run started")

    def info(self, message: str) -> None:
        self._lines.append(f"[{self.logical_utc}] {message}")

    def warn(self, message: str) -> None:
        self._lines.append(f"[{self.logical_utc}] WARN {message}")

    def close(self) -> None:
        self._lines.append(f"[{self.logical_utc}] run finished")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self._lines) + "\n")
