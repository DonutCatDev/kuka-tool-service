"""Bounded mesh and strict extrusion-path browser overlay data."""

from __future__ import annotations

from dataclasses import dataclass

from .layer_inspector import LayerSummary, inspect_layers
from .mesh import parse_mesh_csv
from .parser import SourceValidationError


MAX_OVERLAY_MESH_POINTS = 10_000


@dataclass(frozen=True)
class OverlayMeshPoint:
    cx: float
    cy: float
    color: str
    x: float
    y: float
    height: float | None


@dataclass(frozen=True)
class PathOverlay:
    source_filename: str
    mesh_filename: str
    source_sha256: str
    mesh_sha256: str
    layer: LayerSummary
    mesh_points: tuple[OverlayMeshPoint, ...]
    mesh_point_count: int
    missing_count: int
    path_point_count: int
    rendered_path_point_count: int
    outside_mesh_count: int
    svg_path_points: str
    coordinate_bounds: dict[str, float]


def build_path_overlay(
    source_data: bytes,
    source_filename: str,
    mesh_data: bytes,
    mesh_filename: str,
    layer_index: int,
) -> PathOverlay:
    """Map one parsed extrusion layer and all mesh samples into one SVG space."""

    layers = inspect_layers(source_data, source_filename, layer_index)
    mesh = parse_mesh_csv(mesh_data)
    mesh_point_count = len(mesh.x_values) * len(mesh.y_values)
    if mesh_point_count > MAX_OVERLAY_MESH_POINTS:
        raise SourceValidationError(
            f"Overlay mesh contains {mesh_point_count:,} points; "
            f"the rendering limit is {MAX_OVERLAY_MESH_POINTS:,}."
        )

    path_xs = [point[0] for point in layers.preview_points]
    path_ys = [point[1] for point in layers.preview_points]
    x_min = min(mesh.x_values[0], min(path_xs))
    x_max = max(mesh.x_values[-1], max(path_xs))
    y_min = min(mesh.y_values[0], min(path_ys))
    y_max = max(mesh.y_values[-1], max(path_ys))
    bounds = {"min_x": x_min, "max_x": x_max, "min_y": y_min, "max_y": y_max}

    def svg_x(value: float) -> float:
        return _scale(value, x_min, x_max, 900)

    def svg_y(value: float) -> float:
        return 600 - _scale(value, y_min, y_max, 600)

    points: list[OverlayMeshPoint] = []
    for x_index, x_value in enumerate(mesh.x_values):
        for y_index, y_value in enumerate(mesh.y_values):
            height = mesh.z_values[x_index][y_index]
            points.append(
                OverlayMeshPoint(
                    cx=svg_x(x_value),
                    cy=svg_y(y_value),
                    color=_height_color(height, mesh.minimum_height, mesh.maximum_height),
                    x=x_value,
                    y=y_value,
                    height=height,
                )
            )
    outside = sum(
        1
        for x_value, y_value, _ in layers.preview_points
        if x_value < mesh.x_values[0]
        or x_value > mesh.x_values[-1]
        or y_value < mesh.y_values[0]
        or y_value > mesh.y_values[-1]
    )
    path = " ".join(
        f"{svg_x(x_value):.2f},{svg_y(y_value):.2f}"
        for x_value, y_value, _ in layers.rendered_preview_points
    )
    return PathOverlay(
        source_filename=source_filename,
        mesh_filename=mesh_filename,
        source_sha256=layers.input_sha256,
        mesh_sha256=mesh.sha256,
        layer=layers.preview_layer,
        mesh_points=tuple(points),
        mesh_point_count=mesh_point_count,
        missing_count=mesh.missing_count,
        path_point_count=layers.preview_point_count,
        rendered_path_point_count=layers.rendered_point_count,
        outside_mesh_count=outside,
        svg_path_points=path,
        coordinate_bounds=bounds,
    )


def _scale(value: float, minimum: float, maximum: float, size: float) -> float:
    if maximum == minimum:
        return size / 2
    return 30 + ((value - minimum) / (maximum - minimum) * (size - 60))


def _height_color(height: float | None, minimum: float, maximum: float) -> str:
    if height is None:
        return "#8b96a3"
    fraction = 0.5 if maximum == minimum else (height - minimum) / (maximum - minimum)
    hue = 240 - (240 * fraction)
    return f"hsl({hue:.1f} 72% 48%)"
