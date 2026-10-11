"""The `factory` command line."""

import time
from pathlib import Path

import typer

from factory.config import resolve
from factory.contracts import CostEntry, CostLedger, EpisodeSpec, Script
from factory.tools.language_pack import load_pack
from factory.tools.profiler import format_report, profile

app = typer.Typer(no_args_is_help=True, add_completion=False)


def load_spec(path: Path) -> EpisodeSpec:
    return EpisodeSpec.model_validate_json(path.read_text(encoding="utf-8"))


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
    from factory.adapters.llm.anthropic_client import LLMClient
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
    llm = LLMClient()
    store = ArtifactStore()
    where = {"channel": spec.channel, "episode": spec.episode_id, "season": spec.season_id}
    ledger = CostLedger(episode_id=spec.episode_id, budget_usd=spec.budget_usd)

    a2_version = a2.version(llm.model)
    a2_inputs = [spec, config.config_hash]
    envelope = None if fresh else store.read_envelope(**where, station=a2.STATION, version=a2_version,
                                                      inputs=a2_inputs)
    if envelope:
        draft = Script.model_validate(envelope["artifact"])
        a2_costs = [CostEntry.model_validate(c) for c in envelope.get("cost", [])]
        typer.echo(f"A2: reusing stored draft {a2.STATION}@{envelope['hash']}")
    else:
        typer.echo(f"A2: drafting {spec.episode_id} with {llm.model} ...")
        draft, a2_cost = a2.write_script(spec, config, pack, llm)
        a2_costs = [a2_cost]
        store.write(**where, station=a2.STATION, version=a2_version, inputs=a2_inputs, artifact=draft,
                    extra={"cost": [c.model_dump(mode="json") for c in a2_costs]})
        typer.echo(f"A2: done, ${a2_cost.usd:.4f}, cache read {a2_cost.cache_read_input_tokens} tokens")
    ledger.entries += a2_costs

    result = a3.level_loop(draft, spec, config, pack, llm, max_turns=max_turns)
    ledger.entries += result.costs
    a3_version = a3.version(llm.model)
    a3_inputs = [draft, spec, config.config_hash]
    script_path = store.write(**where, station=a3.STATION, version=a3_version, inputs=a3_inputs,
                              artifact=result.script,
                              extra={"status": result.status, "turns": result.turns,
                                     "cost": [c.model_dump(mode="json") for c in result.costs]})
    store.write(**where, station="level_report", version=a3_version, inputs=a3_inputs,
                artifact=result.reports[-1], extra={"status": result.status, "turns": result.turns})
    store.write(**where, station="cost_ledger", version=a3_version, inputs=a3_inputs, artifact=ledger)

    for entry in ledger.entries:
        typer.echo(f"  {entry.station:<16} {entry.model:<18} in={entry.input_tokens} out={entry.output_tokens} "
                   f"cache_w={entry.cache_creation_input_tokens} cache_r={entry.cache_read_input_tokens} ${entry.usd:.4f}")
    typer.echo(format_report(result.reports[-1]))
    typer.echo(f"status {result.status} after {result.turns} A3 turn(s); total ${ledger.total_usd:.4f}; "
               f"{time.monotonic() - started:.0f}s")
    typer.echo(f"script: {script_path}")
    raise typer.Exit(0 if result.status == "PASSED" else 2)


@app.callback()
def main():
    """Language-learning video factory."""
