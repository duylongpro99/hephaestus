#!/usr/bin/env bash
# Local CI: lint, unit and conformance tests, then one xx-fixture episode from SPEC to SCHEDULED
# against a fresh Postgres database. A hosted runner can call this script as is.
set -euo pipefail

cd "$(dirname "$0")/.."
started=$(date +%s)
current="setup"
trap 'echo "ci: FAILED at step: $current" >&2' ERR

step() {
  current="$1"
  echo
  echo "== $current"
}

step "check tools"
for tool in uv docker ffmpeg ffprobe; do
  command -v "$tool" >/dev/null || { echo "ci: $tool is not on PATH" >&2; false; }
done

# No LLM endpoint: every LLM call must come from the fake provider. Empty values also stop
# .env from filling them in.
export LLM_GATEWAY_URL="" LLM_GATEWAY_API_KEY=""
# Every media purpose is served by the offline providers of the fake profile.
export FACTORY_MEDIA_PROFILE="fake"
DB_NAME="factory_ci"
export DATABASE_URL="postgresql://factory:factory@localhost:5432/factory"
CI_DATABASE_URL="postgresql://factory:factory@localhost:5432/$DB_NAME"
SPEC="evals/xx-fixture/adult/specs/xx-A2-e2e.json"
EPISODE="xx-A2-e2e"
ARTIFACTS="$(mktemp -d)"

step "lint"
uv run ruff check .

step "unit and conformance tests"
uv run pytest -q -m "not db and not e2e"

step "start postgres"
docker compose up -d --wait db

step "migrate a fresh database"
docker compose exec -T db psql -q -U factory -d factory -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE)"
docker compose exec -T db psql -q -U factory -d factory -c "CREATE DATABASE $DB_NAME"
DATABASE_URL="$CI_DATABASE_URL" uv run factory db migrate
DATABASE_URL="$CI_DATABASE_URL" uv run factory db migrate | grep -q "up to date"

step "database and end-to-end tests"
uv run pytest -q -m "db or e2e"

step "end-to-end episode"
DATABASE_URL="$CI_DATABASE_URL" uv run factory run "$SPEC" --auto-approve --fake-llm --artifacts "$ARTIFACTS"

step "check the episode"
DATABASE_URL="$CI_DATABASE_URL" uv run factory status "$EPISODE" | tee "$ARTIFACTS/status.txt"
grep -q "^$EPISODE: SCHEDULED;" "$ARTIFACTS/status.txt"
grep -q "receipt export/.* scheduled" "$ARTIFACTS/status.txt"
video=$(find "$ARTIFACTS" -path "*/$EPISODE/c8_render@*/master.mp4" | head -n 1)
[ -n "$video" ] || { echo "ci: no master.mp4 under $ARTIFACTS" >&2; false; }
ffprobe -v error -show_entries stream=codec_type -of csv=p=0 "$video" | sort | tr '\n' ' ' | grep -q "audio video"

current="done"
rm -rf "$ARTIFACTS"
echo
echo "ci: passed in $(( $(date +%s) - started ))s"
