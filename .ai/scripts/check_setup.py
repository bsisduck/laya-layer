"""Validate repository workflow artifacts; application checks run through Make."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    config = json.loads((ROOT / ".ai/agentic.config.json").read_text())
    for name in [
        "README.md", "AGENTS.md", "SDLC.md", "CODE_REVIEW.md",
        "BACKWARD_COMPATIBILITY.md", "AgentGate_Full_Project_Architecture.md",
        "docs/readiness.md", ".ai/specs/implementation-start.md",
        "pyproject.toml", "uv.lock",
        f".ai/trackers/{config['tracker']}.md",
        f".ai/browsers/{config['browser']['provider']}.md",
    ]:
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing required preparation artifact: {name}")
    for name in ["runs", "analysis", "specs", "scripts", "qa"]:
        if not (ROOT / config["paths"][name]).is_dir():
            raise SystemExit(f"Missing configured directory: {name}")
    if config["version"] != 1 or config["validation"]["commands"] != ["make validate"]:
        raise SystemExit("Keep the pipeline config and documented validation gate aligned")
    subprocess.run(
        ["git", "diff", "--check"], cwd=ROOT, check=True,
    )
    print("PASS: repository workflow artifacts; Python validation follows")


if __name__ == "__main__":
    main()
