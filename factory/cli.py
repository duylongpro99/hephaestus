"""The `factory` command line."""

from pathlib import Path

import typer

from factory.config import resolve
from factory.contracts import EpisodeSpec, Script
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


@app.callback()
def main():
    """Language-learning video factory."""
