"""Artifact contracts. Each model is the JSON Schema of one artifact type."""

from factory.contracts.cost_ledger import CostEntry, CostLedger
from factory.contracts.episode_spec import EpisodeSpec, RateTarget
from factory.contracts.gate_decision import GateDecision
from factory.contracts.level_report import GateFailure, LevelReport, OffLevelToken
from factory.contracts.qa_report import QAIssue, QAReport
from factory.contracts.script import Line, QuizItem, Script, Segment, VocabItem

CONTRACTS = {
    "episode_spec": EpisodeSpec,
    "script": Script,
    "level_report": LevelReport,
    "qa_report": QAReport,
    "gate_decision": GateDecision,
    "cost_ledger": CostLedger,
}

SCHEMA_VERSIONS = {name: model.model_fields["schema_version"].default for name, model in CONTRACTS.items()}

__all__ = [
    "CONTRACTS",
    "SCHEMA_VERSIONS",
    "CostEntry",
    "CostLedger",
    "EpisodeSpec",
    "GateDecision",
    "GateFailure",
    "LevelReport",
    "Line",
    "OffLevelToken",
    "QAIssue",
    "QAReport",
    "QuizItem",
    "RateTarget",
    "Script",
    "Segment",
    "VocabItem",
]
