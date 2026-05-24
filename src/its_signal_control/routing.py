from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReroutingPolicy:
    probability: float = 1.0
    period_seconds: int = 10
    incident_activation_offset_seconds: int = 0

    def to_sumo_args(self) -> list[str]:
        return [
            "--device.rerouting.probability",
            str(self.probability),
            "--device.rerouting.period",
            str(self.period_seconds),
        ]


def build_rerouting_policy(
    probability: float,
    period_seconds: int,
    incident_activation_offset_seconds: int = 0,
) -> ReroutingPolicy:
    if not 0.0 <= probability <= 1.0:
        raise ValueError("Rerouting probability must be between 0.0 and 1.0.")
    if period_seconds <= 0:
        raise ValueError("Rerouting period must be positive.")
    return ReroutingPolicy(
        probability=probability,
        period_seconds=period_seconds,
        incident_activation_offset_seconds=incident_activation_offset_seconds,
    )
