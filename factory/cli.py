"""The `factory` command line."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import typer

from factory.adapters.llm.base import LLMError
from factory.config import REPO_ROOT, ResolvedConfig, resolve
from factory.contracts import CostEntry, CostLedger, EpisodeSpec, GateDecision, Script
from factory.tools.language_pack import load_pack
from factory.tools.profiler import format_report, profile

app = typer.Typer(no_args_is_help=True, add_completion=False)


def load_spec(path: Path) -> EpisodeSpec:
    return EpisodeSpec.model_validate_json(path.read_text(encoding="utf-8"))


def eval_dir(config: ResolvedConfig) -> Path:
    """Golden-eval home for a pack x audience pair (architecture §16)."""
    return REPO_ROOT / "evals" / config.pack.code / config.audience.profile


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fail(exc: LLMError):
    spent = sum(c.usd for c in exc.costs)
    typer.echo(f"error: {exc}" + (f" (already spent ${spent:.4f})" if exc.costs else ""), err=True)
    raise typer.Exit(1)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def append_attempt(path: Path, attempt: dict) -> None:
    """Keep every run of an episode; the last attempt is the current one."""
    record = read_json(path) if path.exists() else {"attempts": []}
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    record["attempts"].append(attempt)
    write_json(path, record)


def latest_attempt(path: Path) -> dict | None:
    return read_json(path)["attempts"][-1] if path.exists() else None


@app.command("profile")
def profile_cmd(
    script_path: Path = typer.Argument(..., exists=True, help="Script JSON"),
    spec_path: Path = typer.Option(..., "--spec", exists=True, help="EpisodeSpec JSON"),
    out: Path | None = typer.Option(None, help="LevelReport path (default: <script>.level_report.json)"),
):
    """Run the code gates on a script and write its LevelReport."""
    spec = load_spec(spec_path)
    script = Script.model_validate_json(script_path.read_text(encoding="utf-8"))
    config = resolve(spec.channel, spec.level)
    report = profile(script, spec, config, load_pack(config.pack.code))
    out = out or script_path.with_suffix(".level_report.json")
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(format_report(report))
    typer.echo(f"wrote {out}")
    raise typer.Exit(0 if report.passed else 1)


@app.command("script")
def script_cmd(
    spec_path: Path = typer.Argument(..., exists=True, help="EpisodeSpec JSON"),
    fresh: bool = typer.Option(False, help="Ignore a stored A2 draft and call the model again"),
    max_turns: int = typer.Option(4, help="Maximum A3 editing turns"),
):
    """Draft a script with A2, run the code gates, and patch it with A3 until it passes or escalates."""
    from factory.adapters.llm.router import provider_for
    from factory.agents.a2_scriptwriter import agent as a2
    from factory.agents.a3_level_editor import agent as a3
    from factory.artifacts import ArtifactStore

    started = time.monotonic()
    spec = load_spec(spec_path)
    config = resolve(spec.channel, spec.level)
    if spec.config_hash != config.config_hash:
        typer.echo(f"warning: spec config_hash {spec.config_hash[:19]} differs from the live config "
                   f"{config.config_hash[:19]}; using the live config")
    pack = load_pack(config.pack.code)
    try:
        writer, editor = provider_for(a2.STATION), provider_for(a3.STATION)
    except LLMError as exc:
        fail(exc)
    store = ArtifactStore()
    where = {"channel": spec.channel, "episode": spec.episode_id, "season": spec.season_id}
    ledger = CostLedger(episode_id=spec.episode_id, budget_usd=spec.budget_usd)

    a2_version = a2.version(writer.identity)
    from factory.agents.prefix import wordlist_block
    from factory.artifacts import sha256_text

    # The wordlist comes from pack data that neither the config hash nor the code hash covers.
    wordlist_hash = sha256_text(wordlist_block(config, pack))
    a2_inputs = [spec, config.config_hash, wordlist_hash]
    envelope = None if fresh else store.read_envelope(**where, station=a2.STATION, version=a2_version,
                                                      inputs=a2_inputs)
    if envelope:
        draft = Script.model_validate(envelope["artifact"])
        a2_costs = [CostEntry.model_validate(c) for c in envelope.get("cost", [])]
        typer.echo(f"A2: reusing stored draft {a2.STATION}@{envelope['hash']}")
    else:
        typer.echo(f"A2: drafting {spec.episode_id} with {writer.identity} ...")
        try:
            draft, a2_costs = a2.write_script(spec, config, pack, writer)
        except LLMError as exc:
            fail(exc)
        store.write(**where, station=a2.STATION, version=a2_version, inputs=a2_inputs, artifact=draft,
                    extra={"cost": [c.model_dump(mode="json") for c in a2_costs]})
        typer.echo(f"A2: done, ${sum(c.usd for c in a2_costs):.4f}, "
                   f"cache read {sum(c.cache_read_input_tokens for c in a2_costs)} tokens")
    ledger.entries += a2_costs

    result = a3.level_loop(draft, spec, config, pack, editor, max_turns=max_turns)
    ledger.entries += result.costs
    a3_version = a3.version(editor.identity)
    a3_inputs = [draft, spec, config.config_hash, wordlist_hash]
    script_path = store.write(**where, station=a3.STATION, version=a3_version, inputs=a3_inputs,
                              artifact=result.script,
                              extra={"status": result.status, "turns": result.turns,
                                     "cost": [c.model_dump(mode="json") for c in result.costs]})
    store.write(**where, station="level_report", version=a3_version, inputs=a3_inputs,
                artifact=result.reports[-1], extra={"status": result.status, "turns": result.turns})
    store.write(**where, station="cost_ledger", version=a3_version, inputs=a3_inputs, artifact=ledger)

    elapsed = round(time.monotonic() - started, 1)
    out_dir = eval_dir(config)
    write_json(out_dir / "scripts" / f"{spec.episode_id}.json", result.script.model_dump(mode="json"))
    append_attempt(out_dir / "runs" / f"{spec.episode_id}.json", {
        "episode_id": spec.episode_id,
        "status": result.status,
        "error": result.error,
        "a3_turns": result.turns,
        "elapsed_s": elapsed,
        "station_versions": {a2.STATION: a2_version, a3.STATION: a3_version},
        "first_report": result.reports[0].model_dump(mode="json"),
        "final_report": result.reports[-1].model_dump(mode="json"),
        "cost_ledger": ledger.model_dump(mode="json"),
    })

    for entry in ledger.entries:
        typer.echo(f"  {entry.station:<16} {entry.model:<18} in={entry.input_tokens} out={entry.output_tokens} "
                   f"cache_w={entry.cache_creation_input_tokens} cache_r={entry.cache_read_input_tokens} ${entry.usd:.4f}"
                   + ("" if entry.priced else " (no price for this model; not in the total)"))
    typer.echo(format_report(result.reports[-1]))
    typer.echo(f"status {result.status} after {result.turns} A3 turn(s); total ${ledger.total_usd:.4f}; {elapsed:.0f}s")
    typer.echo(f"artifact: {script_path}")
    raise typer.Exit(0 if result.status == "PASSED" else 2)


@app.command("review")
def review_cmd(
    spec_path: Path = typer.Argument(..., exists=True, help="EpisodeSpec JSON"),
    script_path: Path | None = typer.Option(None, "--script", help="Script JSON (default: the exported eval script)"),
):
    """Run the two-persona review panel on a script, one independent call per persona."""
    from factory.adapters.llm.router import provider_for
    from factory.agents.review_panel import agent as panel

    spec = load_spec(spec_path)
    config = resolve(spec.channel, spec.level)
    script_path = script_path or eval_dir(config) / "scripts" / f"{spec.episode_id}.json"
    script = Script.model_validate_json(script_path.read_text(encoding="utf-8"))
    run_path = eval_dir(config) / "runs" / f"{spec.episode_id}.json"
    for persona in panel.PERSONAS:
        try:
            llm = provider_for(panel.station(persona))
            result = panel.review(persona, spec, script, llm)
        except LLMError as exc:
            fail(exc)
        write_json(eval_dir(config) / "reviews" / spec.episode_id / f"{persona}.json", {
            "station_version": panel.version(persona, llm.identity),
            "level_fit_verdict": result.level_fit_verdict,
            "qa_report": result.qa_report.model_dump(mode="json"),
            "gate_decision": result.decision.model_dump(mode="json"),
            "costs": [c.model_dump(mode="json") for c in result.costs],
        })
        if run_path.exists():  # the panel's cost belongs to the script's ledger
            record = read_json(run_path)
            data = {k: v for k, v in record["attempts"][-1]["cost_ledger"].items() if k != "total_usd"}
            data["entries"] += [c.model_dump(mode="json") for c in result.costs]
            ledger = CostLedger.model_validate(data)
            record["attempts"][-1]["cost_ledger"] = ledger.model_dump(mode="json")
            write_json(run_path, record)
        counts = {sev: sum(i.severity == sev for i in result.qa_report.issues) for sev in ("critical", "major", "minor")}
        typer.echo(f"{persona:<9} {result.decision.decision:<16} level {result.level_fit_verdict:<5} "
                   f"issues {counts}  ${sum(c.usd for c in result.costs):.4f}")


@app.command("decide")
def decide_cmd(
    spec_path: Path = typer.Argument(..., exists=True, help="EpisodeSpec JSON"),
    decision: str = typer.Option(..., help="approve | edit-and-approve | reject"),
    notes: str = typer.Option("", help="What you found, using the panel's rubric"),
    level_fit: str = typer.Option(..., help="below | at | above the spec level"),
):
    """Record a human spot-check GateDecision for a script (user: human)."""
    spec = load_spec(spec_path)
    config = resolve(spec.channel, spec.level)
    if level_fit not in ("below", "at", "above"):
        raise typer.BadParameter("level-fit must be below, at or above")
    if decision not in ("approve", "edit-and-approve", "reject"):
        raise typer.BadParameter("decision must be approve, edit-and-approve or reject")
    gate_decision = GateDecision(episode_id=spec.episode_id, gate=1, user="human", decision=decision, notes=notes)
    path = eval_dir(config) / "reviews" / spec.episode_id / "human.json"
    write_json(path, {"level_fit_verdict": level_fit, "gate_decision": gate_decision.model_dump(mode="json")})
    typer.echo(f"wrote {path}")


@app.command("summary")
def summary_cmd(
    specs_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="Directory of EpisodeSpec JSON"),
):
    """Aggregate runs and reviews into one table and a JSON summary for the spike report."""
    specs = [load_spec(p) for p in sorted(specs_dir.glob("*.json"))]
    if not specs:
        raise typer.BadParameter("no specs found")
    config = resolve(specs[0].channel, specs[0].level)
    base = eval_dir(config)
    rows = []
    for spec in specs:
        run = latest_attempt(base / "runs" / f"{spec.episode_id}.json")
        reviews = {}
        for name in ("examiner", "learner", "human"):
            path = base / "reviews" / spec.episode_id / f"{name}.json"
            if path.exists():
                reviews[name] = read_json(path)
        panel_usd = sum(c["usd"] for r in reviews.values() for c in r.get("costs", []))
        entries = run["cost_ledger"]["entries"] if run else []
        script_usd = sum(e["usd"] for e in entries if not e["station"].startswith("review_"))
        final = run["final_report"] if run else None
        rows.append({
            "episode_id": spec.episode_id,
            "theme": spec.theme,
            "status": run["status"] if run else "NOT_RUN",
            "a3_turns": run["a3_turns"] if run else None,
            "elapsed_s": run["elapsed_s"] if run else None,
            "first_gate_failures": [f["gate"] for f in run["first_report"]["gate_failures"]] if run else [],
            "in_level_ratio": final["in_level_ratio"] if final else None,
            "script_usd": round(script_usd, 4),
            "panel_usd": round(panel_usd, 4),
            "decisions": {k: v["gate_decision"]["decision"] for k, v in reviews.items()},
            "level_fit": {k: v["level_fit_verdict"] for k, v in reviews.items()},
            "critical": {k: sum(i["severity"] == "critical" for i in v.get("qa_report", {}).get("issues", []))
                         for k, v in reviews.items() if k != "human"},
            "scores": {k: v["qa_report"]["rubric_scores"] for k, v in reviews.items() if "qa_report" in v},
        })
    write_json(base / "reviews" / "summary.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(), "episodes": rows,
    })
    typer.echo("| episode | status | A3 turns | first failures | in-level | examiner | learner | human | $ script | $ panel |")
    typer.echo("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        d = r["decisions"]
        ratio = f"{r['in_level_ratio']:.1%}" if r["in_level_ratio"] is not None else "-"
        typer.echo(f"| {r['episode_id']} | {r['status']} | {r['a3_turns']} | {', '.join(r['first_gate_failures']) or '-'} "
                   f"| {ratio} | {d.get('examiner', '-')} | {d.get('learner', '-')} | {d.get('human', '-')} "
                   f"| {r['script_usd']:.2f} | {r['panel_usd']:.2f} |")
    typer.echo(f"wrote {base / 'reviews' / 'summary.json'}")


@app.command("models")
def models_cmd(provider: str = typer.Argument(..., help="A provider name from config/llm.yaml")):
    """List the model names a provider's endpoint offers, to pick models for each role."""
    from factory.adapters.llm.router import list_models

    try:
        names = list_models(provider)
    except LLMError as exc:
        fail(exc)
    for name in names:
        typer.echo(name)
    typer.echo(f"{len(names)} model(s)", err=True)


@app.callback()
def main():
    """Language-learning video factory."""
    from factory.env import load_dotenv

    load_dotenv()
