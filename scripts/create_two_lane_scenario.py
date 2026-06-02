from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from its_signal_control.actions import LEFT_TURN_DIRS
from its_signal_control.scenario_validation import validate_two_lane_network


def _connection_dirs(source_net: Path) -> dict[tuple[str, str], str]:
    root = ET.parse(source_net).getroot()
    return {
        (connection.get("from", ""), connection.get("to", "")): connection.get("dir", "s")
        for connection in root.findall("connection")
        if not connection.get("from", "").startswith(":")
    }


def _set_edge_lanes(edge_path: Path, output_path: Path) -> None:
    tree = ET.parse(edge_path)
    root = tree.getroot()
    for edge in root.findall("edge"):
        edge.set("numLanes", "2")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def _set_connection_lanes(connection_path: Path, output_path: Path, turn_dirs: dict[tuple[str, str], str]) -> None:
    tree = ET.parse(connection_path)
    root = tree.getroot()
    for connection in root.findall("connection"):
        turn_dir = turn_dirs.get((connection.get("from", ""), connection.get("to", "")), "s")
        lane = "1" if turn_dir in LEFT_TURN_DIRS else "0"
        connection.set("fromLane", lane)
        connection.set("toLane", lane)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def create_two_lane_scenario(source_dir: Path, target_dir: Path) -> None:
    source_net = source_dir / "grid_4x4.net.xml"
    source_route = source_dir / "grid_4x4_rate2500.rou.xml"
    target_net = target_dir / "grid_4x4_2lane.net.xml"

    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="two_lane_plain_") as tmp_name:
        tmp_dir = Path(tmp_name)
        plain_prefix = tmp_dir / "grid"
        subprocess.run(
            [
                "netconvert",
                "-s",
                str(source_net),
                "--plain-output-prefix",
                str(plain_prefix),
                "--no-warnings",
            ],
            check=True,
        )

        edge_path = tmp_dir / "grid.edg.xml"
        node_path = tmp_dir / "grid.nod.xml"
        connection_path = tmp_dir / "grid.con.xml"
        two_lane_edges = tmp_dir / "grid_2lane.edg.xml"
        two_lane_connections = tmp_dir / "grid_2lane.con.xml"

        _set_edge_lanes(edge_path, two_lane_edges)
        _set_connection_lanes(connection_path, two_lane_connections, _connection_dirs(source_net))

        subprocess.run(
            [
                "netconvert",
                "-n",
                str(node_path),
                "-e",
                str(two_lane_edges),
                "-x",
                str(two_lane_connections),
                "-o",
                str(target_net),
                "--tls.guess",
                "true",
                "--junctions.limit-turn-speed",
                "5.50",
                "--no-turnarounds",
                "false",
                "--no-warnings",
            ],
            check=True,
        )

    if source_route.exists():
        shutil.copy2(source_route, target_dir / "grid_4x4_2lane_rate2500.rou.xml")
    if (source_dir / "view.xml").exists():
        shutil.copy2(source_dir / "view.xml", target_dir / "view.xml")
    (target_dir / "sim.sumocfg").write_text(
        "\n".join(
            [
                "<configuration>",
                "    <input>",
                '        <net-file value="grid_4x4_2lane.net.xml"/>',
                '        <route-files value="grid_4x4_2lane_rate2500.rou.xml"/>',
                "    </input>",
                "    <time>",
                '        <begin value="0"/>',
                "    </time>",
                "    <gui_only>",
                '        <gui-settings-file value="view.xml"/>',
                "    </gui_only>",
                "</configuration>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target_dir / ".gitignore").write_text(
        "route_tmp/\ntrips.trips.xml\n*.tmp.xml\n",
        encoding="utf-8",
    )

    issues = validate_two_lane_network(target_net)
    if issues:
        raise RuntimeError("Generated scenario failed validation:\n" + "\n".join(issues[:20]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the two-lane grid_4x4 SUMO scenario.")
    parser.add_argument("--source-dir", default=str(REPO_ROOT / "scenarios" / "grid_4x4"))
    parser.add_argument("--target-dir", default=str(REPO_ROOT / "scenarios" / "grid_4x4_2lane"))
    args = parser.parse_args()
    create_two_lane_scenario(Path(args.source_dir), Path(args.target_dir))


if __name__ == "__main__":
    main()
