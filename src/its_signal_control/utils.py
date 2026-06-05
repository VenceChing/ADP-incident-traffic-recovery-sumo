import os
import shutil
import sys
import subprocess
import time
import xml.etree.ElementTree as ET
import uuid
from typing import Union

from .config import NETWORK_FILE, ROUTE_HORIZON_TOLERANCE

ROUTE_TMP_DIR = "route_tmp"


def _console_safe(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def cleanup_route_temp_files(route_file: str | None = None) -> None:
    os.makedirs(ROUTE_TMP_DIR, exist_ok=True)
    candidates = []
    if route_file:
        route_name = os.path.basename(route_file)
        route_root, route_ext = os.path.splitext(route_name)
        candidates.extend(
            os.path.join(".", name)
            for name in os.listdir(".")
            if name.startswith(f"{route_root}.") and name.endswith(f".tmp{route_ext}")
        )
    candidates.extend(os.path.join(ROUTE_TMP_DIR, name) for name in os.listdir(ROUTE_TMP_DIR))

    for path in candidates:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except PermissionError:
            pass


def get_route_horizon(route_file: str) -> float | None:
    if not os.path.exists(route_file):
        return None

    max_depart: float | None = None
    for _, element in ET.iterparse(route_file, events=("end",)):
        if element.tag == "vehicle":
            depart = element.get("depart")
            try:
                depart_time = float(depart) if depart is not None else None
            except ValueError:
                depart_time = None
            if depart_time is not None:
                max_depart = depart_time if max_depart is None else max(max_depart, depart_time)
        element.clear()
    return max_depart


def route_file_covers_time(route_file: str, generate_time: float) -> bool:
    horizon = get_route_horizon(route_file)
    if horizon is None:
        return False
    return horizon + ROUTE_HORIZON_TOLERANCE >= generate_time


def route_file_matches_network(route_file: str, network_file: str) -> bool:
    """Return whether every edge referenced by a route exists in the network."""
    if not os.path.exists(route_file) or not os.path.exists(network_file):
        return False

    network_edges: set[str] = set()
    try:
        for _, element in ET.iterparse(network_file, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] == "edge":
                edge_id = element.get("id")
                if edge_id and not edge_id.startswith(":") and element.get("function") != "internal":
                    network_edges.add(edge_id)
            element.clear()

        found_route = False
        for _, element in ET.iterparse(route_file, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] == "route":
                edges = element.get("edges")
                if edges:
                    found_route = True
                    if any(edge_id not in network_edges for edge_id in edges.split()):
                        return False
            element.clear()
    except ET.ParseError:
        return False

    return found_route


def generate_routes(insertion_rate: Union[int, float], generate_time: int, route_file: str) -> str:
    """Generate routes using SUMO's randomTrips.py utility."""
    if "SUMO_HOME" not in os.environ:
        raise EnvironmentError("SUMO_HOME is not set.")

    python_exe = sys.executable
    random_trips_path = os.path.join(os.environ["SUMO_HOME"], "tools", "randomTrips.py")
    cleanup_route_temp_files(route_file)
    os.makedirs(ROUTE_TMP_DIR, exist_ok=True)
    route_root, route_ext = os.path.splitext(route_file)
    output_route_file = os.path.join(
        ROUTE_TMP_DIR,
        f"{os.path.basename(route_root)}.{uuid.uuid4().hex}.tmp{route_ext}",
    )

    cmd = [
        python_exe,
        random_trips_path,
        "-n",
        NETWORK_FILE,
        "-e",
        str(generate_time),
        "-r",
        output_route_file,
        "--fringe-factor",
        "max",
        "--insertion-rate",
        str(insertion_rate),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        if not os.path.exists(output_route_file) or os.path.getsize(output_route_file) == 0:
            if exc.stderr:
                print(_console_safe(exc.stderr))
            raise
        detail = (
            _console_safe(exc.stderr.strip().splitlines()[-1])
            if exc.stderr
            else "unknown post-write error"
        )
        print(
            "WARNING: randomTrips.py failed after writing the route file; "
            f"using generated routes from {output_route_file}. Detail: {detail}"
        )
    for attempt in range(10):
        try:
            os.replace(output_route_file, route_file)
            return route_file
        except PermissionError:
            if attempt < 9:
                time.sleep(0.05)
    try:
        shutil.copyfile(output_route_file, route_file)
        return route_file
    except PermissionError:
        pass
    print(
        f"WARNING: Could not replace locked route file {route_file}; "
        f"using {output_route_file} for this run."
    )
    return output_route_file
