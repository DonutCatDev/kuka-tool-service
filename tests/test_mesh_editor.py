from __future__ import annotations

from pathlib import Path

import pytest

from kuka_tool_service.mesh import parse_mesh_csv
from kuka_tool_service.mesh_editor import MeshEditRequest, build_edited_mesh
from kuka_tool_service.parser import SourceValidationError


FIXTURES = Path(__file__).parent / "fixtures" / "mesh_edit"
SOURCE = (FIXTURES / "input.csv").read_bytes()


def test_rectangular_add_edit_is_deterministic_and_reparseable() -> None:
    artifact = build_edited_mesh(
        SOURCE,
        "Measured Mesh.csv",
        MeshEditRequest("add", 0.25, 0, 10, 10, 20),
    )

    assert artifact.filename == "Measured_Mesh_edited.csv"
    assert artifact.changed_cell_count == 4
    assert artifact.data == (FIXTURES / "expected.csv").read_bytes()
    parsed = parse_mesh_csv(artifact.data)
    assert parsed.measured_count == 9
    assert parsed.maximum_height == 9


@pytest.mark.parametrize(
    "operation, expected", [("set", 2.0), ("subtract", 3.0), ("multiply", 10.0)]
)
def test_supported_mesh_edit_operations(operation: str, expected: float) -> None:
    artifact = build_edited_mesh(
        SOURCE,
        "mesh.csv",
        MeshEditRequest(operation, 2, 10, 10, 10, 10),
    )

    assert parse_mesh_csv(artifact.data).z_values[1][1] == expected


def test_mesh_edit_rejects_missing_cells_and_empty_or_reversed_bounds() -> None:
    missing = b",0,10\n0,1,\n10,3,4\n"
    with pytest.raises(SourceValidationError, match="unmeasured mesh cell"):
        build_edited_mesh(missing, "mesh.csv", MeshEditRequest("set", 2, 0, 0, 10, 10))
    with pytest.raises(SourceValidationError, match="contain no mesh coordinates"):
        build_edited_mesh(SOURCE, "mesh.csv", MeshEditRequest("set", 2, 1, 9, 0, 20))
    with pytest.raises(SourceValidationError, match="must not exceed"):
        build_edited_mesh(SOURCE, "mesh.csv", MeshEditRequest("set", 2, 10, 0, 0, 20))


def test_mesh_edit_rejects_invalid_operation_and_result() -> None:
    with pytest.raises(SourceValidationError, match="must be set"):
        build_edited_mesh(SOURCE, "mesh.csv", MeshEditRequest("divide", 2, 0, 0, 0, 0))
    with pytest.raises(SourceValidationError, match="resulting mesh height"):
        build_edited_mesh(SOURCE, "mesh.csv", MeshEditRequest("multiply", 10_000, 20, 20, 20, 20))


def test_mesh_edit_preserves_utf8_bom_and_crlf_style() -> None:
    source = b"\xef\xbb\xbf,0,10\r\n0,1,2\r\n10,3,4\r\n"
    artifact = build_edited_mesh(
        source, "mesh.csv", MeshEditRequest("add", 0.5, 0, 10, 10, 10)
    )

    assert artifact.data.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in artifact.data
    assert b"\n" not in artifact.data.replace(b"\r\n", b"")
