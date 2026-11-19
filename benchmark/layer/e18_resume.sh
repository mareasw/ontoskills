#!/usr/bin/env bash
# E18 — resume Nano-GraphRAG after the weekly quota reset.
#
# The build replays every cached call for free and pays only for the community
# reports that never completed (563 of 1 930 at the time of the wall). Then the
# questions, then the score, then the paired comparison against the rows already
# on the table. Nothing here is tuned: every setting is in E6-PROTOCOL.md §E18 and
# its amendments 1–7.
#
#   benchmark/layer/e18_resume.sh
#
# Override with LAYER=, WORK=, METER=, PORT=, PYTHON= when the layout differs.
set -euo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
layer=${LAYER:-$repo/../pilot-work/layer}
work=${WORK:-$layer/nano}
meter=${METER:-$layer/runs/nanographrag.meter.jsonl}
port=${PORT:-8096}
python=${PYTHON:-$repo/../pilot-work/venv-nano/bin/python}

set -a
# shellcheck disable=SC1091
. "$repo/.env"
set +a

if ! ss -tln 2>/dev/null | grep -q "127.0.0.1:$port "; then
  echo "starting the meter proxy on $port"
  ( cd "$repo" && exec python3 -m benchmark.layer.meter_proxy \
      --port "$port" --upstream "$OPENAI_BASE_URL" --label nanographrag \
      --log "$meter" --append --stream-upstream ) &
  sleep 2
fi

export OPENAI_BASE_URL="http://127.0.0.1:$port/v1"
export PYTHONPATH="$repo/../pilot-work/pypath:$repo"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$repo"

echo "== build =="
"$python" -m benchmark.layer.run_nanographrag \
  --phase build --layer "$layer" --working "$work" --meter "$meter"

for mode in local naive; do
  echo "== ask ($mode) =="
  "$python" -m benchmark.layer.run_nanographrag \
    --phase ask --mode "$mode" --layer "$layer" --working "$work" --meter "$meter"
  echo "== score ($mode) =="
  "$python" -m benchmark.layer.run_nanographrag \
    --phase score --mode "$mode" --layer "$layer" --working "$work" --meter "$meter"
done

echo "== comparison =="
python3 -m benchmark.layer.e18_nano --layer "$layer"

echo "spent: $(python3 - <<'PY'
import json, os
from pathlib import Path
path = Path(os.environ["METER"])
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
ok = [r for r in rows if int(r.get("status", 200)) < 400]
prompt = sum(r.get("prompt_tokens") or 0 for r in ok)
completion = sum(r.get("completion_tokens") or 0 for r in ok)
print(f"{prompt / 1e6 * 0.15 + completion / 1e6 * 0.60:.4f} $ over {len(ok)} calls")
PY
)"
