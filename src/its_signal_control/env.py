import os
import sys
from typing import Dict, List, Any, Optional

if "SUMO_HOME" in os.environ:
    tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    if tools not in sys.path:
        sys.path.append(tools)
else:
    raise EnvironmentError("SUMO_HOME is not set.")

import traci

from .config import (
    INCIDENT_BLOCK_TRAVEL_TIME,
    INCIDENT_CLOSE_LANES_AFTER_SPAWN,
    INCIDENT_REROUTE_EPSILON,
    REROUTING_PERIOD,
    REROUTING_PROBABILITY,
    SIM_END_TIME,
    SUMO_CONFIG,
)


class SumoEnv:
    def __init__(self, use_gui: bool, step_length: float) -> None:
        self.use_gui = use_gui
        self.step_length = step_length
        self.incident_triggered = False
        self._incident_edges: set[str] = set()
        self._incident_lanes_closed = False
        self._last_incident_reroute_time: float | None = None
        self._stress_alpha = {}

    def start_simulation(self, end_time: Optional[float] = None) -> None:
        sumo_binary = "sumo-gui" if self.use_gui else "sumo"
        sumo_cmd = [
            sumo_binary,
            "-c",
            SUMO_CONFIG,
            "--step-length", str(self.step_length),
            "--device.rerouting.probability", str(REROUTING_PROBABILITY),
            "--device.rerouting.period", str(REROUTING_PERIOD),
            "--time-to-teleport", "-1",
            "--ignore-route-errors",
            "--no-warnings",
        ]
        if end_time is not None:
            sumo_cmd.extend(["--end", str(end_time)])
        traci.start(sumo_cmd)

    def trigger_incident(self, edge_ids: List[str], current_time: float, start_time: float) -> None:
        if self.incident_triggered:
            if INCIDENT_CLOSE_LANES_AFTER_SPAWN and not self._incident_lanes_closed:
                self._close_incident_lanes()
                self._reroute_vehicles_away_from_incident(current_time, force=True)
                return
            self._reroute_vehicles_away_from_incident(current_time)
            return
        if current_time < start_time:
            return

        self._incident_edges = set(edge_ids)

        for vehicle_id in traci.vehicle.getIDList():
            vtype_id = traci.vehicle.getTypeID(vehicle_id)
            default_color = traci.vehicletype.getColor(vtype_id)
            traci.vehicle.setColor(vehicle_id, default_color)

        for edge_id in edge_ids:
            route_id = f"route_{edge_id}"
            if route_id not in traci.route.getIDList():
                traci.route.add(route_id, [edge_id])
            lane_count = max(1, traci.edge.getLaneNumber(edge_id))
            for lane_index in range(lane_count):
                veh_id = f"accident_{edge_id}" if lane_count == 1 else f"accident_{edge_id}_{lane_index}"
                try:
                    traci.vehicle.add(
                        vehID=veh_id,
                        routeID=route_id,
                        departPos="10",
                        departLane=str(lane_index),
                        departSpeed="0",
                    )
                except traci.TraCIException:
                    continue

                traci.vehicle.setSpeedMode(veh_id, 0)
                traci.vehicle.setSpeed(veh_id, 0)
                traci.vehicle.setParameter(veh_id, "timeToTeleport", "-1")
                try:
                    traci.vehicle.setStop(
                        veh_id,
                        edge_id,
                        pos=10,
                        laneIndex=lane_index,
                        duration=1.0e9,
                    )
                except traci.TraCIException:
                    pass
                traci.vehicle.setColor(veh_id, (255, 0, 0, 255))

        self._close_incident_edges(current_time)
        self._reroute_vehicles_away_from_incident(current_time, force=True)
        self.incident_triggered = True

    def _close_incident_edges(self, current_time: float) -> None:
        end_time = SIM_END_TIME if SIM_END_TIME is not None else current_time + 1.0e9
        for edge_id in self._incident_edges:
            try:
                traci.edge.adaptTraveltime(
                    edge_id,
                    INCIDENT_BLOCK_TRAVEL_TIME,
                    current_time,
                    end_time,
                )
            except traci.TraCIException:
                pass

    def _close_incident_lanes(self) -> None:
        for edge_id in self._incident_edges:
            lane_count = max(1, traci.edge.getLaneNumber(edge_id))
            for lane_index in range(lane_count):
                lane_id = f"{edge_id}_{lane_index}"
                try:
                    traci.lane.setDisallowed(lane_id, ["passenger"])
                except traci.TraCIException:
                    pass
        self._incident_lanes_closed = True

    def _reroute_vehicles_away_from_incident(self, current_time: float, force: bool = False) -> None:
        if not self._incident_edges:
            return
        if (
            not force
            and self._last_incident_reroute_time is not None
            and current_time - self._last_incident_reroute_time < max(INCIDENT_REROUTE_EPSILON, REROUTING_PERIOD)
        ):
            return

        for vehicle_id in traci.vehicle.getIDList():
            if vehicle_id.startswith("accident_"):
                continue
            try:
                current_edge = traci.vehicle.getRoadID(vehicle_id)
                if current_edge in self._incident_edges:
                    continue
                route = traci.vehicle.getRoute(vehicle_id)
            except traci.TraCIException:
                continue
            if not any(edge_id in self._incident_edges for edge_id in route):
                continue
            try:
                traci.vehicle.rerouteTraveltime(vehicle_id)
            except traci.TraCIException:
                pass

        self._last_incident_reroute_time = current_time

    def get_agent_state(
        self,
        tls_id: str,
        incident_start_time: float,
        current_time: float,
        incident_edges: List[str],
    ) -> Dict[str, Any]:
        lanes = traci.trafficlight.getControlledLanes(tls_id)
        queue_lengths = {}
        for lane_id in lanes:
            edge_id = traci.lane.getEdgeID(lane_id)
            if current_time >= incident_start_time and edge_id in incident_edges:
                queue_lengths[lane_id] = 0
            else:
                queue_lengths[lane_id] = traci.lane.getLastStepHaltingNumber(lane_id)
        current_phase = traci.trafficlight.getPhase(tls_id)
        time_discrete = current_time - incident_start_time if current_time >= incident_start_time else 0.0

        return {
            "queue_lengths": queue_lengths,
            "current_phase": current_phase,
            "time_discrete": time_discrete,
        }

    def init_stress_polygons(self, edge_ids: List[str]) -> None:
        for edge_id in edge_ids:
            if edge_id.startswith(":"):
                continue
            lane_count = traci.edge.getLaneNumber(edge_id)
            if lane_count <= 0:
                continue
            lane_id = f"{edge_id}_0"
            shape = traci.lane.getShape(lane_id)
            poly_id = f"poly_{edge_id}"
            if poly_id in traci.polygon.getIDList():
                continue
            traci.polygon.add(
                polygonID=poly_id,
                shape=shape,
                color=(255, 165, 0, 0),
                fill=False,
                layer=1,
                lineWidth=8.0,
            )
            self._stress_alpha[edge_id] = 0

    def render_queue_stress(
        self,
        baseline_queues: Dict[str, int],
        tau: float,
        incident_edges: List[str],
        queue_margin: float = 0.0,
    ) -> None:
        for edge_id in baseline_queues.keys():
            poly_id = f"poly_{edge_id}"
            if edge_id in incident_edges:
                if self._stress_alpha.get(edge_id) != 0 and poly_id in traci.polygon.getIDList():
                    traci.polygon.setColor(poly_id, (255, 165, 0, 0))
                    self._stress_alpha[edge_id] = 0
                continue
            current_queue = traci.edge.getLastStepHaltingNumber(edge_id)
            threshold = tau * baseline_queues.get(edge_id, 0) + queue_margin
            excess = max(0, current_queue - threshold)
            alpha = 0 if excess <= 0 else min(255, int(50 + excess * 15))
            if self._stress_alpha.get(edge_id) == alpha:
                continue
            if poly_id not in traci.polygon.getIDList():
                lane_id = f"{edge_id}_0"
                shape = traci.lane.getShape(lane_id)
                traci.polygon.add(
                    polygonID=poly_id,
                    shape=shape,
                    color=(255, 165, 0, 0),
                    fill=False,
                    layer=1,
                    lineWidth=8.0,
                )
            traci.polygon.setColor(poly_id, (255, 165, 0, alpha))
            self._stress_alpha[edge_id] = alpha

    def close(self) -> None:
        traci.close()
