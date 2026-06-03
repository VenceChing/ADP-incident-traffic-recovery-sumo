from __future__ import annotations

import subprocess
from pathlib import Path


def build_netconvert_command(osm_path: str | Path, output_net_path: str | Path) -> list[str]:
    osm = Path(osm_path)
    output = Path(output_net_path)
    if osm.suffix.lower() not in {".osm", ".xml"}:
        raise ValueError("Expected an OSM XML file.")
    return [
        "netconvert",
        "--osm-files",
        str(osm),
        "-o",
        str(output),
        "--tls.guess",
        "true",
        "--junctions.join",
        "true",
    ]


def ingest_osm(osm_path: str | Path, output_net_path: str | Path) -> Path:
    command = build_netconvert_command(osm_path, output_net_path)
    subprocess.run(command, check=True)
    return Path(output_net_path)
