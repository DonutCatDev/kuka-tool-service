from __future__ import annotations

from pathlib import Path

import pytest

from kuka_tool_service.parser import SourceValidationError
from kuka_tool_service.probe_generator import ProbeRequest, build_probe_source

from conftest import sample_src


FIXTURES = Path(__file__).parent / "fixtures" / "probe"


def request(**overrides) -> ProbeRequest:
    values = {
        "safe_z_mm": 20,
        "probe_z_mm": 15,
        "spacing_mm": 50,
        "margin_mm": 0,
        "travel_speed_mps": 0.15,
        "probe_speed_mps": 0.055,
        "scan_pattern": "zigzag",
        "scan_priority": "row",
    }
    values.update(overrides)
    return ProbeRequest(**values)


def test_probe_grid_is_deterministic_and_uses_extrusion_bounds() -> None:
    first = build_probe_source(sample_src(), "Cell 04.src", request())
    second = build_probe_source(sample_src(), "Cell 04.src", request())
    text = first.data.decode()

    assert first == second
    assert first.filename == "Cell_04_probe_grid.src"
    assert first.point_count == 5
    assert first.bounds == {"min_x": 55.0, "max_x": 255.0, "min_y": 0.0, "max_y": 0.0}
    assert "; GRID_POINTS = 5" in text
    assert "LIN {X 55.000, Y 0.000, Z 20.000}" in text
    assert "LIN {X 255.000, Y 0.000, Z 15.000}" in text
    assert "; generated fixture" not in text
    assert text.endswith("END\r\n")


def test_probe_grid_matches_golden_bytes() -> None:
    artifact = build_probe_source(
        (FIXTURES / "input.src").read_bytes(), "fixture.src", request()
    )

    assert artifact.data == (FIXTURES / "expected.src").read_bytes()


def test_probe_grid_preserves_motion_orientation_fields() -> None:
    source = sample_src().replace(
        b"LIN {X 100, Y 0, Z 0}",
        b"LIN {Z 0, A 12.5, Y 0, X 100, E1 7} C_DIS",
        1,
    )
    artifact = build_probe_source(source, "sample.src", request())

    assert b"A 12.5" in artifact.data
    assert b"E1 7" in artifact.data
    assert b"C_DIS" in artifact.data


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"safe_z_mm": 10, "probe_z_mm": 10}, "Safe Z must be greater"),
        ({"spacing_mm": 0.01}, "spacing must be between"),
        ({"scan_pattern": "spiral"}, "one_way or zigzag"),
    ],
)
def test_probe_grid_rejects_invalid_parameters(overrides, message) -> None:
    with pytest.raises(SourceValidationError, match=message):
        build_probe_source(sample_src(), "sample.src", request(**overrides))


def test_probe_grid_caps_generated_point_count() -> None:
    with pytest.raises(SourceValidationError, match="limit is 10,000"):
        build_probe_source(sample_src(), "sample.src", request(spacing_mm=0.1, margin_mm=1000))


def test_probe_grid_rejects_out_of_range_generated_bounds() -> None:
    source = sample_src().replace(b"X 210", b"X 20010")
    with pytest.raises(SourceValidationError, match="bounds exceed"):
        build_probe_source(source, "sample.src", request(spacing_mm=1000))
