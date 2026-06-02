from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from its_signal_control.scenario_validation import validate_two_lane_network


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the two-lane SUMO network and action groups.")
    parser.add_argument(
        "net_path",
        nargs="?",
        default=str(REPO_ROOT / "scenarios" / "grid_4x4_2lane" / "grid_4x4_2lane.net.xml"),
    )
    args = parser.parse_args()

    issues = validate_two_lane_network(args.net_path)
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print(f"OK: {args.net_path}")


if __name__ == "__main__":
    main()
