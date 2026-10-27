from __future__ import annotations

import pytest

from kuka_tool_service.parser import SourceValidationError
from kuka_tool_service.path_overlay import MAX_OVERLAY_MESH_POINTS, build_path_overlay


SOURCE = b"DEF PATH()\n;travel end\nLIN {X 0, Y 0, Z 5}\nLIN {X 10, Y 10, Z 5}\n;travel start\nEND\n"
MESH = b",0,10\n0,1,2\n10,3,\n"


def test_path_overlay_maps_mesh_and_path_in_shared_coordinates() -> None:
    report = build_path_overlay(SOURCE, "path.src", MESH, "mesh.csv", 0)

    assert report.layer.index == 0
    assert report.mesh_point_count == 4
    assert report.missing_count == 1
    assert report.path_point_count == report.rendered_path_point_count == 2
    assert report.outside_mesh_count == 0
    assert report.svg_path_points == "30.00,570.00 870.00,30.00"
    assert report.mesh_points[-1].height is None
    assert report.mesh_points[-1].color == "#8b96a3"


def test_path_overlay_reports_points_outside_mesh() -> None:
    source = SOURCE.replace(b"X 10, Y 10", b"X 20, Y 20")
    report = build_path_overlay(source, "path.src", MESH, "mesh.csv", 0)

    assert report.outside_mesh_count == 1
    assert report.coordinate_bounds == {"min_x": 0, "max_x": 20, "min_y": 0, "max_y": 20}


def test_path_overlay_rejects_mesh_above_rendering_limit() -> None:
    axis = ",".join(str(value) for value in range(101))
    row = ",".join("0" for _ in range(101))
    mesh = ("," + axis + "\n" + "".join(f"{x},{row}\n" for x in range(101))).encode()

    with pytest.raises(SourceValidationError, match=f"limit is {MAX_OVERLAY_MESH_POINTS:,}"):
        build_path_overlay(SOURCE, "path.src", mesh, "mesh.csv", 0)
