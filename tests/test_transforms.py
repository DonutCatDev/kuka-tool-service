from __future__ import annotations

from hashlib import sha256

import pytest

from kuka_tool_service.parser import SourceValidationError
from kuka_tool_service.transforms import MetadataRequest, build_annotated_source

from conftest import SAMPLE_LINES


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
