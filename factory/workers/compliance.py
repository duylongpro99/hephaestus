"""A11 Compliance, code checks only: platform flags and metadata limits (architecture §3)."""

from factory.config import ResolvedConfig
from factory.contracts import PublishPackage, QAReport

REVIEWER = "a11_compliance"
TITLE_MAX, DESCRIPTION_MAX = 100, 5000  # YouTube's limits


def check(package: PublishPackage, config: ResolvedConfig) -> QAReport:
    failures = []
    if package.made_for_kids != config.audience.made_for_kids:
        failures.append(f"made_for_kids is {package.made_for_kids}, but the {config.audience.profile} "
                        f"audience profile says {config.audience.made_for_kids}")
    if not package.contains_synthetic_media:
        failures.append("contains_synthetic_media must be set: the voices and images are generated")
    for lang in config.channel.support_languages:
        title, description = package.title.get(lang, ""), package.description.get(lang, "")
        if not title.strip() or not description.strip():
            failures.append(f"no title or description in {lang}")
        if len(title) > TITLE_MAX:
            failures.append(f"{lang} title is {len(title)} characters (max {TITLE_MAX})")
        if len(description) > DESCRIPTION_MAX:
            failures.append(f"{lang} description is {len(description)} characters (max {DESCRIPTION_MAX})")
    summary = "flags and metadata pass" if not failures else f"{len(failures)} compliance failure(s)"
    return QAReport(episode_id=package.episode_id, reviewer=REVIEWER, hard_gate_failures=failures, summary=summary)
