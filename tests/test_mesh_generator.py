from __future__ import annotations

from pathlib import Path

import pytest

from kuka_tool_service.mesh import parse_mesh_csv
from kuka_tool_service.mesh_generator import MeshGenerationRequest, build_mesh_from_source
from kuka_tool_service.parser import SourceValidationError

from conftest import sample_src


FIXTURES = Path(__file__).parent / "fixtures" / "mesh_generation"


def request(**overrides) -> MeshGenerationRequest:
    values = {
        "spacing_x_mm": 50,
        "spacing_y_mm": 50,
        "margin_mm": 0,
        "baseline_height_mm": 7.5,
    }
    values.update(overrides)
    return MeshGenerationRequest(**values)


def test_generated_mesh_matches_golden_and_reparses() -> None:
    artifact = build_mesh_from_source(sample_src(), "Cell 04.src", request())

    assert artifact.data == (FIXTURES / "expected.csv").read_bytes()
    assert artifact.filename == "Cell_04_mesh.csv"
    assert artifact.x_count == 4
    assert artifact.y_count == 2
    assert artifact.cell_count == 8
    assert artifact.bounds == {"min_x": 100, "max_x": 250, "min_y": 0, "max_y": 50}
    mesh = parse_mesh_csv(artifact.data)
    assert mesh.measured_count == 8
    assert mesh.minimum_height == mesh.maximum_height == 7.5


def test_generated_mesh_snaps_outward_with_margin() -> None:
    artifact = build_mesh_from_source(
        sample_src(), "sample.src", request(spacing_x_mm=40, spacing_y_mm=25, margin_mm=5)
    )

    assert artifact.bounds == {"min_x": 80, "max_x": 240, "min_y": -25, "max_y": 25}
    assert artifact.cell_count == 15


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"spacing_x_mm": 0.01}, "spacing must be between"),
        ({"margin_mm": -1}, "margin must be between"),
        ({"baseline_height_mm": 10_001}, "Baseline height"),
    ],
)
def test_generated_mesh_rejects_invalid_parameters(overrides, message) -> None:
    with pytest.raises(SourceValidationError, match=message):
        build_mesh_from_source(sample_src(), "sample.src", request(**overrides))


def test_generated_mesh_caps_axis_count() -> None:
    with pytest.raises(SourceValidationError, match="axis exceeds"):
        build_mesh_from_source(
            sample_src(),
            "sample.src",
            request(spacing_x_mm=0.1, spacing_y_mm=0.1, margin_mm=1000),
        )


def test_generated_mesh_caps_cell_count() -> None:
    source = sample_src().replace(b"LIN {Z 10, X 210, Y 0}", b"LIN {Z 10, X 210, Y 100}")
    with pytest.raises(SourceValidationError, match="limit is 1,000,000"):
        build_mesh_from_source(
            source,
            "sample.src",
            request(spacing_x_mm=0.1, spacing_y_mm=0.1),
        )
