"""Start a real check-only Cezar run so validation is visible in the cockpit."""

import argparse
import json
import subprocess
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4322)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    root = Path(__file__).resolve().parents[2]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    origin = f"http://127.0.0.1:{args.port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, body=None, method=None):
        request = urllib.request.Request(
            origin + "/api/v1" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": origin},
            method=method,
        )
        with opener.open(request, timeout=10) as response:
            return json.load(response)

    health = request("/health")
    if Path(health["repoRoot"]).resolve() != root:
        raise SystemExit("This port belongs to a different Cezar project")
    title = f"Verify AgentGate — {revision[:8]}" + (" + working changes" if dirty else "")
    task = (
        title + "\n\nRun make validate against the current working tree. "
        "This check records actual validation; it does not recreate earlier implementation history.\n\n"
        "Repository: https://github.com/bsisduck/laya-sec-agent\n"
        "Architecture: https://github.com/bsisduck/laya-sec-agent/blob/main/docs/architecture.md\n"
        "Docs and roadmap: https://github.com/bsisduck/laya-sec-agent/blob/main/docs/delivery.md\n"
        "Real inference evidence is separate from deterministic validation."
    )
    run = request(
        "/runs",
        {
            "workflow": "agentgate-verify",
            "task": task,
            "worktree": False,
            "autonomous": True,
            "generateFollowups": False,
        },
        "POST",
    )
    request("/runs/" + run["id"], {"title": title}, "PATCH")
    print(json.dumps({"run_id": run["id"], "status": run["status"], "cockpit": origin}))


if __name__ == "__main__":
    main()
