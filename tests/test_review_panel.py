"""Panel parsing and decision rules, against fixture responses in the model's output shape. No network."""

import pytest
from pydantic import ValidationError

from factory.agents.review_panel.agent import PERSONAS, PanelVerdict, build_user, enforce_rules, to_review, version
from tests.conftest import FIXTURES


def verdict(name: str) -> PanelVerdict:
    return PanelVerdict.model_validate_json((FIXTURES / "panel" / name).read_text(encoding="utf-8"))


def test_major_issue_turns_approve_into_edit_and_approve():
    review = to_review(verdict("examiner_edit.json"), "examiner", "en-A2-x00")
    assert review.decision.decision == "edit-and-approve"
    assert review.approved
    assert "decision changed from approve" in review.decision.notes
    assert review.decision.gate == 1 and review.decision.user == "examiner"
    assert review.qa_report.rubric_scores["grammar_point_teaching"] == 3
    assert review.level_fit_verdict == "at"
    assert "s1l3:" in review.decision.diff


def test_critical_issue_forces_reject():
    review = to_review(verdict("learner_critical.json"), "learner", "en-A2-x00")
    assert review.qa_report.has_critical
    assert review.decision.decision == "reject"
    assert not review.approved


def test_clean_approve_stays_approve():
    clean = verdict("examiner_edit.json").model_copy(update={"issues": []})
    assert enforce_rules(clean) == "approve"


def test_reject_is_never_upgraded():
    rejected = verdict("examiner_edit.json").model_copy(update={"issues": [], "decision": "reject"})
    assert enforce_rules(rejected) == "reject"


def test_out_of_range_score_is_rejected():
    raw = (FIXTURES / "panel" / "examiner_edit.json").read_text(encoding="utf-8").replace('"score": 5', '"score": 7', 1)
    with pytest.raises(ValidationError):
        PanelVerdict.model_validate_json(raw)


def test_reviewer_sees_only_spec_and_script(spec, script):
    prompt = build_user(spec, script)
    assert "s1l1" in prompt and spec.grammar_point in prompt
    assert "config_hash" not in prompt and "budget_usd" not in prompt


def test_personas_have_distinct_versions():
    versions = {version(p, "claude-opus-5-5") for p in PERSONAS}
    assert len(versions) == 2
