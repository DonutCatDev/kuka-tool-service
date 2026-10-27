"""Strict extrusion-layer summaries and bounded browser preview data."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from time import monotonic

from .parser import MAX_PARSE_SECONDS, SourceValidationError, decode_source, inspect_source


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
_LIN = re.compile(r"^\s*LIN\b\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_COORD = re.compile(rf"\b(?P<axis>[XYZ])\s*(?P<value>{_NUMBER})", re.IGNORECASE)
_TRAVEL_START = re.compile(r";\s*travel\s+start\b", re.IGNORECASE)
_TRAVEL_END = re.compile(r";\s*travel\s+end\b", re.IGNORECASE)
MAX_PREVIEW_POINTS = 5_000


@dataclass(frozen=True)
class LayerSummary:
    index: int
    start_line: int
    end_line: int
    motion_count: int
    z_min: float
    z_max: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    path_distance_mm: float


@dataclass(frozen=True)
class LayerInspection:
    filename: str
    input_sha256: str
    layers: tuple[LayerSummary, ...]
    preview_layer: LayerSummary
    preview_point_count: int
    rendered_point_count: int
    preview_points: tuple[tuple[float, float, float], ...]
    rendered_preview_points: tuple[tuple[float, float, float], ...]
    svg_points: str


def inspect_layers(data: bytes, filename: str, preview_index: int) -> LayerInspection:
    """Parse strict extrusion regions and prepare one bounded SVG polyline."""

    if not isinstance(preview_index, int) or not 0 <= preview_index <= 499_999:
        raise SourceValidationError("Preview layer must be an integer from 0 through 499999.")
    document = decode_source(data)
    inspect_source(data, filename=filename)
    deadline = monotonic() + MAX_PARSE_SECONDS
    expected = "end"
    active_start: int | None = None
    active_points: list[tuple[float, float, float]] = []
    summaries: list[LayerSummary] = []
    preview_points: list[tuple[float, float, float]] = []

    for line_number, line in enumerate(document.lines, 1):
        if line_number % 4096 == 0 and monotonic() > deadline:
            raise SourceValidationError("Layer inspection exceeded the 15 second processing limit.")
        has_start = _TRAVEL_START.search(line) is not None
        has_end = _TRAVEL_END.search(line) is not None
        if has_start and has_end:
            raise SourceValidationError(f"Line {line_number} contains ambiguous travel markers.")
        if has_end:
            if expected != "end":
                raise SourceValidationError(
                    f"Unexpected travel-end marker on line {line_number}; markers must alternate."
                )
            expected = "start"
            active_start = line_number
            active_points = []
            continue
        if has_start:
            if expected != "start" or active_start is None:
                raise SourceValidationError(
                    f"Unexpected travel-start marker on line {line_number}; markers must alternate."
                )
            summary = _summarize_layer(
                len(summaries), active_start, line_number, active_points
            )
            summaries.append(summary)
            if summary.index == preview_index:
                preview_points = list(active_points)
            expected = "end"
            active_start = None
            active_points = []
            continue

        motion = _LIN.search(line)
        if motion is None or active_start is None:
            continue
        coordinates = list(_COORD.finditer(motion.group("body")))
        axes = [match.group("axis").upper() for match in coordinates]
        if set(axes) != {"X", "Y", "Z"} or len(axes) != 3:
            raise SourceValidationError(
                f"Extrusion LIN on line {line_number} must contain exactly one X, Y, and Z coordinate."
            )
        values = {
            match.group("axis").upper(): float(match.group("value"))
            for match in coordinates
        }
        if not all(math.isfinite(value) for value in values.values()):
            raise SourceValidationError(
                f"Extrusion LIN on line {line_number} contains a non-finite coordinate."
            )
        active_points.append((values["X"], values["Y"], values["Z"]))

    if expected != "end":
        raise SourceValidationError("The final extrusion layer is missing a travel-start marker.")
    if not summaries:
        raise SourceValidationError("Layer inspection found no complete extrusion layers.")
    if preview_index >= len(summaries):
        raise SourceValidationError(
            f"Preview layer {preview_index} is out of range; the source contains "
            f"{len(summaries)} extrusion layers (0-{len(summaries) - 1})."
        )
    sampled = _downsample(preview_points, MAX_PREVIEW_POINTS)
    return LayerInspection(
        filename=filename,
        input_sha256=document.sha256,
        layers=tuple(summaries),
        preview_layer=summaries[preview_index],
        preview_point_count=len(preview_points),
        rendered_point_count=len(sampled),
        preview_points=tuple(preview_points),
        rendered_preview_points=tuple(sampled),
        svg_points=_svg_points(sampled),
    )


def _summarize_layer(
    index: int,
    start_line: int,
    end_line: int,
    points: list[tuple[float, float, float]],
) -> LayerSummary:
    if not points:
        raise SourceValidationError(
            f"Extrusion layer {index} between lines {start_line} and {end_line} has no complete LIN commands."
        )
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    distance = sum(math.dist(previous, current) for previous, current in zip(points, points[1:]))
    return LayerSummary(
        index=index,
        start_line=start_line,
        end_line=end_line,
        motion_count=len(points),
        z_min=min(zs),
        z_max=max(zs),
        x_min=min(xs),
        x_max=max(xs),
        y_min=min(ys),
        y_max=max(ys),
        path_distance_mm=distance,
    )


def _downsample(
    points: list[tuple[float, float, float]], limit: int
) -> list[tuple[float, float, float]]:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(index * step)] for index in range(limit)]


def _svg_points(points: list[tuple[float, float, float]]) -> str:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    def scale(value: float, minimum: float, maximum: float, size: float) -> float:
        if maximum == minimum:
            return size / 2
        return 20 + ((value - minimum) / (maximum - minimum) * (size - 40))

    return " ".join(
        f"{scale(x, x_min, x_max, 800):.2f},{500 - scale(y, y_min, y_max, 500):.2f}"
        for x, y, _ in points
    )
