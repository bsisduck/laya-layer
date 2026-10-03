"""Disposable browser QA server; optional backend source must be a reviewed checkout.

No simulated admin routes. Credentials remain in the private QA state directory.
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-source", type=Path, default=Path("src"))
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    sys.path.insert(0, str(args.backend_source.resolve()))
    import agentgate

    agentgate.__path__.append(str(Path(__file__).resolve().parents[2] / "src/agentgate"))
    import uvicorn

    from agentgate.app import create_app
    from agentgate.cli import initialize_demo
    from agentgate.documents import DocumentRegistry, FixtureExecutor, demo_documents
    from agentgate.policy import load_policy
    from agentgate.service import ActionService
    from agentgate.storage import Store
    from agentgate.web_routes import attach_web_routes

    if not args.state_dir.exists():
        initialize_demo(args.state_dir)
    policy = load_policy(Path("config/policy.yaml"))
    store = Store(args.state_dir / "agentgate.sqlite3")
    documents = demo_documents()
    service = ActionService(
        store,
        policy,
        DocumentRegistry(documents),
        FixtureExecutor(documents),
        (args.state_dir / "audit.key").read_bytes(),
    )
    try:
        from agentgate.admin import bootstrap_operator
    except ImportError:
        app = create_app(service)
    else:
        if not (args.state_dir / "operator.token").exists():
            bootstrap_operator(args.state_dir, policy)
        app = create_app(service, admin_origin=f"http://127.0.0.1:{args.port}")
    if not any(getattr(route, "path", None) == "/" for route in app.routes):
        attach_web_routes(app)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
