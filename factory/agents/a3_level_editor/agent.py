"""A3 Level Editor: a Tool Runner loop that patches a script until the code gates pass.

One A3 turn is one editing round: the model receives the current LevelReport and script,
edits through tools, and stops; then the profiler re-checks. After `max_turns` rounds
without a pass, the episode is ESCALATED and the last LevelReport is kept.

With a RevisionRequest (reviewers rejected the script), the loop runs at least one turn even
when the gates pass, so the model can act on the reviewers' notes; a revision that changes
nothing is ESCALATED.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


from pydantic import BaseModel, ConfigDict, Field, ValidationError

from factory.adapters.llm.base import LLMError, LLMProvider, ToolSpec
from factory.agents.drafts import to_draft_dict, translation_languages
from factory.agents.prefix import system_blocks
from factory.artifacts import ADAPTER_SOURCES, station_version
from factory.config import ResolvedConfig
from factory.contracts import CostEntry, EpisodeSpec, LevelReport, Line, RevisionRequest, Script, VocabItem
from factory.tools.language_pack import LanguagePack
from factory.tools.profiler import format_report, profile
from factory.tools.rate_estimator import estimate_duration_min, speech_units

STATION = "a3_level_editor"
HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompt.md"
Status = Literal["PASSED", "ESCALATED"]


def version(identity: str) -> str:
    return station_version(identity, PROMPT_PATH, Path(__file__).resolve(), HERE.parent / "prefix.py",
                           HERE.parent / "drafts.py", *ADAPTER_SOURCES)


class EditError(ValueError):
    pass


class EditSession:
    """The script being edited, plus the edit operations the tools expose."""

    def __init__(self, script: Script, spec: EpisodeSpec, config: ResolvedConfig, pack: LanguagePack):
        self.script = script.model_copy(deep=True)
        self.spec, self.config, self.pack = spec, config, pack
        self.translations = translation_languages(config.pack.code, config.channel.support_languages)
        self.edits = 0

    def report(self) -> LevelReport:
        return profile(self.script, self.spec, self.config, self.pack)

    def _locate(self, line_id: str) -> tuple[list[Line], int, str]:
        for segment in self.script.segments:
            for index, line in enumerate(segment.lines):
                if line.id == line_id:
                    return segment.lines, index, segment.type
        raise EditError(f"no line with id {line_id}")

    def _dialogue_lines(self) -> list[Line]:
        return [line for s in self.script.segments if s.type == "dialogue" for line in s.lines]

    def _editable(self, line_id: str) -> tuple[list[Line], int, str]:
        """Locate a line A3 may change directly. Replay lines are rebuilt from the dialogue."""
        lines, index, seg_type = self._locate(line_id)
        if seg_type == "replay":
            dialogue = self._dialogue_lines()
            hint = f"edit the dialogue line {dialogue[index].id} instead" if index < len(dialogue) else "edit the dialogue"
            raise EditError(f"{line_id} is a replay line; {hint}, and the replay is rebuilt from it")
        return lines, index, seg_type

    def sync_replay(self) -> str:
        """Rebuild the replay from the dialogue, keeping the replay's own pauses where it has them."""
        replay = next((s for s in self.script.segments if s.type == "replay"), None)
        if replay is None:
            return "no replay segment"
        old_pauses = [line.pause_after_ms for line in replay.lines]
        replay.lines = [
            line.model_copy(update={
                "id": f"{replay.id}l{i}",
                "pause_after_ms": old_pauses[i - 1] if i <= len(old_pauses) else 500,
                "visual_cue": None,
            })
            for i, line in enumerate(self._dialogue_lines(), start=1)
        ]
        return f"replay rebuilt from the dialogue ({len(replay.lines)} lines)"

    def _after_change(self, seg_type: str, message: str) -> str:
        self.edits += 1
        if seg_type == "dialogue":
            message += "; " + self.sync_replay()
        return message

    def _check_translations(self, translations: dict[str, str]) -> dict[str, str]:
        missing = [lang for lang in self.translations if not translations.get(lang, "").strip()]
        if missing:
            raise EditError(f"translations missing for: {', '.join(missing)}")
        return {lang: translations[lang] for lang in self.translations}

    def _new_id(self, after_id: str) -> str:
        existing = {x.id for s in self.script.segments for x in [*s.lines, *s.items]}
        n = 1
        while f"{after_id}x{n}" in existing:
            n += 1
        return f"{after_id}x{n}"

    def edit_line(self, line_id: str, text: str, translations: dict[str, str]) -> str:
        translations = self._check_translations(translations)
        lines, index, seg_type = self._editable(line_id)
        lines[index] = lines[index].model_copy(update={"text": text, "translation": translations})
        return self._after_change(seg_type, f"edited {line_id}")

    def insert_line(
        self, after_line_id: str, speaker: str, text: str, translations: dict[str, str], pause_after_ms: int,
    ) -> str:
        translations = self._check_translations(translations)
        cast = {member.id for member in self.config.channel.cast}
        if speaker not in cast:
            raise EditError(f"unknown speaker {speaker}; use one of {sorted(cast)}")
        lines, index, seg_type = self._editable(after_line_id)
        new = Line(id=self._new_id(after_line_id), speaker=speaker, text=text,
                   translation=translations, pause_after_ms=max(0, pause_after_ms))
        lines.insert(index + 1, new)
        return self._after_change(seg_type, f"inserted {new.id}")

    def delete_line(self, line_id: str) -> str:
        lines, index, seg_type = self._editable(line_id)
        if len(lines) == 1:
            raise EditError("cannot delete the only line of a segment")
        del lines[index]
        return self._after_change(seg_type, f"deleted {line_id}")

    def set_pause(self, line_id: str, pause_after_ms: int) -> str:
        lines, index, _ = self._locate(line_id)  # replay pauses are the replay's own
        lines[index] = lines[index].model_copy(update={"pause_after_ms": max(0, pause_after_ms)})
        self.edits += 1
        return f"set pause after {line_id} to {pause_after_ms} ms"

    def edit_quiz_item(
        self, item_id: str, question: str, options: list[str], answer_index: int, translations: dict[str, str],
    ) -> str:
        translations = self._check_translations(translations)
        for segment in self.script.segments:
            for index, item in enumerate(segment.items):
                if item.id == item_id:
                    if len(options) < 2 or not 0 <= answer_index < len(options):
                        raise EditError("need at least 2 options and an answer_index inside them")
                    segment.items[index] = item.model_copy(update={
                        "question": question, "options": options, "answer_index": answer_index,
                        "translation": translations,
                    })
                    self.edits += 1
                    return f"edited quiz item {item_id}"
        raise EditError(f"no quiz item with id {item_id}")

    def validate(self) -> None:
        """Re-check the edited script against the Script contract."""
        self.script = Script.model_validate(self.script.model_dump())

    def set_vocab_gloss(self, word: str, glosses: dict[str, str]) -> str:
        support = self.config.channel.support_languages
        missing = [lang for lang in support if not glosses.get(lang, "").strip()]
        if missing:
            raise EditError(f"glosses missing for: {', '.join(missing)}")
        is_target = word.lower() in {w.lower() for w in self.spec.target_words}
        for item in self.script.vocab:
            if item.word.lower() == word.lower():
                item.gloss = {lang: glosses[lang] for lang in support}
                item.is_target = item.is_target or is_target
                break
        else:
            self.script.vocab.append(VocabItem(word=word, gloss={lang: glosses[lang] for lang in support},
                                               is_target=is_target))
        self.edits += 1
        return f"set glosses for {word}"

    def profile_summary(self) -> str:
        report = self.report()
        text = {line.id: line.text for line in self.script.iter_lines()}
        text |= {item.id: " / ".join([item.question, *item.options])
                 for segment in self.script.segments for item in segment.items}
        flagged = sorted({lid for f in report.gate_failures for lid in f.line_ids})
        return json.dumps({
            "passed": report.passed,
            "gate_failures": [f.model_dump() for f in report.gate_failures],
            "off_level_words": [f"{t.surface} ({t.level or 'not in list'}) in {t.line_id}" for t in report.off_level_tokens],
            "target_word_counts": report.target_word_counts,
            "sentence_length": report.sentence_length.model_dump(),
            "estimated_duration_min": report.estimated_duration_min,
            "flagged_lines": {lid: text.get(lid, "") for lid in flagged},
        }, ensure_ascii=False)

    def rate_summary(self) -> str:
        band = self.config.band
        return json.dumps({
            "spoken_words": speech_units(self.script, self.pack),
            "estimated_duration_min": estimate_duration_min(self.script, self.pack, band.rate),
            "pauses_total_ms": sum(line.pause_after_ms for line in self.script.iter_lines()),
            "spec_length_min": list(self.spec.length_min),
            "rate": band.rate.model_dump(),
        })


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class WordArgs(_Args):
    word: str = Field(description="The off-level word or its dictionary form.")


class EditLineArgs(_Args):
    line_id: str = Field(description='The id of the line to change, e.g. "s2l4".')
    text: str = Field(description="The new line text in the target language.")
    translations: dict[str, str] = Field(description='Translation per translation language, e.g. {"vi": "..."}.')


class InsertLineArgs(_Args):
    after_line_id: str = Field(description="The id of the line the new line follows.")
    speaker: str = Field(description="A cast id from the resolved configuration.")
    text: str = Field(description="The line text in the target language.")
    translations: dict[str, str] = Field(description='Translation per translation language, e.g. {"vi": "..."}.')
    pause_after_ms: int = Field(description="Pause after the line, in milliseconds.")


class LineIdArgs(_Args):
    line_id: str = Field(description="The id of the line.")


class PauseArgs(_Args):
    line_id: str = Field(description="The id of the line.")
    pause_after_ms: int = Field(description="The new pause in milliseconds.")


class QuizItemArgs(_Args):
    item_id: str = Field(description='The id of the quiz item, e.g. "s5q1".')
    question: str = Field(description="The new question in the target language.")
    options: list[str] = Field(description="The answer options in the target language, at least 2.")
    answer_index: int = Field(description="Zero-based index of the correct option.")
    translations: dict[str, str] = Field(description='Translation of the question per translation language.')


class GlossArgs(_Args):
    word: str = Field(description="The vocabulary word, exactly as in the spec for a target word.")
    glosses: dict[str, str] = Field(description='A gloss per support language, e.g. {"en": "...", "vi": "..."}.')


def make_tools(session: EditSession) -> list[ToolSpec]:
    level = session.config.level
    return [
        ToolSpec("lexical_profile", "Run the code gates on the current script and return the failures, "
                 "off-level words, target-word counts, sentence-length stats, duration and the text of flagged "
                 "lines.", NoArgs, lambda a: session.profile_summary()),
        ToolSpec("rate_estimate", "Return spoken words, total pauses and estimated duration against the spec "
                 "length.", NoArgs, lambda a: session.rate_summary()),
        ToolSpec("find_simpler_synonym", "List in-level synonyms for a word, most common first. Empty if none "
                 "are known.", WordArgs,
                 lambda a: json.dumps(session.pack.simpler_synonyms(a.word.lower(), level)[:10])),
        ToolSpec("edit_line", "Replace the text of one line. Editing a dialogue line rebuilds the replay from "
                 "the dialogue.", EditLineArgs, lambda a: session.edit_line(a.line_id, a.text, a.translations)),
        ToolSpec("insert_line", "Insert a new line after an existing line. In the dialogue, the replay is "
                 "rebuilt to match.", InsertLineArgs,
                 lambda a: session.insert_line(a.after_line_id, a.speaker, a.text, a.translations, a.pause_after_ms)),
        ToolSpec("delete_line", "Delete one line. In the dialogue, the replay is rebuilt to match.", LineIdArgs,
                 lambda a: session.delete_line(a.line_id)),
        ToolSpec("set_pause", "Change the pause after one line.", PauseArgs,
                 lambda a: session.set_pause(a.line_id, a.pause_after_ms)),
        ToolSpec("edit_quiz_item", "Replace an on-screen quiz item (question, options, answer).", QuizItemArgs,
                 lambda a: session.edit_quiz_item(a.item_id, a.question, a.options, a.answer_index, a.translations)),
        ToolSpec("sync_replay", "Rebuild the replay segment from the dialogue, line for line (fixes "
                 "replay_mismatch).", NoArgs, lambda a: session.sync_replay()),
        ToolSpec("set_vocab_gloss", "Add or replace the glosses of a vocabulary item.", GlossArgs,
                 lambda a: session.set_vocab_gloss(a.word, a.glosses)),
    ]


@dataclass
class LevelLoopResult:
    script: Script
    status: Status
    turns: int
    reports: list[LevelReport]
    costs: list[CostEntry] = field(default_factory=list)
    error: str | None = None  # why the loop stopped early, if it did
    reason: str | None = None  # why a finished loop is ESCALATED, when the gate report does not say


NO_CHANGES = "revision made no changes to the script"


def format_revision(revision: RevisionRequest) -> str:
    """The reviewers' notes and issues, verbatim, one block per reviewer."""
    blocks = []
    for note in revision.notes:
        lines = [f"- {note.reviewer} (gate {note.gate})" + (f": {note.notes}" if note.notes.strip() else "")]
        for issue in note.issues:
            fix = f"; suggested fix: {issue.suggested_fix}" if issue.suggested_fix else ""
            lines.append(f"  - [{issue.severity}] {issue.line_id or 'episode'} ({issue.category}): "
                         f"{issue.description}{fix}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def build_user(session: EditSession, report: LevelReport, revision: RevisionRequest | None = None) -> str:
    support = session.config.channel.support_languages
    draft = to_draft_dict(session.script, session.config.pack.code, support)
    parts = []
    if revision is not None:
        parts.append(f"Reviewer feedback (rejected by {revision.rejected_by}, revision {revision.round}):\n"
                     f"{format_revision(revision)}")
        gates = "The script passes every code gate; keep it that way." if report.passed else \
            f"The script also failed these gates.\n\n{format_report(report)}"
        parts.append(gates)
    else:
        parts.append(f"The script failed these gates.\n\n{format_report(report)}")
    parts += [f"Episode Spec:\n{session.spec.model_dump_json()}",
              f"Current script:\n{json.dumps(draft, ensure_ascii=False)}"]
    return "\n\n".join(parts)


def level_loop(
    script: Script, spec: EpisodeSpec, config: ResolvedConfig, pack: LanguagePack, llm: LLMProvider,
    max_turns: int = 4, revision: RevisionRequest | None = None,
) -> LevelLoopResult:
    session = EditSession(script, spec, config, pack)
    system = system_blocks(PROMPT_PATH.read_text(encoding="utf-8"), config, pack)
    tools = make_tools(session)
    reports = [session.report()]
    costs: list[CostEntry] = []
    turns, error = 0, None
    while (not reports[-1].passed or (revision is not None and turns == 0)) and turns < max_turns:
        turns += 1
        try:
            costs += llm.tool_loop(
                station=STATION, system=system, user=build_user(session, reports[-1], revision), tools=tools,
            )
            session.validate()
        except LLMError as exc:
            costs += exc.costs
            error = str(exc)
        except ValidationError as exc:
            error = f"edited script broke the Script contract: {exc}"
        reports.append(session.report())
        if error:
            break
    # A failing gate is the better explanation, so only an unchanged script that passes is NO_CHANGES.
    unchanged = revision is not None and not error and reports[-1].passed and session.script == script
    reason = NO_CHANGES if unchanged else None
    status: Status = "PASSED" if reports[-1].passed and not error and not reason else "ESCALATED"
    return LevelLoopResult(script=session.script, status=status, turns=turns, reports=reports,
                           costs=costs, error=error, reason=reason)
