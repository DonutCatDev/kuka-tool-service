from __future__ import annotations

from pathlib import Path

import pytest

from kuka_tool_service.merger import build_merged_source
from kuka_tool_service.parser import SourceValidationError, inspect_source


FIXTURES = Path(__file__).parent / "fixtures" / "merge"


def sources() -> tuple[bytes, bytes]:
    return (FIXTURES / "primary.src").read_bytes(), (FIXTURES / "secondary.src").read_bytes()


def test_merge_matches_golden_bytes_and_preserves_provenance() -> None:
    primary, secondary = sources()
    artifact = build_merged_source(primary, secondary, "Primary path.src", "secondary.src")

    assert artifact.data == (FIXTURES / "expected.src").read_bytes()
    assert artifact.filename == "Primary_path_merged.src"
    assert artifact.primary_block_count == 2
    assert artifact.secondary_block_count == 2
    assert len({artifact.primary_sha256, artifact.secondary_sha256, artifact.output_sha256}) == 3
    assert inspect_source(artifact.data).extrusion_layer_count == 4


def test_merge_rejects_duplicate_inputs() -> None:
    primary, _ = sources()
    with pytest.raises(SourceValidationError, match="must be different"):
        build_merged_source(primary, primary, "primary.src", "secondary.src")


def test_merge_rejects_misaligned_z() -> None:
    primary, secondary = sources()
    secondary = secondary.replace(b"Z 5}\n;travel start", b"Z 6}\n;travel start", 1)
    with pytest.raises(SourceValidationError, match="differs in Z height"):
        build_merged_source(primary, secondary, "primary.src", "secondary.src")


def test_merge_rejects_incompatible_scaffolding() -> None:
    primary, secondary = sources()
    secondary = secondary.replace(b"; shared shutdown", b"; different shutdown")
    with pytest.raises(SourceValidationError, match="tails are not structurally compatible"):
        build_merged_source(primary, secondary, "primary.src", "secondary.src")


def test_merge_rejects_different_block_counts() -> None:
    primary, secondary = sources()
    second_block = secondary.index(b"$VEL.CP = 0.110000\nLIN {X 101, Y 0, Z 10}")
    tail = secondary.index(b"$VEL.CP = 0.110000\nLIN {X 100, Y 0, Z 20}")
    secondary = secondary[:second_block] + secondary[tail:]
    with pytest.raises(SourceValidationError, match="same number of path blocks"):
        build_merged_source(primary, secondary, "primary.src", "secondary.src")
