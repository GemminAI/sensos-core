"""Phase 2 closing assertion: msr.abi.StabilizedTrajectory (re-exported as
sensos_core.trajectory_hash.StabilizedTrajectory) already satisfies
categorical-lift-engine's cle.abi.inputs.StabilizedTrajectoryLike Protocol
structurally, with no conversion code. Verified interactively this session
(`isinstance` check passes; CLEEngine.lift()/CategoricalLiftEngine.lift()
both type as `trajectory: StabilizedTrajectoryLike` directly) -- this test
pins that fact so a future dependency bump in either repo cannot silently
break it without a test failure.

No new adapter is introduced here. If this test ever needs one to pass,
that is itself the signal that MSR and CLE's ABIs have drifted apart.
"""

from cle.abi.inputs import MeaningStateLike, StabilizedTrajectoryLike

from sensos_core.trajectory_hash import MeaningState, StabilizedTrajectory


def _make_trajectory() -> StabilizedTrajectory:
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
        dwell_steps=3,
        dwell_seconds=1.5,
        provenance=("obs-1",),
    )


def test_msr_meaning_state_satisfies_cle_protocol():
    trajectory = _make_trajectory()
    assert isinstance(trajectory.states[0], MeaningStateLike)


def test_msr_stabilized_trajectory_satisfies_cle_protocol_with_no_adapter():
    trajectory = _make_trajectory()
    assert isinstance(trajectory, StabilizedTrajectoryLike)
