"""Validate preparation artifacts, without claiming application test coverage."""

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
    # Deliberately prevent bootstrap success from becoming product-test evidence.
    if any((ROOT / name).exists() for name in ["src", "workers", "pyproject.toml"]):
        raise SystemExit(
            "Application work detected: replace the setup-only gate with real "
            "lint, typing, tests, and build validation before reporting success."
        )
    print("PASS: preparation artifacts; application tests are not implemented")


if __name__ == "__main__":
    main()
