"""The `factory` command line."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import typer

from factory.adapters.llm.base import LLMError
from factory.config import REPO_ROOT, ResolvedConfig, resolve
from factory.contracts import CostLedger, EpisodeSpec, GateDecision, Script
from factory.tools.language_pack import load_pack
from factory.tools.profiler import format_report, profile

app = typer.Typer(no_args_is_help=True, add_completion=False)
db_app = typer.Typer(no_args_is_help=True, help="The orchestrator's Postgres database.")
app.add_typer(db_app, name="db")


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
    fresh: bool = typer.Option(False, help="Ignore stored A2 and A3 outputs and call the models again"),
    max_turns: int = typer.Option(4, help="Maximum A3 editing turns"),
    writer_role: str = typer.Option("a2_scriptwriter", "--writer", help="config/llm.yaml role that drafts the script"),
):
    """Draft a script with A2, run the code gates, and patch it with A3 until it passes or escalates."""
    from factory.adapters.llm.router import provider_for
    from factory.agents.a2_scriptwriter import agent as a2
    from factory.agents.a3_level_editor import agent as a3
    from factory.artifacts import ArtifactStore, Producer
    from factory.orchestrator.stations import LevelLoopFailed, draft_script, level_script, wordlist_hash

    started = time.monotonic()
    spec = load_spec(spec_path)
    config = resolve(spec.channel, spec.level)
    if spec.config_hash != config.config_hash:
        typer.echo(f"warning: spec config_hash {spec.config_hash[:19]} differs from the live config "
                   f"{config.config_hash[:19]}; using the live config")
    pack = load_pack(config.pack.code)
    try:
        writer, editor = provider_for(writer_role), provider_for(a3.STATION)
    except LLMError as exc:
        fail(exc)
    store = ArtifactStore()
    out = Producer(store, spec.channel, spec.episode_id, spec.season_id, fresh=fresh)
    ledger = CostLedger(episode_id=spec.episode_id, budget_usd=spec.budget_usd)

    typer.echo(f"A2: {spec.episode_id} with {writer.identity} ...")
    try:
        draft = draft_script(out, spec, config, pack, writer)
    except LLMError as exc:
        fail(exc)
    a2_costs = out.ledger[:]
    if out.last.reused:
        typer.echo(f"A2: reusing stored draft {a2.STATION}@{out.last.envelope['hash']}")
    else:
        typer.echo(f"A2: done, ${sum(c.usd for c in a2_costs):.4f}, "
                   f"cache read {sum(c.cache_read_input_tokens for c in a2_costs)} tokens")

    try:
        leveled = level_script(out, draft, spec, config, pack, editor, max_turns=max_turns)
        script, status, turns, error = leveled.script, leveled.status, leveled.turns, None
        first_report, final_report = leveled.first_report, leveled.report
        script_path = next(p.path for p in out.produced if p.envelope["station"] == a3.STATION)
        if out.produced[-2].reused:
            typer.echo(f"A3: reusing stored result {a3.STATION}@{out.produced[-2].envelope['hash']}")
    except LevelLoopFailed as exc:
        result = exc.result
        script, status, turns, error = result.script, "ESCALATED", result.turns, result.error
        first_report, final_report = result.reports[0], result.reports[-1]
        ledger.entries += exc.costs
        script_path = None
    ledger.entries = out.ledger + ledger.entries
    a3_version = a3.version(editor.identity)
    a3_inputs = [draft, spec, config.config_hash, wordlist_hash(config, pack), max_turns]
    store.write(channel=spec.channel, episode=spec.episode_id, season=spec.season_id, station="cost_ledger",
                version=a3_version, inputs=a3_inputs, artifact=ledger)

    elapsed = round(time.monotonic() - started, 1)
    out_dir = eval_dir(config)
    write_json(out_dir / "scripts" / f"{spec.episode_id}.json", script.model_dump(mode="json"))
    append_attempt(out_dir / "runs" / f"{spec.episode_id}.json", {
        "episode_id": spec.episode_id,
        "status": status,
        "error": error,
        "a3_turns": turns,
        "elapsed_s": elapsed,
        "station_versions": {a2.STATION: a2.version(writer.identity), a3.STATION: a3_version},
        "first_report": first_report.model_dump(mode="json"),
        "final_report": final_report.model_dump(mode="json"),
        "cost_ledger": ledger.model_dump(mode="json"),
    })

    for entry in ledger.entries:
        typer.echo(f"  {entry.station:<16} {entry.model:<18} in={entry.input_tokens} out={entry.output_tokens} "
                   f"cache_w={entry.cache_creation_input_tokens} cache_r={entry.cache_read_input_tokens} ${entry.usd:.4f}"
                   + ("" if entry.priced else " (no price for this model; not in the total)"))
    typer.echo(format_report(final_report))
    typer.echo(f"status {status} after {turns} A3 turn(s); total ${ledger.total_usd:.4f}; {elapsed:.0f}s")
    if error:
        typer.echo(f"error: {error}")
    if script_path:
        typer.echo(f"artifact: {script_path}")
    raise typer.Exit(0 if status == "PASSED" else 2)


@app.command("review")
def review_cmd(
    spec_path: Path = typer.Argument(..., exists=True, help="EpisodeSpec JSON"),
    script_path: Path | None = typer.Option(None, "--script", help="Script JSON (default: the exported eval script)"),
    fresh: bool = typer.Option(False, help="Ignore stored reviews of this script and call the reviewers again"),
):
    """Run the two-persona review panel on a script, one independent call per persona."""
    from factory.adapters.llm.router import provider_for
    from factory.agents.review_panel import agent as panel
    from factory.artifacts import ArtifactStore, Producer
    from factory.orchestrator.stations import review_script

    spec = load_spec(spec_path)
    config = resolve(spec.channel, spec.level)
    script_path = script_path or eval_dir(config) / "scripts" / f"{spec.episode_id}.json"
    script = Script.model_validate_json(script_path.read_text(encoding="utf-8"))
    run_path = eval_dir(config) / "runs" / f"{spec.episode_id}.json"
    out = Producer(ArtifactStore(), spec.channel, spec.episode_id, spec.season_id, fresh=fresh)
    for persona in panel.PERSONAS:
        try:
            llm = provider_for(panel.station(persona))
            [result] = review_script(out, spec, script, {persona: llm})
        except LLMError as exc:
            fail(exc)
        write_json(eval_dir(config) / "reviews" / spec.episode_id / f"{persona}.json", {
            "station_version": panel.version(persona, llm.identity),
            "level_fit_verdict": result.level_fit_verdict,
            "qa_report": result.qa_report.model_dump(mode="json"),
            "gate_decision": result.decision.model_dump(mode="json"),
            "costs": [c.model_dump(mode="json") for c in result.costs],
        })
        # The panel's cost belongs to the script's ledger, once: a stored review was counted when it ran.
        if run_path.exists() and not out.last.reused:
            record = read_json(run_path)
            data = {k: v for k, v in record["attempts"][-1]["cost_ledger"].items() if k != "total_usd"}
            data["entries"] += [c.model_dump(mode="json") for c in result.costs]
            ledger = CostLedger.model_validate(data)
            record["attempts"][-1]["cost_ledger"] = ledger.model_dump(mode="json")
            write_json(run_path, record)
        counts = {sev: sum(i.severity == sev for i in result.qa_report.issues) for sev in ("critical", "major", "minor")}
        typer.echo(f"{persona:<9} {result.decision.decision:<16} level {result.level_fit_verdict:<5} "
                   f"issues {counts}  ${sum(c.usd for c in result.costs):.4f}"
                   + ("  (stored review)" if out.last.reused else ""))


@app.command("decide")
def decide_cmd(
    spec_path: Path = typer.Argument(..., exists=True, help="EpisodeSpec JSON"),
    decision: str = typer.Option(..., help="approve | edit-and-approve | reject"),
    notes: str = typer.Option("", help="What you found, using the panel's rubric"),
    level_fit: str | None = typer.Option(None, help="below | at | above the spec level; also saves the decision as eval data"),
    gate: int = typer.Option(1, help="1 = script approval, 2 = final approval"),
    diff: str | None = typer.Option(None, help="With edit-and-approve: the edits, as a unified diff or notes per line id"),
):
    """Record a human GateDecision (user: human) for an episode in the database, and as eval data with --level-fit."""
    import os

    from factory.orchestrator import repo
    from factory.orchestrator.states import GATES

    spec = load_spec(spec_path)
    if decision not in ("approve", "edit-and-approve", "reject"):
        raise typer.BadParameter("decision must be approve, edit-and-approve or reject")
    if gate not in (1, 2):
        raise typer.BadParameter("gate must be 1 or 2")
    if level_fit is not None and level_fit not in ("below", "at", "above"):
        raise typer.BadParameter("level-fit must be below, at or above")
    gate_decision = GateDecision(episode_id=spec.episode_id, gate=gate, user="human", decision=decision, notes=notes,
                                 diff=diff)
    recorded = False
    if level_fit is not None:
        if gate != 1:
            raise typer.BadParameter("--level-fit applies to the script gate (1) only")
        config = resolve(spec.channel, spec.level)
        path = eval_dir(config) / "reviews" / spec.episode_id / "human.json"
        write_json(path, {"level_fit_verdict": level_fit, "gate_decision": gate_decision.model_dump(mode="json")})
        typer.echo(f"wrote {path}")
        recorded = True
    if os.environ.get("DATABASE_URL"):
        with db_connect() as conn:
            episode = repo.get_episode(conn, spec.episode_id)
            if episode:
                if episode["status"] != GATES[gate]:
                    typer.echo(f"error: {spec.episode_id} is at {episode['status']}, not waiting at gate {gate} "
                               f"({GATES[gate]})", err=True)
                    raise typer.Exit(1)
                with conn.transaction():
                    repo.insert_gate_decision(conn, gate_decision)
                typer.echo(f"recorded gate {gate} {decision} for {spec.episode_id}; `factory run` continues it")
                recorded = True
    if not recorded:
        typer.echo(f"error: {spec.episode_id} is not in the database; pass --level-fit to save eval data", err=True)
        raise typer.Exit(1)


@app.command("run")
def run_cmd(
    spec_path: Path = typer.Argument(..., exists=True, help="EpisodeSpec JSON"),
    auto_approve: bool = typer.Option(False, help="Approve human gates as user 'auto' instead of waiting"),
    fake_llm: bool = typer.Option(False, help="Serve every LLM role from tests/fixtures/<pack>/<episode>/"),
    artifacts: Path = typer.Option(None, help="Artifact store root (default: artifacts/)"),
):
    """Create the episode if new, then move it through the stations until SCHEDULED, a gate, or a stop."""
    from datetime import datetime, timezone
    from functools import cache

    from factory.adapters.image.fake import FakeImageProvider
    from factory.adapters.llm.fake import FakeLLMProvider
    from factory.adapters.llm.router import provider_for
    from factory.adapters.publish.fake import FakePublisher
    from factory.adapters.tts.fake import FakeTTS
    from factory.agents.review_panel.agent import PERSONAS
    from factory.artifacts import ARTIFACT_ROOT, ArtifactStore
    from factory.orchestrator import repo
    from factory.orchestrator.runner import Runner
    from factory.orchestrator.stations import Stations, Vendors
    from factory.orchestrator.states import DONE, PIPELINE, STOPPED

    spec = load_spec(spec_path)
    store = ArtifactStore(artifacts or ARTIFACT_ROOT)
    fixtures = REPO_ROOT / "tests" / "fixtures"
    with db_connect() as conn:
        if repo.get_episode(conn, spec.episode_id) is None:
            config = resolve(spec.channel, spec.level)
            if spec.config_hash != config.config_hash:
                typer.echo(f"error: spec config_hash {spec.config_hash[:19]} differs from the live config "
                           f"{config.config_hash[:19]}; re-resolve the spec before creating the episode", err=True)
                raise typer.Exit(1)
            with conn.transaction():
                repo.create_episode(conn, spec, config, datetime.now(timezone.utc))
            typer.echo(f"created {spec.episode_id} at SPEC (config {config.config_hash[:19]})")
        else:
            config = ResolvedConfig.model_validate(repo.get_episode(conn, spec.episode_id)["resolved_config"])
            repo.create_episode(conn, spec, config, datetime.now(timezone.utc))  # refuses a changed spec

        @cache
        def llm(role: str):
            if fake_llm:
                return FakeLLMProvider(fixtures / config.pack.code / spec.episode_id)
            return provider_for(role)

        vendors = Vendors(llm=llm, tts=FakeTTS, images=FakeImageProvider(),
                          publisher=FakePublisher(store.root / "_fake_publisher"))
        runner = Runner(conn, Stations(vendors).registry(), store, auto_approve=auto_approve,
                        panel_users=tuple(PERSONAS))
        state = runner.advance(spec.episode_id)
        print_status(conn, spec.episode_id)
    if state in STOPPED:
        raise typer.Exit(1)
    if state not in DONE:
        gate = PIPELINE[state].gate
        typer.echo(f"waiting at gate {gate}: record a decision with `factory decide {spec_path} --gate {gate} "
                   "--decision approve|edit-and-approve|reject`, then run again")


def print_status(conn, episode_id: str) -> None:
    from factory.orchestrator import repo

    episode = repo.get_episode(conn, episode_id)
    if episode is None:
        typer.echo(f"error: no episode {episode_id}", err=True)
        raise typer.Exit(1)
    for job in repo.jobs(conn, episode_id):
        took = (job["finished_at"] - job["started_at"]).total_seconds()
        typer.echo(f"  {job['station']:<16} {job['from_status']:>15} -> {job['to_status'] or '(retry)':<15} "
                   f"#{job['attempt']} {job['status']:<10} {took:6.2f}s" + (f"  {job['error']}" if job["error"] else ""))
    spent = repo.spent_usd(conn, episode_id)
    typer.echo(f"{episode_id}: {episode['status']}; spent ${spent:.4f} of ${float(episode['budget_usd']):.2f}")
    for receipt in repo.receipts(conn, episode_id):
        typer.echo(f"  receipt {receipt.platform}/{receipt.external_id} {receipt.status} "
                   f"publish_at {receipt.publish_at.isoformat() if receipt.publish_at else '-'}")


@app.command("status")
def status_cmd(episode_id: str = typer.Argument(..., help="Episode id")):
    """Print an episode's state, its jobs and its spend against the budget."""
    with db_connect() as conn:
        print_status(conn, episode_id)


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


def db_connect():
    from factory.orchestrator.db import DatabaseError, connect

    try:
        return connect()
    except DatabaseError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)


@db_app.command("migrate")
def db_migrate_cmd():
    """Apply the SQL migrations the database does not have yet."""
    from factory.orchestrator.db import migrate

    with db_connect() as conn:
        applied = migrate(conn)
    typer.echo(f"applied {', '.join(applied)}" if applied else "database is up to date")


@app.callback()
def main():
    """Language-learning video factory."""
    from factory.env import load_dotenv

    load_dotenv()
