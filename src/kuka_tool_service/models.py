"""Typed data models shared by parsing and browser presentation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MotionSegment:
    """One parsed KRL motion command with complete XYZ coordinates."""

    line_number: int
    command: str
    x: float
    y: float
    z: float
    velocity_mps: float | None
    phase: str


@dataclass(frozen=True)
class VelocityCommand:
    """One parsed ``$VEL.CP`` assignment."""

    line_number: int
    value_mps: float
    phase: str


@dataclass(frozen=True)
class SourceDocument:
    """Decoded source plus byte-preservation metadata."""

    original_bytes: bytes = field(repr=False)
    text: str
    lines: tuple[str, ...]
    encoding: str
    newline: str
    newline_label: str
    terminal_newline: bool
    sha256: str


@dataclass(frozen=True)
class InspectionReport:
    """Serializable inspection result for one source document."""

    filename: str
    sha256: str
    byte_count: int
    line_count: int
    encoding: str
    newline: str
    terminal_newline: bool
    def_name: str | None
    ptp_count: int
    lin_count: int
    incomplete_motion_count: int
    velocity_command_count: int
    velocity_distribution: dict[str, dict[str, int]]
    travel_start_count: int
    travel_end_count: int
    extrusion_layer_count: int
    return_travel_count: int
    z_layer_count: int
    wipe_count: int
    bounds: dict[str, dict[str, float]] | None
    path_distance_mm: float
    estimated_runtime_seconds: float
    initial_layer_speed_mps: float | None
    final_layer_speed_mps: float | None
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary."""

        return asdict(self)
