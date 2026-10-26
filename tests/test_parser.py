from __future__ import annotations

import pytest

from kuka_tool_service.parser import SourceValidationError, decode_source, inspect_source

from conftest import sample_src


def test_inspection_recreates_lfam_marker_conventions() -> None:
    report = inspect_source(sample_src(), filename="fixture.src")

    assert report.filename == "fixture.src"
    assert report.encoding == "utf-8"
    assert report.newline == "CRLF"
    assert report.terminal_newline is True
    assert report.def_name == "SAMPLE"
    assert report.ptp_count == 1
    assert report.lin_count == 6
    assert report.travel_start_count == 2
    assert report.travel_end_count == 2
    assert report.extrusion_layer_count == 2
    assert report.return_travel_count == 3
    assert report.z_layer_count == 2
    assert report.wipe_count == 2
    assert report.path_distance_mm == pytest.approx(220.0)
    assert report.estimated_runtime_seconds == pytest.approx(4.2)
    assert report.initial_layer_speed_mps == pytest.approx(0.05)
    assert report.final_layer_speed_mps == pytest.approx(0.05)
    assert report.bounds == {
        "x": {"min": 0.0, "max": 210.0},
        "y": {"min": 0.0, "max": 0.0},
        "z": {"min": 0.0, "max": 10.0},
    }
    assert report.warnings == ()


def test_parser_accepts_coordinate_reordering_and_scientific_notation() -> None:
    data = b"DEF TEST()\n$VEL.CP=.5\nPTP {Y 2, X 1, Z 3}\nLIN {Z 4e0, X -1.5, Y +2.5}\n"
    report = inspect_source(data)

    assert report.ptp_count == 1
    assert report.lin_count == 1
    assert report.bounds == {
        "x": {"min": -1.5, "max": 1.0},
        "y": {"min": 2.0, "max": 2.5},
        "z": {"min": 3.0, "max": 4.0},
    }


def test_incomplete_motion_is_reported_not_silently_counted() -> None:
    report = inspect_source(b"DEF TEST()\nLIN {X 1, Y 2}\n")

    assert report.lin_count == 1
    assert report.incomplete_motion_count == 1
    assert any("complete XYZ" in warning for warning in report.warnings)


def test_cp1252_and_mixed_newlines_are_identified() -> None:
    document = decode_source("DEF MÖBEL()\r\n; café\nEND\r\n".encode("cp1252"))

    assert document.encoding == "cp1252"
    assert document.newline_label == "mixed"


def test_utf8_bom_is_identified_without_changing_the_source_hash() -> None:
    data = b"\xef\xbb\xbfDEF TEST()\r\nEND\r\n"
    document = decode_source(data)

    assert document.encoding == "utf-8-sig"
    assert document.text.startswith("DEF TEST()")
    assert len(document.sha256) == 64


def test_empty_source_is_rejected() -> None:
    with pytest.raises(SourceValidationError, match="empty"):
        inspect_source(b"")


def test_parse_time_limit_fails_closed() -> None:
    data = ("DEF TEST()\n" + "LIN {X 1, Y 2, Z 3}\n" * 5000).encode()
    with pytest.raises(SourceValidationError, match="processing limit"):
        inspect_source(data, max_parse_seconds=1e-12)
