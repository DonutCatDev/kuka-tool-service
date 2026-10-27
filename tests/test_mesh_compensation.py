from __future__ import annotations

from pathlib import Path

import pytest

from kuka_tool_service.mesh_compensation import (
    MeshCompensationRequest,
    build_mesh_compensated_source,
)
from kuka_tool_service.parser import SourceValidationError, inspect_source


FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = FIXTURES / "probe" / "input.src"
MESH = FIXTURES / "mesh_compensation" / "mesh.csv"
EXPECTED = FIXTURES / "mesh_compensation" / "expected.src"


def request() -> MeshCompensationRequest:
    return MeshCompensationRequest(
        baseline_height_mm=0,
        zone_step_mm=1,
        speed_step_fraction=0.1,
        speed_tolerance_mps=0.0001,
    )


def test_mesh_compensation_matches_golden_bytes() -> None:
    artifact = build_mesh_compensated_source(
        SOURCE.read_bytes(), MESH.read_bytes(), "Cell 04.src", request()
    )

    assert artifact.data == EXPECTED.read_bytes()
    assert artifact.filename == "Cell_04_mesh_speed.src"
    assert artifact.inserted_speed_count == 2
    assert artifact.compensated_motion_count == 2
    assert artifact.baseline_fallback_count == 0
    assert inspect_source(artifact.data).lin_count == inspect_source(SOURCE.read_bytes()).lin_count


def test_mesh_compensation_preserves_cp1252_crlf_and_coordinates() -> None:
    source = SOURCE.read_text().replace("generated", "café generated").replace("\n", "\r\n").encode("cp1252")
    artifact = build_mesh_compensated_source(source, MESH.read_bytes(), "sample.src", request())

    assert b"caf\xe9 generated fixture\r\n" in artifact.data
    assert b"LIN {Z 10, X 210, Y 0}\r\n" in artifact.data
    assert artifact.data.endswith(b"\r\n")


def test_mesh_compensation_reports_out_of_grid_fallback() -> None:
    mesh = b",0,100\n0,0,0\n150,3,3\n"
    artifact = build_mesh_compensated_source(
        SOURCE.read_bytes(), mesh, "sample.src", request()
    )

    assert artifact.inserted_speed_count == 1
    assert artifact.baseline_fallback_count == 1


def test_mesh_compensation_rejects_no_op() -> None:
    flat = b",0,100\n0,0,0\n300,0,0\n"
    with pytest.raises(SourceValidationError, match="produced no speed changes"):
        build_mesh_compensated_source(SOURCE.read_bytes(), flat, "sample.src", request())
