"""Dependency-free launcher entry point; serving uses the isolated installed wheel."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentgate.lifecycle.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
