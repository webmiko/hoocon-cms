#!/usr/bin/env python3
"""Copy VK_CALLBACK_SECRET and VK_CALLBACK_CONFIRMATION from repo .env to VPS."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV_FILE = REPO / ".env"


def _read_local() -> tuple[str, str]:
    secret = conf = ""
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("VK_CALLBACK_SECRET="):
            secret = line.split("=", 1)[1].strip()
        elif line.startswith("VK_CALLBACK_CONFIRMATION="):
            conf = line.split("=", 1)[1].strip()
    if not secret or not conf:
        print("ERROR: set VK_CALLBACK_SECRET and VK_CALLBACK_CONFIRMATION in .env", file=sys.stderr)
        sys.exit(1)
    return secret, conf


MERGE = """\
import sys
from pathlib import Path

fragment = Path(sys.argv[1])
lines = fragment.read_text().splitlines()
keys = {}
for line in lines:
    if line.startswith("VK_CALLBACK_SECRET="):
        keys["VK_CALLBACK_SECRET"] = line.split("=", 1)[1]
    elif line.startswith("VK_CALLBACK_CONFIRMATION="):
        keys["VK_CALLBACK_CONFIRMATION"] = line.split("=", 1)[1]
p = Path("/opt/hoocon/.env")
body = p.read_text().splitlines() if p.exists() else []
out, seen = [], set()
for line in body:
    hit = False
    for k, v in keys.items():
        if line.startswith(k + "="):
            out.append(f"{k}={v}")
            seen.add(k)
            hit = True
            break
    if not hit:
        out.append(line)
for k, v in keys.items():
    if k not in seen:
        out.append(f"{k}={v}")
p.write_text("\\n".join(out) + "\\n")
print(
    "prod updated secret_len=%d confirmation_len=%d"
    % (len(keys.get("VK_CALLBACK_SECRET", "")), len(keys.get("VK_CALLBACK_CONFIRMATION", "")))
)
"""


def main() -> None:
    secret, conf = _read_local()
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as tmp:
        tmp.write(f"VK_CALLBACK_SECRET={secret}\n")
        tmp.write(f"VK_CALLBACK_CONFIRMATION={conf}\n")
        fragment = tmp.name

    merge_path = Path(tempfile.mkstemp(suffix=".py")[1])
    merge_path.write_text(MERGE)

    bash = f"""
set -euo pipefail
cd "{REPO}"
source scripts/ssh-trust.sh
hoocon_ssh_trust
FRAG=/tmp/hoocon-vk-callback.env
MERGE=/tmp/merge_vk_callback_env.py
cleanup() {{ ssh "${{SSH_OPTS[@]}}" hoocon-prod "rm -f $FRAG $MERGE" || true; }}
trap cleanup EXIT
rsync -az -e "ssh ${{SSH_OPTS[*]}}" "{fragment}" "hoocon-prod:$FRAG"
rsync -az -e "ssh ${{SSH_OPTS[*]}}" "{merge_path}" "hoocon-prod:$MERGE"
ssh "${{SSH_OPTS[@]}}" hoocon-prod 'python3 /tmp/merge_vk_callback_env.py /tmp/hoocon-vk-callback.env;
rc=$?; rm -f /tmp/hoocon-vk-callback.env /tmp/merge_vk_callback_env.py; exit $rc'
"""
    result = subprocess.run(["bash", "-c", bash], capture_output=True, text=True)
    Path(fragment).unlink(missing_ok=True)
    merge_path.unlink(missing_ok=True)
    print(result.stdout.strip())
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
