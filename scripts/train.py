from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from its_signal_control.cli import main


if __name__ == "__main__":
    main(["train", "--preset", "configs/training.yaml", "--headless"])
