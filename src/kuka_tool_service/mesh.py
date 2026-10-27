"""Strict CSV mesh parsing and dependency-free interpolation."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from hashlib import sha256
from io import StringIO
import math

from .parser import SourceValidationError


MAX_MESH_BYTES = 8 * 1024 * 1024
MAX_MESH_AXIS = 2_000
MAX_MESH_CELLS = 1_000_000


@dataclass(frozen=True)
class MeshGrid:
    sha256: str
    encoding: str
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    z_values: tuple[tuple[float | None, ...], ...]
    measured_count: int
    missing_count: int
    minimum_height: float
    maximum_height: float
    average_height: float

    def height_at(self, x: float, y: float, baseline: float) -> float:
        """Return bilinear height or the explicit baseline outside/through gaps."""

        if not all(math.isfinite(value) for value in (x, y, baseline)):
            raise SourceValidationError("Mesh lookup values must be finite.")
        x_index = _bracket(self.x_values, x)
        y_index = _bracket(self.y_values, y)
        if x_index is None or y_index is None:
            return baseline
        x0, x1 = self.x_values[x_index], self.x_values[x_index + 1]
        y0, y1 = self.y_values[y_index], self.y_values[y_index + 1]
        corners = (
            self.z_values[x_index][y_index],
            self.z_values[x_index + 1][y_index],
            self.z_values[x_index][y_index + 1],
            self.z_values[x_index + 1][y_index + 1],
        )
        if any(value is None for value in corners):
            return baseline
        z00, z10, z01, z11 = (float(value) for value in corners)
        tx = (x - x0) / (x1 - x0)
        ty = (y - y0) / (y1 - y0)
        return (
            z00 * (1 - tx) * (1 - ty)
            + z10 * tx * (1 - ty)
            + z01 * (1 - tx) * ty
            + z11 * tx * ty
        )


def parse_mesh_csv(data: bytes) -> MeshGrid:
    if not data:
        raise SourceValidationError("The uploaded mesh CSV is empty.")
    if len(data) > MAX_MESH_BYTES:
        raise SourceValidationError("The uploaded mesh CSV exceeds the 8 MiB limit.")
    encoding = "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise SourceValidationError("Mesh CSV must use UTF-8 encoding.") from exc
    try:
        rows = list(csv.reader(StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise SourceValidationError(f"Mesh CSV syntax is invalid: {exc}.") from exc
    if len(rows) < 3 or len(rows[0]) < 3:
        raise SourceValidationError("Mesh CSV requires at least two X rows and two Y columns.")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise SourceValidationError("Every mesh CSV row must contain the same number of fields.")
    if rows[0][0].strip():
        raise SourceValidationError("The mesh CSV top-left field must be empty.")
    if len(rows) - 1 > MAX_MESH_AXIS or width - 1 > MAX_MESH_AXIS:
        raise SourceValidationError("A mesh axis exceeds the 2,000-value limit.")
    if (len(rows) - 1) * (width - 1) > MAX_MESH_CELLS:
        raise SourceValidationError("The mesh exceeds the 1,000,000-cell limit.")

    y_values = _axis(rows[0][1:], "Y")
    x_values = _axis([row[0] for row in rows[1:]], "X")
    z_rows: list[tuple[float | None, ...]] = []
    measured: list[float] = []
    for row_number, row in enumerate(rows[1:], 2):
        z_row: list[float | None] = []
        for column_number, raw in enumerate(row[1:], 2):
            if not raw.strip():
                z_row.append(None)
                continue
            value = _finite_float(raw, f"mesh cell row {row_number}, column {column_number}")
            measured.append(value)
            z_row.append(value)
        z_rows.append(tuple(z_row))
    if not measured:
        raise SourceValidationError("Mesh CSV contains no measured height values.")
    cell_count = len(x_values) * len(y_values)
    return MeshGrid(
        sha256=sha256(data).hexdigest(),
        encoding=encoding,
        x_values=x_values,
        y_values=y_values,
        z_values=tuple(z_rows),
        measured_count=len(measured),
        missing_count=cell_count - len(measured),
        minimum_height=min(measured),
        maximum_height=max(measured),
        average_height=sum(measured) / len(measured),
    )


def compensated_speed(
    base_speed: float,
    height: float,
    baseline_height: float,
    zone_step_mm: float,
    speed_step_fraction: float,
    tolerance_mps: float,
) -> float:
    """Recreate the reference zone-to-speed convention with explicit bounds."""

    values = (base_speed, height, baseline_height, zone_step_mm, speed_step_fraction, tolerance_mps)
    if not all(math.isfinite(value) for value in values):
        raise SourceValidationError("Speed compensation parameters must be finite.")
    if not 0.001 <= base_speed <= 0.1:
        raise SourceValidationError("Base speed must be between 0.001 and 0.1 m/s.")
    if not 0 < zone_step_mm <= 100:
        raise SourceValidationError("Zone step must be greater than 0 and at most 100 mm.")
    if not -1 <= speed_step_fraction <= 1:
        raise SourceValidationError("Speed step fraction must be between -1 and 1.")
    if not 0 <= tolerance_mps <= 0.1:
        raise SourceValidationError("Speed tolerance must be between 0 and 0.1 m/s.")
    deviation = height - baseline_height
    if abs(deviation) < zone_step_mm / 2:
        return round(base_speed, 6)
    steps = round(deviation / zone_step_mm)
    adjusted = round(base_speed * (1 - (steps * speed_step_fraction)), 6)
    if abs(adjusted - base_speed) < tolerance_mps:
        return round(base_speed, 6)
    return max(0.001, min(0.1, adjusted))


def _axis(raw_values: list[str], label: str) -> tuple[float, ...]:
    values = tuple(_finite_float(raw, f"{label} axis") for raw in raw_values)
    if any(current <= previous for previous, current in zip(values, values[1:])):
        raise SourceValidationError(f"Mesh {label} coordinates must be strictly increasing and unique.")
    return values


def _finite_float(raw: str, label: str) -> float:
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise SourceValidationError(f"{label} must be numeric.") from exc
    if not math.isfinite(value):
        raise SourceValidationError(f"{label} must be finite.")
    return value


def _bracket(values: tuple[float, ...], target: float) -> int | None:
    if target < values[0] or target > values[-1]:
        return None
    if target == values[-1]:
        return len(values) - 2
    for index in range(len(values) - 1):
        if values[index] <= target <= values[index + 1]:
            return index
    return None
