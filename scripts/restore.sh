#!/usr/bin/env bash
set -euo pipefail
export PYTHONUTF8=1
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if command -v uv >/dev/null 2>&1; then
  exec uv run --project "${script_dir}/.." python "${script_dir}/snapshot.py" restore "$@"
fi
if [[ -x "${script_dir}/../.venv/Scripts/python.exe" ]]; then
  exec "${script_dir}/../.venv/Scripts/python.exe" "${script_dir}/snapshot.py" restore "$@"
fi
if [[ -x "${script_dir}/../.venv/bin/python" ]]; then
  exec "${script_dir}/../.venv/bin/python" "${script_dir}/snapshot.py" restore "$@"
fi
exec python3 "${script_dir}/snapshot.py" restore "$@"
