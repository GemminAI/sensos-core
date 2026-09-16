from msr.abi import MeaningState, StabilizedTrajectory

from sensos_core.trajectory_hash import compute_trajectory_hash


def _make_trajectory(dwell_steps: int = 3) -> StabilizedTrajectory:
    state = MeaningState(
        frame_id="frame-1",
        step_index=0,
        time_s=0.0,
        theta=(1.0, 2.0),
        precision=((1.0, 0.0), (0.0, 1.0)),
        speed=0.1,
        potential=0.5,
        basin_id="basin-a",
        source_observation_id="obs-1",
    )
    return StabilizedTrajectory(
        trajectory_id="traj-1",
        frame_id="frame-1",
        basin_id="basin-a",
        states=(state,),
        centroid=(1.0, 2.0),
        covariance=((1.0, 0.0), (0.0, 1.0)),
        dwell_steps=dwell_steps,
        dwell_seconds=1.5,
        provenance=("obs-1",),
    )


def test_hash_is_deterministic_across_calls():
    trajectory = _make_trajectory()
    first = compute_trajectory_hash(trajectory)
    second = compute_trajectory_hash(trajectory)
    assert first == second


def test_hash_is_deterministic_across_equal_but_distinct_instances():
    a = _make_trajectory()
    b = _make_trajectory()
    assert a is not b
    assert compute_trajectory_hash(a) == compute_trajectory_hash(b)


def test_hash_changes_when_content_changes():
    a = _make_trajectory(dwell_steps=3)
    b = _make_trajectory(dwell_steps=4)
    assert compute_trajectory_hash(a) != compute_trajectory_hash(b)


def test_hash_is_a_64_char_hex_sha256_digest():
    digest = compute_trajectory_hash(_make_trajectory())
    assert len(digest) == 64
    int(digest, 16)  # raises ValueError if not valid hex
