import os
import sys
from typing import Dict, List, Any, Optional

if "SUMO_HOME" in os.environ:
    tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    if tools not in sys.path:
        sys.path.append(tools)
else:
    raise EnvironmentError("SUMO_HOME is not set.")

import sumolib
import traci

from .config import REROUTING_PERIOD, REROUTING_PROBABILITY, SUMO_CONFIG


class SumoEnv:
    def __init__(self, use_gui: bool, step_length: float) -> None:
        self.use_gui = use_gui
        self.step_length = step_length
        self.incident_triggered = False
        self._stress_alpha = {}

        # --- 修正後的動態路徑代碼 ---
        # 1. 取得當前 env.py 的絕對路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. 修改這裡：只要往上推兩層 ".."，就能正確抵達專案根目錄
        # 這樣路徑就會包含 ADP-incident-traffic-recovery-sumo 這一層
        project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))

        # 3. 匯入配置
        from .config import SCENARIO_DIR, NETWORK_FILE
        
        # 4. 拼接出完美的絕對路徑
        net_abs_path = os.path.join(project_root, SCENARIO_DIR, NETWORK_FILE)
        
        # 5. 讀取路網
        import sumolib
        self.net = sumolib.net.readNet(net_abs_path)

    def start_simulation(self, end_time: Optional[float] = None) -> None:
        sumo_binary = "sumo-gui" if self.use_gui else "sumo"
        
        # 這裡也同步改為往上兩層
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
        
        from .config import SCENARIO_DIR, SUMO_CONFIG
        sumo_config_abs_path = os.path.join(project_root, SCENARIO_DIR, SUMO_CONFIG)

        sumo_cmd = [
            sumo_binary,
            "-c", sumo_config_abs_path,
            "--step-length", str(self.step_length),
            "--device.rerouting.probability", str(REROUTING_PROBABILITY),
            "--device.rerouting.period", str(REROUTING_PERIOD),
            "--time-to-teleport", "-1",
            "--no-warnings",
        ]
        if end_time is not None:
            sumo_cmd.extend(["--end", str(end_time)])
        traci.start(sumo_cmd)

    def trigger_incident(self, edge_ids: List[str], current_time: float, start_time: float) -> None:
        if self.incident_triggered:
            return
        if current_time < start_time:
            return

        for vehicle_id in traci.vehicle.getIDList():
            vtype_id = traci.vehicle.getTypeID(vehicle_id)
            default_color = traci.vehicletype.getColor(vtype_id)
            traci.vehicle.setColor(vehicle_id, default_color)

        for edge_id in edge_ids:
            veh_id = f"accident_{edge_id}"
            route_id = f"route_{edge_id}"
            if route_id not in traci.route.getIDList():
                traci.route.add(route_id, [edge_id])
            try:
                traci.vehicle.add(
                    vehID=veh_id,
                    routeID=route_id,
                    departPos="10",
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
                    laneIndex=0,
                    duration=1.0e9,
                )
            except traci.TraCIException:
                pass
            traci.vehicle.setColor(veh_id, (255, 0, 0, 255))

        self.incident_triggered = True

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
