from __future__ import annotations

from pathlib import Path

import pytest

from kuka_tool_service.mesh import compensated_speed, parse_mesh_csv
from kuka_tool_service.parser import SourceValidationError


FIXTURE = Path(__file__).parent / "fixtures" / "mesh" / "valid.csv"


def test_parse_mesh_reports_grid_and_missing_values() -> None:
    mesh = parse_mesh_csv(FIXTURE.read_bytes())

    assert mesh.x_values == (0.0, 10.0)
    assert mesh.y_values == (0.0, 10.0)
    assert mesh.measured_count == 3
    assert mesh.missing_count == 1
    assert mesh.minimum_height == 1
    assert mesh.maximum_height == 3
    assert mesh.average_height == 2


def test_bilinear_lookup_and_explicit_baseline_fallback() -> None:
    complete = parse_mesh_csv(b",0,10\n0,0,10\n10,10,20\n")
    missing = parse_mesh_csv(FIXTURE.read_bytes())

    assert complete.height_at(5, 5, baseline=99) == 10
    assert complete.height_at(20, 5, baseline=99) == 99
    assert missing.height_at(5, 5, baseline=99) == 99


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"X,0,10\n0,1,2\n10,3,4\n", "top-left field"),
        (b",0,10\n0,1,2\n0,3,4\n", "strictly increasing"),
        (b",0,10\n0,1,2\n10,3\n", "same number of fields"),
        (b",0,10\n0,,\n10,,\n", "no measured height"),
        (b",0,10\n0,1,nan\n10,3,4\n", "must be finite"),
    ],
)
def test_mesh_parser_rejects_malformed_grids(payload, message) -> None:
    with pytest.raises(SourceValidationError, match=message):
        parse_mesh_csv(payload)


def test_speed_compensation_matches_reference_zone_convention() -> None:
    assert compensated_speed(0.05, 10.0, 10.0, 1.0, 0.02, 0.0001) == 0.05
    assert compensated_speed(0.05, 12.0, 10.0, 1.0, 0.02, 0.0001) == 0.048
    assert compensated_speed(0.05, 8.0, 10.0, 1.0, 0.02, 0.0001) == 0.052
