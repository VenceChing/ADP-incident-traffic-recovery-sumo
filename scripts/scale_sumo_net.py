from __future__ import annotations

import argparse
import re
from pathlib import Path

NUMBER = r"-?\d+(?:\.\d+)?"
PAIR_RE = re.compile(rf"({NUMBER}),({NUMBER})")
ATTR_RE = re.compile(r'\b(x|y|shape|customShape|netOffset|convBoundary|origBoundary)="([^"]*)"')


def _scale_pair(match: re.Match[str], factor: float) -> str:
    return f"{float(match.group(1)) * factor:.2f},{float(match.group(2)) * factor:.2f}"


def _scale_attr(name: str, value: str, factor: float) -> str:
    if name in {"shape", "customShape", "netOffset"}:
        return PAIR_RE.sub(lambda match: _scale_pair(match, factor), value)
    if name in {"x", "y"}:
        return f"{float(value) * factor:.2f}"
    if name in {"convBoundary", "origBoundary"}:
        return ",".join(f"{float(item) * factor:.2f}" for item in value.split(","))
    return value


def scale_net(path: Path, factor: float) -> None:
    text = path.read_text(encoding="utf-8")
    scaled = ATTR_RE.sub(
        lambda match: f'{match.group(1)}="{_scale_attr(match.group(1), match.group(2), factor)}"',
        text,
    )
    path.write_text(scaled, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scale SUMO network coordinates in-place.")
    parser.add_argument("net", type=Path)
    parser.add_argument("--factor", type=float, required=True)
    args = parser.parse_args()
    scale_net(args.net, args.factor)
    print(f"Scaled {args.net} by factor {args.factor}")


if __name__ == "__main__":
    main()
