"""Traffic incident control experiment package."""
"""Incident-aware decentralized ADP traffic signal control for SUMO."""

import os
import sys

if "SUMO_HOME" in os.environ:
    sumo_tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    if sumo_tools not in sys.path:
        sys.path.append(sumo_tools)

__all__ = ["config"]
