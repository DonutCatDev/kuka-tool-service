from __future__ import annotations

from pathlib import Path

import pytest

from kuka_tool_service.mesh import parse_mesh_csv
from kuka_tool_service.mesh_editor import MeshFalloffRequest, build_falloff_mesh
from kuka_tool_service.parser import SourceValidationError


FIXTURES = Path(__file__).parent / "fixtures" / "mesh_falloff"
SOURCE = (FIXTURES / "input.csv").read_bytes()


def request(**overrides) -> MeshFalloffRequest:
    values = {
        "operation": "add",
        "value": 2,
        "center_x": 10,
        "center_y": 10,
        "radius_mm": 10.1,
        "falloff": "linear",
    }
    values.update(overrides)
    return MeshFalloffRequest(**values)


def test_linear_falloff_edit_matches_golden_and_reparses() -> None:
    artifact = build_falloff_mesh(SOURCE, "Measured Mesh.csv", request())

    assert artifact.filename == "Measured_Mesh_falloff.csv"
    assert artifact.changed_cell_count == 5
    assert artifact.data == (FIXTURES / "expected.csv").read_bytes()
    assert parse_mesh_csv(artifact.data).measured_count == 9


@pytest.mark.parametrize(
    "falloff, expected",
    [("linear", 1.0), ("quadratic", 1.5), ("cubic", 1.75)],
)
def test_falloff_curves_match_grouped_edit_convention(falloff, expected) -> None:
    source = b",0,5,10\n0,0,0,0\n10,0,0,0\n"
    artifact = build_falloff_mesh(
        source,
        "mesh.csv",
        request(center_x=0, center_y=0, radius_mm=10, falloff=falloff),
    )

    assert parse_mesh_csv(artifact.data).z_values[0][1] == expected


@pytest.mark.parametrize(
    "operation, expected",
    [("set", 3.5), ("subtract", 4.0), ("multiply", 7.5)],
)
def test_weighted_operations_blend_from_current_value(operation, expected) -> None:
    source = b",0,5,10\n0,5,5,5\n10,5,5,5\n"
    artifact = build_falloff_mesh(
        source,
        "mesh.csv",
        request(operation=operation, center_x=0, center_y=0, radius_mm=10),
    )

    assert parse_mesh_csv(artifact.data).z_values[0][1] == expected


def test_falloff_rejects_missing_empty_and_invalid_regions() -> None:
    missing = b",0,10\n0,1,\n10,3,4\n"
    with pytest.raises(SourceValidationError, match="unmeasured mesh cell"):
        build_falloff_mesh(missing, "mesh.csv", request(center_x=0, center_y=0, radius_mm=20))
    with pytest.raises(SourceValidationError, match="contains no mesh coordinates"):
        build_falloff_mesh(SOURCE, "mesh.csv", request(center_x=100, center_y=100, radius_mm=1))
    with pytest.raises(SourceValidationError, match="linear, quadratic, or cubic"):
        build_falloff_mesh(SOURCE, "mesh.csv", request(falloff="step"))
