"""Read-only host inventory. Does not start services or run inference."""

import json
import re
import shutil
import subprocess
from pathlib import Path


def probe(label, command, json_summary=False):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        output = (result.stdout or result.stderr).strip().splitlines()
        state = "OK" if result.returncode == 0 else "GAP"
        detail = output[0] if output else "no output"
        if json_summary and result.returncode == 0:
            detail = json.dumps(json.loads(result.stdout).get("summary", {}))
        print(f"{state}: {label}: {detail}")
        return result
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"GAP: {label}: {type(error).__name__}")


def check_skills():
    roots = [Path.home() / ".codex/skills", Path.home() / ".agents/skills"]
    skills = {}
    for root in reversed(roots):
        skills.update({p.name: p for p in root.glob("om-*") if (p / "SKILL.md").is_file()})
    setup = skills.get("om-setup-agent-pipeline")
    if not setup:
        print("GAP: Open Mercato setup skill missing")
        return
    reference = (setup / "references/skill-coverage.md").read_text()
    roster = set(re.search(r'ROSTER="([^"]+)"', reference).group(1).split())
    missing = sorted(roster - skills.keys())
    broken = set()
    for directory in skills.values():
        for file in directory.rglob("*.md"):
            for target in re.findall(
                r"om-[a-z-]+/references/[A-Za-z0-9._/-]+", file.read_text()
            ):
                name, relative = target.split("/", 1)
                if name not in skills or not (skills[name] / relative).exists():
                    broken.add(target)
    print(f"{'GAP' if missing or broken else 'OK'}: Open Mercato skills: {len(skills)} installed")
    for item in missing + sorted(broken):
        print(f"  missing: {item}")


def main():
    for name in ["git", "node", "npm", "python3.12", "uv", "codex", "claude", "swift"]:
        probe(name, [name, "--version"])
    probe("Docker engine", ["docker", "info", "--format", "{{.ServerVersion}}"])
    probe("Ollama inventory (not inference validation)", ["ollama", "list"])
    gh = probe("GitHub CLI", ["gh", "--version"])
    version = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", gh.stdout) if gh else None
    if not version or tuple(map(int, version.groups())) < (2, 82, 1):
        print("GAP: GitHub tracker descriptor requires gh >= 2.82.1")
    browser = shutil.which("agent-browser")
    if not browser:
        cache = Path.home() / ".cache/agent-tools/agent-browser/v0.35.2"
        browser = next((str(p) for p in cache.glob("agent-browser-*") if p.is_file()), None)
    if browser:
        probe("Browser QA", [browser, "doctor", "--json"], json_summary=True)
    else:
        print("GAP: browser QA not installed; use .ai/browsers/agent-browser.md")
    check_skills()
    print("NOTE: This is a tool inventory. Gateway checks: make validate; real inference: scripts/semantic_smoke.py")


if __name__ == "__main__":
    main()
