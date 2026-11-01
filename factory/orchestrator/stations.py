"""One station per episode transition from SPEC to SCHEDULED (architecture §5).

Stations read earlier artifacts by pointer, produce their own through the content-addressed
store and report an outcome; the runner records the rest. The script steps at the top are
shared with the `factory script` and `factory review` commands, so both run one code path.
"""

import hashlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from factory.adapters.costs import ledger_entries
from factory.adapters.image import base as image_base
from factory.adapters.image.base import ImageGenerator
from factory.adapters.llm.base import LLMError, LLMProvider
from factory.adapters.publishing.base import VideoPublisher
from factory.adapters.speech import base as speech_base
from factory.adapters.speech.base import SpeechSynthesizer
from factory.adapters.video.base import VideoRenderer
from factory.agents.a2_scriptwriter import agent as a2
from factory.agents.a3_level_editor import agent as a3
from factory.agents.a3_level_editor.agent import LevelLoopResult
from factory.agents.prefix import wordlist_block
from factory.agents.review_panel import agent as panel
from factory.artifacts import Built, Producer, sha256_text, station_version
from factory.config import ResolvedConfig, pack_module
from factory.contracts import (
    AudioManifest, CostEntry, Enrichment, EpisodeSpec, GateDecision, LevelReport, PublishPackage, PublishReceipt, QAReport, RenderedVideo,
    RenderProps, Script, ShotList, VoiceDirectives,
)
from factory.orchestrator import repo
from factory.orchestrator.runner import StationContext, StationResult
from factory.tools import enrichment
from factory.tools.language_pack import LanguagePack
from factory.tools.profiler import profile
from factory.workers import compliance, composer, packaging, publisher, tech_checks, visuals, voice

CODE = "code"  # the "model" of a station that calls no model


def source(obj) -> Path:
    return Path(inspect.getfile(obj if inspect.ismodule(obj) else type(obj))).resolve()


# Shared script steps ------------------------------------------------------------------------


def wordlist_hash(config: ResolvedConfig, pack: LanguagePack) -> str:
    """The wordlist comes from pack data that neither the config hash nor the code hash covers."""
    return sha256_text(wordlist_block(config, pack))


def draft_script(out: Producer, spec: EpisodeSpec, config: ResolvedConfig, pack: LanguagePack,
                 writer: LLMProvider) -> Script:
    """A2: EpisodeSpec -> Script, reused when the store holds a draft for the same inputs."""
    inputs = [spec, config.config_hash, wordlist_hash(config, pack)]
    return out.produce(a2.STATION, a2.version(writer.identity), inputs, Script,
                       lambda media: Built(*a2.write_script(spec, config, pack, writer)))


class LevelLoopFailed(LLMError):
    """The A3 loop stopped on an error, not on its turn budget; its result is not stored."""

    def __init__(self, result: LevelLoopResult):
        super().__init__(f"{a3.STATION}: {result.error}", result.costs)
        self.result = result


@dataclass
class Leveled:
    script: Script
    status: str  # PASSED or ESCALATED
    turns: int
    first_report: LevelReport
    report: LevelReport


def level_script(out: Producer, draft: Script, spec: EpisodeSpec, config: ResolvedConfig, pack: LanguagePack,
                 editor: LLMProvider, max_turns: int = 4) -> Leveled:
    """A3 + profiler: patch the draft until the code gates pass or the turns run out."""
    version = a3.version(editor.identity)
    inputs = [draft, spec, config.config_hash, wordlist_hash(config, pack), max_turns]

    def build(media: Path) -> Built:
        result = a3.level_loop(draft, spec, config, pack, editor, max_turns=max_turns)
        if result.error:
            raise LevelLoopFailed(result)
        return Built(result.script, result.costs, {"status": result.status, "turns": result.turns})

    script = out.produce(a3.STATION, version, inputs, Script, build)
    envelope = out.last.envelope
    report = out.produce("level_report", version, inputs, LevelReport,
                         lambda media: Built(profile(script, spec, config, pack), extra={
                             "status": envelope["status"], "turns": envelope["turns"]}))
    return Leveled(script=script, status=envelope["status"], turns=envelope["turns"],
                   first_report=profile(draft, spec, config, pack), report=report)


def review_script(out: Producer, spec: EpisodeSpec, script: Script,
                  reviewers: dict[str, LLMProvider]) -> list[panel.Review]:
    """The two-persona panel, one independent call each, reused for the same spec and script."""
    reviews = []
    for persona, llm in reviewers.items():
        def build(media: Path, persona=persona, llm=llm) -> Built:
            r = panel.review(persona, spec, script, llm)
            return Built(r.qa_report, r.costs, {"gate_decision": r.decision.model_dump(mode="json"),
                                                 "level_fit_verdict": r.level_fit_verdict})

        qa_report = out.produce(panel.station(persona), panel.version(persona, llm.identity), [spec, script],
                                QAReport, build)
        envelope = out.last.envelope
        reviews.append(panel.Review(
            persona=persona, qa_report=qa_report,
            decision=GateDecision.model_validate(envelope["gate_decision"]),
            level_fit_verdict=envelope["level_fit_verdict"],
            costs=[CostEntry.model_validate(c) for c in envelope.get("cost", [])],  # as recorded, even when reused
        ))
    return reviews


# Stations ------------------------------------------------------------------------------------


@dataclass
class Vendors:
    """The providers a run uses: LLMs by config/llm.yaml role, media by config/media.yaml purpose."""

    llm: Callable[[str], LLMProvider]
    speech: Callable[[LanguagePack], SpeechSynthesizer]
    images: ImageGenerator
    video: Callable[[LanguagePack], VideoRenderer]
    publisher: VideoPublisher


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def failed(report: QAReport) -> StationResult:
    if report.hard_gate_failures:
        return StationResult("escalate", "; ".join(report.hard_gate_failures))
    return StationResult()


class Stations:
    def __init__(self, vendors: Vendors):
        self.v = vendors

    def registry(self) -> dict[str, Callable[[StationContext], StationResult]]:
        return {
            "a2_scriptwriter": self.scriptwriter,
            "a3_level_editor": self.level_editor,
            "c2_enrichment": self.enrich,
            "review_panel": self.review_panel,
            "voice": self.voice_lines,
            "visuals": self.draw_visuals,
            "render": self.render_video,
            "c9_tech_checks": self.check_video,
            "a9_packager": self.package,
            "a11_compliance": self.check_compliance,
            "c10_upload": self.upload,
            "c10_schedule": self.schedule,
        }

    def scriptwriter(self, ctx: StationContext) -> StationResult:
        draft_script(ctx, ctx.spec, ctx.config, ctx.pack, self.v.llm(a2.STATION))
        return StationResult()

    def level_editor(self, ctx: StationContext) -> StationResult:
        draft = ctx.read(a2.STATION, Script)
        leveled = level_script(ctx, draft, ctx.spec, ctx.config, ctx.pack, self.v.llm(a3.STATION))
        if leveled.status != "PASSED":
            gates = ", ".join(f.gate for f in leveled.report.gate_failures)
            return StationResult("escalate", f"level gates still failing after {leveled.turns} A3 turn(s): {gates}")
        return StationResult()

    def enrich(self, ctx: StationContext) -> StationResult:
        script = ctx.read(a3.STATION, Script)
        version = station_version(CODE, source(enrichment), source(pack_module(ctx.config.pack.code)))
        ctx.produce("c2_enrichment", version, [script, ctx.config.level], Enrichment,
                    lambda media: Built(enrichment.enrich(script, ctx.pack, ctx.config.level)))
        return StationResult()

    def review_panel(self, ctx: StationContext) -> StationResult:
        script = ctx.read(a3.STATION, Script)
        reviews = review_script(ctx, ctx.spec, script, {p: self.v.llm(panel.station(p)) for p in panel.PERSONAS})
        decisions = [r.decision for r in reviews]
        rejected = [r for r in reviews if not r.approved]
        if rejected:
            why = "; ".join(f"{r.persona}: {r.qa_report.summary}" for r in rejected)
            return StationResult("reject", f"panel rejected the script ({why})", decisions)
        return StationResult(gate_decisions=decisions)

    def voice_lines(self, ctx: StationContext) -> StationResult:
        script = ctx.read(a3.STATION, Script)
        directives = ctx.produce("a6_voice_director", station_version(CODE, source(voice)),
                                 [script, ctx.config.config_hash], VoiceDirectives,
                                 lambda media: Built(voice.direct(script, ctx.config, ctx.pack)))
        speech = self.v.speech(ctx.pack)

        def build(media: Path) -> Built:
            manifest, charges = voice.voice(script, directives, ctx.pack, speech, media, ctx.store.uri)
            return Built(manifest, ledger_entries(voice.STATION, charges))

        ctx.produce("c5_audio", station_version(speech.identity, source(voice), source(speech_base), source(speech)), [script, directives],
                    AudioManifest, build)
        return StationResult()

    def draw_visuals(self, ctx: StationContext) -> StationResult:
        script, images = ctx.read(a3.STATION, Script), self.v.images
        def build(media: Path) -> Built:
            shots, charges = visuals.shoot(script, ctx.config, images, media, ctx.store.uri)
            return Built(shots, ledger_entries(visuals.STATION, charges))

        ctx.produce("a7_visual_director", station_version(images.identity, source(visuals), source(image_base),
                                                             source(images)),
                    [script, ctx.config.config_hash], ShotList, build)
        return StationResult()

    def render_video(self, ctx: StationContext) -> StationResult:
        script, audio = ctx.read(a3.STATION, Script), ctx.read("c5_audio", AudioManifest)
        shots = ctx.read("a7_visual_director", ShotList)
        props = ctx.produce("c7_composer", station_version(CODE, source(composer)), [script, audio, shots],
                            RenderProps, lambda media: Built(composer.compose(script, audio, shots)))

        renderer = self.v.video(ctx.pack)

        def build(media: Path) -> Built:
            path = renderer.render(props, ctx.store.resolve, media)
            return Built(RenderedVideo(episode_id=ctx.episode, uri=ctx.store.uri(path), sha256=file_sha256(path),
                                       size_bytes=path.stat().st_size, width=props.width, height=props.height,
                                       fps=props.fps))

        ctx.produce("c8_render", station_version(renderer.identity, source(renderer)), [props], RenderedVideo, build)
        return StationResult()

    def check_video(self, ctx: StationContext) -> StationResult:
        video, audio = ctx.read("c8_render", RenderedVideo), ctx.read("c5_audio", AudioManifest)
        report = ctx.produce(
            "c9_tech_checks", station_version(CODE, source(tech_checks)), [video, audio], QAReport,
            lambda media: Built(tech_checks.check(ctx.store.resolve(video.uri), audio, video.width, video.height)))
        return failed(report)

    def package(self, ctx: StationContext) -> StationResult:
        script, props = ctx.read(a3.STATION, Script), ctx.read("c7_composer", RenderProps)
        video, llm = ctx.read("c8_render", RenderedVideo), self.v.llm(packaging.STATION)

        def build(media: Path) -> Built:
            copy, costs = packaging.write_copy(ctx.spec, script, ctx.config, llm)
            return Built(packaging.package(ctx.spec, ctx.config, props, video.uri, copy), costs)

        ctx.produce(packaging.STATION, packaging.version(llm.identity),
                    [ctx.spec, script, ctx.config.config_hash, props, video], PublishPackage, build)
        return StationResult()

    def check_compliance(self, ctx: StationContext) -> StationResult:
        package = ctx.read(packaging.STATION, PublishPackage)
        report = ctx.produce(compliance.REVIEWER, station_version(CODE, source(compliance)),
                             [package, ctx.config.config_hash], QAReport,
                             lambda media: Built(compliance.check(package, ctx.config)))
        return failed(report)

    def upload(self, ctx: StationContext) -> StationResult:
        package, video = ctx.read(packaging.STATION, PublishPackage), ctx.read("c8_render", RenderedVideo)
        pub = self.v.publisher
        existing = repo.get_receipt(ctx.conn, ctx.episode, pub.platform)
        receipt, uploaded = publisher.upload(existing, pub, ctx.store.resolve(video.uri), package, ctx.clock.now())
        if uploaded:  # stored at once, before anything else can fail, so a retry never uploads again
            with ctx.conn.transaction():
                repo.insert_receipt(ctx.conn, receipt)
        ctx.produce("c10_upload", station_version(pub.identity, source(publisher), source(pub)),
                    [package, video, receipt.external_id], PublishReceipt, lambda media: Built(receipt))
        return StationResult()

    def schedule(self, ctx: StationContext) -> StationResult:
        package, pub = ctx.read(packaging.STATION, PublishPackage), self.v.publisher
        receipt = repo.get_receipt(ctx.conn, ctx.episode, pub.platform)
        if receipt is None:
            return StationResult("fail", f"no {pub.platform} receipt for {ctx.episode}; it was never uploaded")
        publish_at = receipt.publish_at or publisher.publish_time(package, ctx.clock.now())
        scheduled = publisher.schedule(receipt, pub, publish_at, package)
        repo.schedule_receipt(ctx.conn, scheduled)
        ctx.produce("c10_schedule", station_version(pub.identity, source(publisher), source(pub)),
                    [receipt.external_id, publish_at.isoformat()], PublishReceipt, lambda media: Built(scheduled))
        return StationResult()
