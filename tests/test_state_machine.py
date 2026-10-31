"""The episode state machine as pure rules: no database."""

import pytest

from factory.orchestrator.states import (
    DONE, GATES, MAX_REJECTS, PIPELINE, STOPPED, IllegalTransition, State, after_attempt, backoff_s,
    check_transition, is_legal, over_budget,
)

FORWARD = [(src, step.next) for src, step in PIPELINE.items()]


def test_pipeline_runs_from_spec_to_scheduled():
    state, seen = State.SPEC, [State.SPEC]
    while state not in DONE:
        state = PIPELINE[state].next
        seen.append(state)
    assert seen[-1] == State.SCHEDULED
    assert set(seen) | STOPPED == set(State)


def test_gates_are_script_and_final_approval():
    assert GATES == {1: State.QA_OK, 2: State.COMPLIANT}
    assert PIPELINE[State.QA_OK].next == State.SCRIPT_APPROVED
    assert PIPELINE[State.COMPLIANT].next == State.FINAL_APPROVED


@pytest.mark.parametrize(("src", "dst"), FORWARD)
def test_forward_transitions_are_legal(src, dst):
    check_transition(src, dst)


@pytest.mark.parametrize("src", list(PIPELINE))
@pytest.mark.parametrize("dst", sorted(STOPPED))
def test_any_active_state_can_stop(src, dst):
    assert is_legal(src, dst)


@pytest.mark.parametrize("src", [State.ENRICHED, State.QA_OK])
def test_script_rejects_go_back_to_drafted(src):
    assert is_legal(src, State.DRAFTED)


def test_every_other_transition_is_illegal():
    legal = set(FORWARD) | {(s, d) for s in PIPELINE for d in STOPPED}
    legal |= {(State.ENRICHED, State.DRAFTED), (State.QA_OK, State.DRAFTED)}
    for src in State:
        for dst in State:
            if (src, dst) not in legal:
                assert not is_legal(src, dst), f"{src} -> {dst}"
                with pytest.raises(IllegalTransition):
                    check_transition(src, dst)


def test_finished_and_stopped_episodes_never_move():
    for src in DONE | STOPPED:
        assert not any(is_legal(src, dst) for dst in State)


def test_ok_moves_forward():
    move = after_attempt(State.SPEC, "ok", 1, 0)
    assert (move.job_status, move.to) == ("succeeded", State.DRAFTED)


def test_retries_back_off_then_escalate():
    cap = PIPELINE[State.VOICED].max_attempts
    moves = [after_attempt(State.VOICED, "retry", n, 0) for n in range(1, cap + 1)]
    assert [m.to for m in moves[:-1]] == [None] * (cap - 1)
    assert [m.backoff_s for m in moves[:-1]] == [backoff_s(n) for n in range(1, cap)]
    assert backoff_s(1) < backoff_s(2) < backoff_s(3)
    assert (moves[-1].job_status, moves[-1].to) == ("escalated", State.ESCALATED)


@pytest.mark.parametrize("outcome", ["escalate", "fail"])
def test_escalate_and_fail_go_to_the_human_queue(outcome):
    assert after_attempt(State.DRAFTED, outcome, 1, 0).to == State.ESCALATED


def test_panel_reject_rewrites_once_then_escalates():
    first = after_attempt(State.ENRICHED, "reject", 1, rejects=0)
    assert (first.job_status, first.to) == ("rejected", State.DRAFTED)
    again = after_attempt(State.ENRICHED, "reject", 1, rejects=MAX_REJECTS)
    assert (again.job_status, again.to) == ("escalated", State.ESCALATED)


def test_human_gate_reject_always_returns_to_drafted():
    assert after_attempt(State.QA_OK, "reject", 1, rejects=5).to == State.DRAFTED


def test_a_station_without_a_reject_path_cannot_reject():
    with pytest.raises(IllegalTransition):
        after_attempt(State.VOICED, "reject", 1, 0)


def test_budget_stop():
    assert not over_budget(1.0, 1.0)
    assert over_budget(1.0001, 1.0)


def test_final_gate_reject_escalates():
    move = after_attempt(State.COMPLIANT, "reject", 1, 0)
    assert (move.job_status, move.to) == ("rejected", State.ESCALATED)
