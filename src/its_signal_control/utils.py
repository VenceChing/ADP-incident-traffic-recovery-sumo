import os
import sys
import subprocess
import uuid
from typing import Union

from .config import NETWORK_FILE

ROUTE_TMP_DIR = "route_tmp"


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
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        if not os.path.exists(output_route_file) or os.path.getsize(output_route_file) == 0:
            if exc.stderr:
                print(exc.stderr)
            raise
        detail = exc.stderr.strip().splitlines()[-1] if exc.stderr else "unknown post-write error"
        print(
            "WARNING: randomTrips.py failed after writing the route file; "
            f"using generated routes from {output_route_file}. Detail: {detail}"
        )
    try:
        os.replace(output_route_file, route_file)
        return route_file
    except PermissionError:
        print(
            f"WARNING: Could not replace locked route file {route_file}; "
            f"using {output_route_file} for this run."
        )
        return output_route_file
