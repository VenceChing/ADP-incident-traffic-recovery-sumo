from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from its_signal_control.maps import ingest_osm


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert an OSM file into a SUMO network with netconvert.")
    parser.add_argument("osm_path")
    parser.add_argument("output_net_path")
    args = parser.parse_args()
    ingest_osm(args.osm_path, args.output_net_path)


if __name__ == "__main__":
    main()
