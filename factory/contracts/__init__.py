"""Artifact contracts. Each model is the JSON Schema of one artifact type."""

from factory.contracts.audio_manifest import AudioManifest, LineAudio, WordTiming
from factory.contracts.cost_ledger import CostEntry, CostLedger
from factory.contracts.enrichment import Enrichment, HintSpan, LineEnrichment, RubySpan
from factory.contracts.episode_spec import EpisodeSpec, RateTarget
from factory.contracts.gate_decision import GateDecision
from factory.contracts.level_report import GateFailure, LevelReport, OffLevelToken
from factory.contracts.publish_package import Chapter, PublishPackage
from factory.contracts.publish_receipt import PublishReceipt
from factory.contracts.qa_report import QAIssue, QAReport
from factory.contracts.render_props import Caption, RenderProps, Scene
from factory.contracts.rendered_video import RenderedVideo
from factory.contracts.revision_request import ReviewerNote, RevisionRequest
from factory.contracts.script import Line, QuizItem, Script, Segment, VocabItem
from factory.contracts.shot_list import Shot, ShotList
from factory.contracts.voice_directives import LineDirective, VoiceDirectives

CONTRACTS = {
    "episode_spec": EpisodeSpec,
    "script": Script,
    "level_report": LevelReport,
    "qa_report": QAReport,
    "gate_decision": GateDecision,
    "cost_ledger": CostLedger,
    "voice_directives": VoiceDirectives,
    "audio_manifest": AudioManifest,
    "shot_list": ShotList,
    "render_props": RenderProps,
    "publish_package": PublishPackage,
    "publish_receipt": PublishReceipt,
    "enrichment": Enrichment,
    "rendered_video": RenderedVideo,
    "revision_request": RevisionRequest,
}

SCHEMA_VERSIONS = {name: model.model_fields["schema_version"].default for name, model in CONTRACTS.items()}

__all__ = [
    "AudioManifest",
    "CONTRACTS",
    "Caption",
    "Chapter",
    "CostEntry",
    "CostLedger",
    "Enrichment",
    "EpisodeSpec",
    "GateDecision",
    "GateFailure",
    "HintSpan",
    "LevelReport",
    "Line",
    "LineAudio",
    "LineDirective",
    "LineEnrichment",
    "OffLevelToken",
    "PublishPackage",
    "PublishReceipt",
    "QAIssue",
    "QAReport",
    "QuizItem",
    "RateTarget",
    "RenderProps",
    "RenderedVideo",
    "ReviewerNote",
    "RevisionRequest",
    "RubySpan",
    "SCHEMA_VERSIONS",
    "Scene",
    "Script",
    "Segment",
    "Shot",
    "ShotList",
    "VocabItem",
    "VoiceDirectives",
    "WordTiming",
]
