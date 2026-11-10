"""Pre-commit guard: fail if staged content contains values from config/profile.yaml
(names, address, case number, phone/email) or looks like a secret. Prints no values."""
import re
import subprocess
import sys
from pathlib import Path

import yaml

SECRET_RE = re.compile(r"(\d{8,10}:[A-Za-z0-9_-]{35}|gh[pousr]_[A-Za-z0-9]{30,}|sk-ant-[A-Za-z0-9_-]{20,})")


def profile_values() -> list[str]:
    p = Path("config/profile.yaml")
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    out: list[str] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and len(o) >= 6 and o != "TODO":
            out.append(o.lower())

    h = data.get("household", {})
    walk(h)
    walk(data.get("wbs", {}).get("reference"))
    return out


def main() -> int:
    files = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    bad = 0
    if "config/profile.yaml" in files:
        print("BLOCKED: config/profile.yaml is staged")
        bad += 1
    vals = profile_values()
    for f in files:
        if f == "config/profile.yaml":
            continue
        text = subprocess.run(["git", "show", f":{f}"], capture_output=True, text=True).stdout
        low = text.lower()
        for i, v in enumerate(vals):
            if v in low:
                print(f"BLOCKED: {f} contains personal profile value #{i}")
                bad += 1
        if SECRET_RE.search(text):
            print(f"BLOCKED: {f} looks like it contains a secret")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
