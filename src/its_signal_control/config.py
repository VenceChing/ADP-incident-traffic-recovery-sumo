import ast
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

RATE = 2500
TIME = 5400
STEP_LENGTH = 1.0
ROUTE_FILE_PREFIX = "grid_4x4"
ROUTE_FILE = f"{ROUTE_FILE_PREFIX}_rate{RATE}.rou.xml"
SCENARIO_DIR = "scenarios/grid_4x4"
SUMO_CONFIG = "sim.sumocfg"
NETWORK_FILE = "grid_4x4.net.xml"
ACTION_SPACE = "legacy_4"
USE_GUI = False
REGENERATE_ROUTES = False
RENDER_STRESS = False
REROUTING_PROBABILITY = 1.0
REROUTING_PERIOD = 10
INCIDENT_BLOCK_TRAVEL_TIME = 1.0e6
INCIDENT_REROUTE_EPSILON = 1.0
INCIDENT_CLOSE_LANES_AFTER_SPAWN = True
ROUTE_HORIZON_TOLERANCE = 10.0

RUN_SINGLE_DEMO = False
RUN_TRAINING = False
RUN_EVALUATION = True
RESET_WEIGHTS_FOR_TRAINING = True
LOAD_WEIGHTS_FOR_EVALUATION = True
WEIGHT_TRANSFER_MODE = "agent_id"
EVALUATION_CONTROLLERS = ["fixed_time_rr", "greedy", "max_pressure", "adp_eval"]
TRAIN_SAVE_WEIGHTS_EVERY_EPISODE = False
TRAIN_WEIGHT_CHECKPOINT_INTERVAL = 10
TRAIN_WEIGHT_CHECKPOINT_DIR = ""

RANDOM_SEED = 7
TRAIN_EPISODES = 140
EVAL_EPISODES_PER_CONTROLLER = 24
TRAIN_INCIDENT_FRACTION = 0.70
TRAIN_INCIDENT_SELECTION = "cycle"

DEFAULT_INCIDENT_EDGES = ["C2B2", "B2C2"]
DEMO_CONTROLLER = "adp_eval"
DEMO_SEED = RANDOM_SEED + 20_000
DEMO_INCIDENT_EDGES = list(DEFAULT_INCIDENT_EDGES)
INCIDENT_TIME = 1200
DECISION_INTERVAL = 10
FIXED_TIME_DECISION_INTERVAL = 20
SIM_END_TIME = max(TIME, INCIDENT_TIME + 1)

KEEPALIVE_ROUTE_ID = "keepalive"
KEEPALIVE_VEH_ID = "keepalive_0"
KEEPALIVE_EDGE_IDS = ["A0B0"]
KEEPALIVE_DEPART = INCIDENT_TIME + 1

TAU = 1.1
ALPHA = 0.0005
GAMMA = 0.95
TRAIN_EPSILON_START = 0.20
TRAIN_EPSILON_END = 0.02
SWITCH_PENALTY_SCALE = 0.10
ADP_VARIANT_LABEL = "metric_reward_action_features_capacity_v1"
ADP_ACTION_SCORING_MODE = "value"
ADP_FEATURE_SET = "full"
ADP_QUEUE_PRIORITY_WEIGHT = 2.0
ADP_TOTAL_QUEUE_WEIGHT = 0.05
ADP_LANE_FAIRNESS_WEIGHT = 0.0
ADP_LANE_FAIRNESS_MARGIN = 5.0
ADP_RESIDUAL_GREEDY_WEIGHT = 1.0
ADP_RESIDUAL_PRESSURE_WEIGHT = 0.35
ADP_RESIDUAL_VALUE_WEIGHT = 0.50
ADP_RESIDUAL_LOOKAHEAD_WEIGHT = 0.65
ADP_RESIDUAL_DOWNSTREAM_PENALTY_WEIGHT = 0.35
ADP_LOOKAHEAD_DEPTH = 1
ADP_GRIDLOCK_PENALTY = 20.0
ADP_MAX_ABS_WEIGHT = 50.0
ADP_MAX_ABS_TD_ERROR = 10.0
ADP_FEATURE_CLIP = 5.0
ADP_QUEUE_SCALE = 50.0
ADP_DISTANCE_SCALE = 6.0
ADP_TIME_SCALE = 120.0
ADP_SPILLBACK_OCCUPANCY_THRESHOLD = 0.85
ADP_VEHICLE_SPACING = 7.5
ADP_UNBOUNDED_DOWNSTREAM_CAPACITY = 1.0e6
ADP_MODEL_EWMA_ALPHA = 0.05
ADP_MIN_MODEL_OBSERVATIONS = 3
ADP_INCIDENT_ACTION_FEATURES_ENABLED = False
ADP_INCIDENT_ACTION_FEATURE_COUNT = 6

VALIDATION_RATE_CANDIDATES = [2500]
TWO_LANE_RATE_CANDIDATES = [2500, 3000, 3500, 4000, 4500, 5000]
THREE_LANE_RATE_CANDIDATES = [3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000]
VALIDATION_SWITCH_PENALTY_SCALES = [0.04]
VALIDATION_QUEUE_PRIORITY_WEIGHTS = [1.0, 1.5, 2.0]
VALIDATION_ALPHA_CANDIDATES = [0.0005, 0.001]
VALIDATION_TD_ERROR_CAPS = [10.0]
VALIDATION_TRAIN_EPISODES = 24
VALIDATION_EVAL_EPISODES = 4

GRIDLOCK_DEBUG_INTERVAL = 300.0
GRIDLOCK_WARMUP_TIME = 600.0
GRIDLOCK_HALTING_RATIO = 0.95
GRIDLOCK_MIN_VEHICLE_FLOOR = 100
GRIDLOCK_WARMUP_DEMAND_FRACTION = 1.25
GRIDLOCK_CONFIRMATION_TIME = 30.0

SUCCESS_MIN_DELAY = 0.0
SUCCESS_CONFIRMATION_TIME = 180.0
SUCCESS_HALTING_RATIO_MULTIPLIER = 1.15
SUCCESS_HALTING_RATIO_MARGIN = 0.05
SUCCESS_HALTING_RATIO_CAP = 0.95
SUCCESS_EDGE_QUEUE_FLOOR = 10.0
SUCCESS_TOTAL_QUEUE_EXCESS_CAP = 25.0

BASELINE_WARMUP_TIME = 300.0
FLOW_WINDOW = 300.0
FLOW_RECOVERY_RATIO = 0.70
MIN_BASELINE_ARRIVAL_RATE = 0.01

YELLOW_SECONDS = 3
ALL_RED_SECONDS = 1

TRACE_ACTIONS = False
TRACE_ACTION_INTERVALS = 12

DECISION_ORDER_STRATEGY = "unified"
DECISION_ORDER_RANDOM_SEED = 42
ALLOW_NEIGHBOR_INFO = False
ADP_NEIGHBOR_FEATURE_MAX_NEIGHBORS = 4

RESULTS_DIR = "results"
LEGACY_WEIGHTS_PATH = "agent_weights.json"
WEIGHTS_PATH = os.path.join(RESULTS_DIR, "adp_agent_weights.json")
TRAIN_METRICS_CSV_PATH = os.path.join(RESULTS_DIR, "train_metrics.csv")
EVAL_METRICS_CSV_PATH = os.path.join(RESULTS_DIR, "eval_metrics.csv")
EVAL_SUMMARY_CSV_PATH = os.path.join(RESULTS_DIR, "eval_summary.csv")
EVAL_PAIRED_SUMMARY_CSV_PATH = os.path.join(RESULTS_DIR, "eval_paired_summary.csv")
DEMO_METRICS_CSV_PATH = os.path.join(RESULTS_DIR, "demo_metrics.csv")
TRAINING_SVG_PATH = os.path.join(RESULTS_DIR, "training_metrics.svg")
EVAL_SVG_PATH = os.path.join(RESULTS_DIR, "eval_comparison.svg")

METRIC_FIELDNAMES = [
    "phase",
    "controller",
    "episode",
    "seed",
    "status",
    "incident_edges",
    "incident_direction",
    "end_time",
    "duration_after_incident",
    "ttr",
    "avg_pre_total_queue",
    "avg_post_total_queue",
    "max_post_total_queue",
    "final_total_queue",
    "queue_excess_area",
    "avg_queue_excess",
    "max_nonincident_queue_excess",
    "final_nonincident_queue_excess",
    "final_incident_queue",
    "max_incident_queue",
    "avg_post_halting_ratio",
    "recent_halting_ratio",
    "max_post_halting_ratio",
    "final_halting_ratio",
    "baseline_halting_ratio",
    "success_halting_ratio_threshold",
    "baseline_arrival_rate",
    "recent_arrival_rate",
    "throughput_recovery_ratio",
    "success_candidate_seconds",
    "gridlock_candidate_seconds",
    "switch_count",
    "keep_count",
    "switch_rate",
    "lane_fairness_imbalance",
    "avg_lane_fairness_imbalance",
    "max_lane_fairness_imbalance",
    "changed_agents",
    "total_l1_delta",
    "avg_weight_l1",
    "adp_variant",
    "heuristic_note",
]


PATH_CONSTANTS = [
    "WEIGHTS_PATH",
    "TRAIN_WEIGHT_CHECKPOINT_DIR",
    "TRAIN_METRICS_CSV_PATH",
    "EVAL_METRICS_CSV_PATH",
    "EVAL_SUMMARY_CSV_PATH",
    "EVAL_PAIRED_SUMMARY_CSV_PATH",
    "DEMO_METRICS_CSV_PATH",
    "TRAINING_SVG_PATH",
    "EVAL_SVG_PATH",
]


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value.strip("\"'")


def _strip_yaml_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for idx, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", "\""}:
            quote = char
            continue
        if char == "#":
            return line[:idx]
    return line


def load_preset(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a small flat YAML preset without requiring PyYAML at runtime."""
    preset_path = Path(path)
    if not preset_path.is_absolute():
        preset_path = REPO_ROOT / preset_path
    data: dict[str, Any] = {}
    for raw_line in preset_path.read_text(encoding="utf-8").splitlines():
        line = _strip_yaml_comment(raw_line).strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            data[key] = _parse_scalar(value)
    return data


def _refresh_derived_paths() -> None:
    globals()["ROUTE_FILE"] = f"{ROUTE_FILE_PREFIX}_rate{RATE}.rou.xml"
    globals()["SIM_END_TIME"] = max(TIME, INCIDENT_TIME + 1)
    globals()["WEIGHTS_PATH"] = os.path.join(RESULTS_DIR, "adp_agent_weights.json")
    globals()["TRAIN_WEIGHT_CHECKPOINT_DIR"] = os.path.join(RESULTS_DIR, "checkpoints")
    globals()["TRAIN_METRICS_CSV_PATH"] = os.path.join(RESULTS_DIR, "train_metrics.csv")
    globals()["EVAL_METRICS_CSV_PATH"] = os.path.join(RESULTS_DIR, "eval_metrics.csv")
    globals()["EVAL_SUMMARY_CSV_PATH"] = os.path.join(RESULTS_DIR, "eval_summary.csv")
    globals()["EVAL_PAIRED_SUMMARY_CSV_PATH"] = os.path.join(RESULTS_DIR, "eval_paired_summary.csv")
    globals()["DEMO_METRICS_CSV_PATH"] = os.path.join(RESULTS_DIR, "demo_metrics.csv")
    globals()["TRAINING_SVG_PATH"] = os.path.join(RESULTS_DIR, "training_metrics.svg")
    globals()["EVAL_SVG_PATH"] = os.path.join(RESULTS_DIR, "eval_comparison.svg")


def apply_overrides(overrides: dict[str, Any]) -> None:
    explicit_paths = {key for key in overrides if key in PATH_CONSTANTS or key == "ROUTE_FILE"}
    for key, value in overrides.items():
        if key not in globals():
            raise KeyError(f"Unknown configuration key: {key}")
        globals()[key] = value
    if {"RATE", "ROUTE_FILE_PREFIX", "RESULTS_DIR", "TIME", "INCIDENT_TIME"} & set(overrides):
        current_paths = {key: globals()[key] for key in explicit_paths}
        _refresh_derived_paths()
        globals().update(current_paths)


def apply_preset(path: str | os.PathLike[str]) -> dict[str, Any]:
    overrides = load_preset(path)
    apply_overrides(overrides)
    return overrides
