from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from kuka_tool_service.parser import SourceValidationError
from kuka_tool_service.transforms import (
    MetadataRequest,
    VelocityRequest,
    XYZRequest,
    build_annotated_source,
    build_velocity_source,
    build_xyz_source,
)

from conftest import SAMPLE_LINES


FIXTURES = Path(__file__).parent / "fixtures" / "velocity"
XYZ_FIXTURES = Path(__file__).parent / "fixtures" / "xyz"


def request() -> MetadataRequest:
    return MetadataRequest(
        cell_number=4,
        part_prefix=7,
        part_suffix=2,
        part_name="Back Body",
        part_link="PLM-200007-02",
        flow_rate_percent=54,
        cooling_enabled=True,
    )


def test_annotation_preserves_cp1252_crlf_and_unmanaged_text() -> None:
    source = ("; café\r\n" + "\r\n".join(SAMPLE_LINES) + "\r\n").encode("cp1252")
    artifact = build_annotated_source(source, request())
    decoded = artifact.data.decode("cp1252")

    assert artifact.input_sha256 == sha256(source).hexdigest()
    assert artifact.output_sha256 == sha256(artifact.data).hexdigest()
    assert artifact.filename == "CELL04-00702_BACK_BODY_54%.src"
    assert "; café\r\n" in decoded
    assert "DEF C04_00702()\r\n" in decoded
    assert "; Cell Number = CELL04\r\n" in decoded
    assert "; Time Estimate = 00:00\r\n" in decoded
    assert "\n" not in decoded.replace("\r\n", "")
    assert artifact.data.endswith(b"\r\n")


def test_reannotation_replaces_managed_header_without_duplicates() -> None:
    source = ("\n".join(SAMPLE_LINES) + "\n").encode()
    first = build_annotated_source(source, request())
    second = build_annotated_source(first.data, request())
    decoded = second.data.decode()

    assert decoded.count("; Cell Number =") == 1
    assert decoded.count("; Time Estimate =") == 1


def test_annotation_requires_valid_comment_fields() -> None:
    bad = MetadataRequest(**{**request().__dict__, "part_link": "ok; injected"})
    with pytest.raises(SourceValidationError, match="control characters"):
        build_annotated_source(("\n".join(SAMPLE_LINES) + "\n").encode(), bad)


def test_velocity_modification_preserves_context_and_initial_commands() -> None:
    source = ("\r\n".join(SAMPLE_LINES) + "\r\n").encode("cp1252")
    artifact = build_velocity_source(
        source,
        "Cell 04 sample.src",
        VelocityRequest(extrusion_mps=0.042, travel_mps=0.125),
    )
    decoded = artifact.data.decode("cp1252")

    assert artifact.filename == "Cell_04_sample_velocity.src"
    assert artifact.changed_line_count == 4
    assert "$VEL.CP = 0.200000\r\n" in decoded
    assert "$VEL.CP = 0.100000\r\nLIN {X 0, Y 0, Z 0" in decoded
    assert decoded.count("$VEL.CP = 0.042000") == 2
    assert decoded.count("$VEL.CP = 0.125000") == 2
    assert artifact.data.endswith(b"\r\n")


def test_velocity_modification_matches_golden_bytes() -> None:
    source = (FIXTURES / "input.src").read_bytes()
    expected = (FIXTURES / "expected.src").read_bytes()

    artifact = build_velocity_source(
        source,
        "input.src",
        VelocityRequest(extrusion_mps=0.042, travel_mps=0.125),
    )

    assert artifact.data == expected


@pytest.mark.parametrize(
    "lines, message",
    [
        (("DEF BAD()", "$VEL.CP = 0.1", "END"), "requires alternating"),
        (
            (
                "DEF BAD()",
                ";travel end",
                "$VEL.CP = 0.1",
                ";travel end",
                "$VEL.CP = 0.2",
                "END",
            ),
            "markers must alternate",
        ),
    ],
)
def test_velocity_modification_rejects_ambiguous_markers(lines, message) -> None:
    with pytest.raises(SourceValidationError, match=message):
        build_velocity_source(
            ("\n".join(lines) + "\n").encode(),
            "bad.src",
            VelocityRequest(extrusion_mps=0.04, travel_mps=0.1),
        )


def test_xyz_adjustment_matches_golden_bytes() -> None:
    artifact = build_xyz_source(
        (XYZ_FIXTURES / "input.src").read_bytes(),
        "Cell 04.src",
        XYZRequest(x_offset_mm=1.25, y_offset_mm=-2, z_offset_mm=0.25),
    )

    assert artifact.data == (XYZ_FIXTURES / "expected.src").read_bytes()
    assert artifact.filename == "Cell_04_xyz.src"
    assert artifact.changed_line_count == 1


def test_xyz_adjustment_preserves_cp1252_crlf() -> None:
    source = ("; café\r\n" + "\r\n".join(SAMPLE_LINES) + "\r\n").encode("cp1252")
    artifact = build_xyz_source(
        source,
        "sample.src",
        XYZRequest(x_offset_mm=1, y_offset_mm=-2, z_offset_mm=0.5),
    )
    decoded = artifact.data.decode("cp1252")

    assert artifact.changed_line_count == 2
    assert "; café\r\n" in decoded
    assert "LIN {X 101.000, Y -2.000, Z 0.500}" in decoded
    assert "LIN {X 110, Y 0, Z 0}" in decoded
    assert artifact.data.endswith(b"\r\n")


def test_xyz_adjustment_can_target_inclusive_layer_range() -> None:
    source = ("\n".join(SAMPLE_LINES) + "\n").encode()
    artifact = build_xyz_source(
        source,
        "sample.src",
        XYZRequest(1, -2, 0.5, first_layer=1, last_layer=1),
    )

    assert artifact.filename == "sample_xyz_L0001-L0001.src"
    assert artifact.changed_line_count == 1
    assert b"LIN {X 100, Y 0, Z 0}" in artifact.data
    assert b"LIN {Z 10.500, X 211.000, Y -2.000}" in artifact.data


def test_xyz_adjustment_rejects_invalid_or_out_of_range_layer_selection() -> None:
    source = ("\n".join(SAMPLE_LINES) + "\n").encode()
    with pytest.raises(SourceValidationError, match="first not greater than last"):
        build_xyz_source(source, "bad.src", XYZRequest(1, 0, 0, 2, 1))
    with pytest.raises(SourceValidationError, match="contains 2 extrusion layers"):
        build_xyz_source(source, "bad.src", XYZRequest(1, 0, 0, 2, 2))


def test_xyz_adjustment_rejects_incomplete_extrusion_lin() -> None:
    source = b"DEF BAD()\n;travel end\nLIN {X 1, Y 2}\n;travel start\nEND\n"
    with pytest.raises(SourceValidationError, match="exactly one X, Y, and Z"):
        build_xyz_source(
            source,
            "bad.src",
            XYZRequest(x_offset_mm=1, y_offset_mm=0, z_offset_mm=0),
        )


def test_xyz_adjustment_rejects_zero_or_out_of_range_offsets() -> None:
    source = ("\n".join(SAMPLE_LINES) + "\n").encode()
    with pytest.raises(SourceValidationError, match="non-zero"):
        build_xyz_source(source, "bad.src", XYZRequest(0, 0, 0))
    with pytest.raises(SourceValidationError, match="between -1000 and 1000"):
        build_xyz_source(source, "bad.src", XYZRequest(1001, 0, 0))
