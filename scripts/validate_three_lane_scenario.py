from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from its_signal_control.scenario_validation import validate_three_lane_network


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the three-lane SUMO network and action groups.")
    parser.add_argument(
        "--net",
        default=str(REPO_ROOT / "scenarios" / "grid_4x4_3lane" / "grid_4x4_3lane.net.xml"),
    )
    args = parser.parse_args()
    issues = validate_three_lane_network(Path(args.net))
    if issues:
        print("\n".join(issues))
        raise SystemExit(1)
    print(f"OK: {args.net}")


if __name__ == "__main__":
    main()
