from __future__ import annotations

import pytest

from kuka_tool_service.layer_inspector import MAX_PREVIEW_POINTS, inspect_layers
from kuka_tool_service.parser import SourceValidationError

from conftest import sample_src


def test_layer_inspection_summarizes_and_previews_requested_layer() -> None:
    report = inspect_layers(sample_src(), "fixture.src", 1)

    assert len(report.layers) == 2
    assert report.preview_layer.index == 1
    assert report.preview_layer.start_line == 15
    assert report.preview_layer.end_line == 18
    assert report.preview_layer.motion_count == 1
    assert report.preview_layer.z_min == report.preview_layer.z_max == 10
    assert report.preview_point_count == report.rendered_point_count == 1
    assert report.svg_points == "400.00,250.00"


def test_layer_inspection_rejects_out_of_range_and_incomplete_layers() -> None:
    with pytest.raises(SourceValidationError, match="contains 2 extrusion layers"):
        inspect_layers(sample_src(), "fixture.src", 2)
    with pytest.raises(SourceValidationError, match="missing a travel-start marker"):
        inspect_layers(
            sample_src().replace(
                b";travel start\r\n$VEL.CP = 0.100000\r\nLIN {X 210",
                b";missing\r\n$VEL.CP = 0.100000\r\nLIN {X 210",
            ),
            "bad.src",
            0,
        )


def test_layer_inspection_rejects_empty_or_incomplete_extrusion_regions() -> None:
    empty = b"DEF BAD()\n;travel end\n$VEL.CP = 0.05\n;travel start\nEND\n"
    incomplete = b"DEF BAD()\n;travel end\nLIN {X 1, Y 2}\n;travel start\nEND\n"
    with pytest.raises(SourceValidationError, match="has no complete LIN"):
        inspect_layers(empty, "bad.src", 0)
    with pytest.raises(SourceValidationError, match="exactly one X, Y, and Z"):
        inspect_layers(incomplete, "bad.src", 0)


def test_layer_preview_downsamples_large_path_to_fixed_limit() -> None:
    motions = "\n".join(f"LIN {{X {index}, Y {index % 7}, Z 0}}" for index in range(5_010))
    source = f"DEF LARGE()\n;travel end\n{motions}\n;travel start\nEND\n".encode()
    report = inspect_layers(source, "large.src", 0)

    assert report.preview_point_count == 5_010
    assert report.rendered_point_count == MAX_PREVIEW_POINTS
    assert len(report.svg_points.split()) == MAX_PREVIEW_POINTS
