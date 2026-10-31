"""The script steps `factory script`, `factory review` and the orchestrator share, on the en pack.

A fake LLM serves a stored spike script as the A2 draft, so no network is needed.
"""

import json
from collections import Counter

import pytest

from factory.adapters.llm.fake import FakeLLMProvider
from factory.agents.drafts import to_draft_dict
from factory.artifacts import ArtifactStore, Producer
from factory.config import REPO_ROOT, resolve
from factory.contracts import EpisodeSpec, Script
from factory.orchestrator.stations import draft_script, level_script, review_script
from factory.tools.language_pack import load_pack
from tests.conftest import FIXTURES

EVALS = REPO_ROOT / "evals" / "en" / "adult"


class CountingLLM(FakeLLMProvider):
    def __init__(self, fixtures_dir):
        super().__init__(fixtures_dir)
        self.calls: Counter[str] = Counter()

    def structured(self, *, station, **kwargs):
        self.calls[station] += 1
        return super().structured(station=station, **kwargs)


@pytest.fixture(scope="module")
def episode(tmp_path_factory):
    spec = EpisodeSpec.model_validate_json((EVALS / "specs" / "en-A2-x01.json").read_text(encoding="utf-8"))
    config = resolve(spec.channel, spec.level)
    script = Script.model_validate_json((EVALS / "scripts" / "en-A2-x01.json").read_text(encoding="utf-8"))
    fixtures = tmp_path_factory.mktemp("llm")
    (fixtures / "a2_scriptwriter.json").write_text(json.dumps(
        to_draft_dict(script, config.pack.code, config.channel.support_languages)))
    for persona in ("examiner", "learner"):
        (fixtures / f"review_{persona}.json").write_text((FIXTURES / "panel" / "examiner_edit.json").read_text())
    return spec, config, load_pack("en"), script, fixtures


def test_draft_level_and_review_share_one_store(tmp_path, episode):
    spec, config, pack, script, fixtures = episode
    llm = CountingLLM(fixtures)
    out = Producer(ArtifactStore(tmp_path), spec.channel, spec.episode_id)
    draft = draft_script(out, spec, config, pack, llm)
    assert draft == script
    leveled = level_script(out, draft, spec, config, pack, llm)
    assert leveled.status == "PASSED" and leveled.turns == 0 and leveled.report.passed
    reviews = review_script(out, spec, leveled.script, {"examiner": llm, "learner": llm})
    assert [r.decision.decision for r in reviews] == ["edit-and-approve", "edit-and-approve"]
    assert [p.envelope["station"] for p in out.produced] == [
        "a2_scriptwriter", "a3_level_editor", "level_report", "review_examiner", "review_learner"]

    again = Producer(ArtifactStore(tmp_path), spec.channel, spec.episode_id)
    draft_script(again, spec, config, pack, llm)
    level_script(again, draft, spec, config, pack, llm)
    review_script(again, spec, leveled.script, {"examiner": llm, "learner": llm})
    assert all(p.reused for p in again.produced)
    assert llm.calls == {"a2_scriptwriter": 1, "review_examiner": 1, "review_learner": 1}

    fresh = Producer(ArtifactStore(tmp_path), spec.channel, spec.episode_id, fresh=True)
    draft_script(fresh, spec, config, pack, llm)
    assert llm.calls["a2_scriptwriter"] == 2
