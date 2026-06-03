from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


STEP_LOG_FIELDS = [
    "run_id",
    "phase",
    "controller",
    "episode",
    "seed",
    "time",
    "agent_id",
    "current_phase",
    "action",
    "reward",
    "total_queue",
    "mean_speed",
]


class StepLogWriter:
    def __init__(self, output_root: str | Path, run_id: str) -> None:
        self.path = Path(output_root) / "runs" / run_id / "step_logs" / "steps.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._needs_header = not self.path.exists() or self.path.stat().st_size == 0

    def append(self, row: dict[str, Any]) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=STEP_LOG_FIELDS)
            if self._needs_header:
                writer.writeheader()
                self._needs_header = False
            writer.writerow({field: row.get(field, "") for field in STEP_LOG_FIELDS})
