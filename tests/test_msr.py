import json

import pytest

from sensos_core.msr import Calibration, evaluate_manifold_shift, load_calibration


@pytest.fixture
def calib() -> Calibration:
    return Calibration(
        model_build_id="micro-llm-v0.4-test",
        measured_at="2026-09-05T00:00:00Z",
        noise_floor_lower=5.93,
        noise_floor_upper=10.98,
        background_mean=8.50,
        sample_config={"points": 128, "dims": 256},
    )


def test_uncalibrated_when_calib_is_none():
    assert evaluate_manifold_shift(8.5, None) == "UNCALIBRATED"


def test_uncalibrated_regardless_of_d_manifold_value():
    # UNCALIBRATED must not depend on d_manifold at all — a missing
    # calibration file must never let a value "accidentally" look
    # meaningful.
    for d in (-100.0, 0.0, 5.93, 8.5, 10.98, 1e9):
        assert evaluate_manifold_shift(d, None) == "UNCALIBRATED"


def test_stagnant_below_noise_floor_lower(calib):
    assert evaluate_manifold_shift(5.0, calib) == "STAGNANT"


def test_boundary_at_noise_floor_lower_is_internal_not_stagnant(calib):
    # SPEC-MSR-001_v2 §3.2: strictly < lower is STAGNANT, so the boundary
    # value itself falls into NOISE_FLOOR_INTERNAL.
    assert evaluate_manifold_shift(calib.noise_floor_lower, calib) == "NOISE_FLOOR_INTERNAL"


def test_noise_floor_internal_within_range(calib):
    assert evaluate_manifold_shift(8.5, calib) == "NOISE_FLOOR_INTERNAL"


def test_boundary_at_noise_floor_upper_is_internal(calib):
    assert evaluate_manifold_shift(calib.noise_floor_upper, calib) == "NOISE_FLOOR_INTERNAL"


def test_structural_shift_above_noise_floor_upper(calib):
    assert evaluate_manifold_shift(15.0, calib) == "STRUCTURAL_SHIFT_DETECTED"


def test_load_calibration_returns_none_when_file_missing(tmp_path):
    assert load_calibration(tmp_path, "some-build-that-was-never-measured") is None


def test_load_calibration_never_applies_a_different_builds_file(tmp_path):
    """A calibration file measured for one build must not be picked up for
    a different model_build_id, even if present in the same data_dir —
    SPEC-MSR-001_v2 §3.1's whole point is that MAC001's v0.1 numbers must
    not silently apply to v0.4."""
    calib_dir = tmp_path / "calibration"
    calib_dir.mkdir()
    (calib_dir / "micro-llm-v0.1-mac001.json").write_text(
        json.dumps(
            {
                "model_build_id": "micro-llm-v0.1-mac001",
                "measured_at": "2026-08-01T00:00:00Z",
                "noise_floor_lower": 5.93,
                "noise_floor_upper": 10.98,
                "background_mean": 8.50,
                "sample_config": {"points": 128, "dims": 256},
            }
        )
    )
    assert load_calibration(tmp_path, "micro-llm-v0.4-different-build") is None


def test_load_calibration_reads_matching_build_file(tmp_path):
    calib_dir = tmp_path / "calibration"
    calib_dir.mkdir()
    (calib_dir / "micro-llm-v0.4-test.json").write_text(
        json.dumps(
            {
                "model_build_id": "micro-llm-v0.4-test",
                "measured_at": "2026-09-05T00:00:00Z",
                "noise_floor_lower": 4.0,
                "noise_floor_upper": 9.0,
                "background_mean": 6.5,
                "sample_config": {"points": 128, "dims": 256},
            }
        )
    )
    loaded = load_calibration(tmp_path, "micro-llm-v0.4-test")
    assert loaded is not None
    assert loaded.noise_floor_lower == 4.0
    assert loaded.noise_floor_upper == 9.0
    assert evaluate_manifold_shift(6.5, loaded) == "NOISE_FLOOR_INTERNAL"
