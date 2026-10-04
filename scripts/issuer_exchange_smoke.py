#!/usr/bin/env python3
"""Installed exchange → direct REST/MCP/Hermes, with GENERATED-KEY/PROVIDER FIXTURES.

Owns only this checkout's prepared QA installation. Uses its installed wheel and
supervisor; replaces only its owned private provider with a labelled deterministic
fixture. No inference, primary services or shared Ollama calls. Finally stops QA.
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".ai/qa/artifacts_issuer_exchange"


def fixture_provider(port, state, counts):
    """Never logs requests or bodies. Private provider wire fixture only."""
    upstream = (state / "data/litellm.token").read_text().strip()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, body, status=200):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def permitted(self):
            return self.headers.get("Authorization") == "Bearer " + upstream

        def do_GET(self):
            if self.path != "/v1/models" or not self.permitted():
                return self.reply({}, 401)
            self.reply({"data": [{"id": "local-demo", "object": "model"}]})

        def do_POST(self):
            if self.path != "/v1/chat/completions" or not self.permitted():
                return self.reply({}, 401)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 262144:
                return self.reply({}, 413)
            payload = json.loads(self.rfile.read(length))
            complete = any(m["role"] == "tool" for m in payload["messages"])
            if complete:
                returned = next(m for m in reversed(payload["messages"]) if m["role"] == "tool")
                assert returned["tool_call_id"] == "fixture-call-7"
                envelope = json.loads(returned["content"])
                result = (
                    envelope
                    if "executed" in envelope
                    else envelope.get("structuredContent", envelope.get("result", envelope))
                )
                result = json.loads(result) if isinstance(result, str) else result
                assert result["executed"] is True
            message = {
                "role": "assistant",
                "content": "Fixture result summarized" if complete else None,
            }
            if not complete:
                message["tool_calls"] = [
                    {
                        "id": "fixture-call-7",
                        "type": "function",
                        "function": {
                            "name": "documents_read",
                            "arguments": json.dumps({"document_id": "tenant-a-notes"}),
                        },
                    }
                ]
            # Persist counts only, never assertion/messages or raw response bodies.
            previous = json.loads(counts.read_text()) if counts.exists() else {"calls": 0}
            counts.write_text(
                json.dumps({"calls": previous["calls"] + 1, "kind": "provider-fixture"})
            )
            self.reply(
                {
                    "id": "fixture-completion",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "local-demo",
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": "stop" if complete else "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23},
                }
            )

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def private_json(path, value):
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream)


def installed_run(state, base, hermes_source):
    import httpx
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from agentgate.lifecycle.install import services
    from agentgate.lifecycle.processes import launch
    from agentgate.storage import credential_digest

    assert "site-packages" in __import__("agentgate").__file__
    assert str(ROOT / "src") not in __import__("agentgate").__file__
    gateway = state / "runtime/gateway/bin/agentgate"
    python = state / "runtime/gateway/bin/python"
    suffix = uuid.uuid4().hex[:12]
    report_path = ARTIFACTS / ("report-" + suffix + ".json")
    counts = ARTIFACTS / ("fixture-counts-" + suffix + ".json")
    counts.write_text(json.dumps({"calls": 0, "kind": "provider-fixture"}))
    configured = services(state)
    provider = next(service for service in configured if service.name == "litellm")
    command = [
        str(python),
        "-I",
        str(Path(__file__).resolve()),
        "--fixture-provider",
        "--port",
        str(provider.port),
        "--state",
        str(state),
        "--counts",
        str(counts),
    ]
    configured = [
        replace(service, command=command) if service.name == "litellm" else service
        for service in configured
    ]
    launch(state, configured)
    data = state / "data"
    parent = (data / "client.token").read_text().strip()
    report = {
        "kind": "installed-generated-key-provider-fixture",
        "model_evaluation": "not_run",
        "source_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "runs": [],
        "status": "in_progress",
    }
    saved = None
    old_trust = None
    admin = httpx.Client(base_url=base, trust_env=False, timeout=15, headers={"Origin": base})
    csrf = None
    database = data / "agentgate.sqlite3"

    def sql(statement, parameters=()):
        with sqlite3.connect(database) as db:
            return db.execute(statement, parameters).fetchall()

    def run_cli(*args):
        result = subprocess.run(
            [str(gateway), "--state-dir", str(data), *args], capture_output=True, timeout=30
        )
        assert result.returncode == 0, "Installed CLI failed (contents withheld)"
        return result

    def activate(value):
        current = admin.get("/admin/policy").json()
        response = admin.post(
            "/admin/policy/activate",
            headers=csrf,
            json={
                "policy": value | {"revision": current["policy"]["revision"] + 1},
                "expected_version": current["version"],
            },
        )
        assert response.status_code == 200

    try:
        assert admin.get("/admin/config").json()["mode"] == "credential"
        login = admin.post(
            "/admin/session", json={"token": (data / "operator.token").read_text().strip()}
        )
        assert login.status_code == 200
        csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
        saved = admin.get("/admin/policy").json()["policy"]
        identity = json.loads(
            sql("SELECT identity FROM credentials WHERE digest=?", (credential_digest(parent),))[0][
                0
            ]
        )
        subject_role = "issuer-smoke-" + suffix
        grants = [
            {
                "operation": "documents.read",
                "resources": ["tenant-a-notes"],
                "classifications": ["internal"],
            },
            {
                "operation": "memory.query",
                "resources": ["demo-notes"],
                "classifications": ["internal"],
            },
            {"operation": "mail.send", "domains": ["demo.internal"]},
            {"operation": "chat.completions", "models": ["local-demo"]},
        ]
        delegation = {
            "profiles": [
                {"role_id": subject_role, "grants": grants},
                {"role_id": "analyst", "grants": grants},
            ],
            "required": [
                {
                    "tenant_id": identity["tenant_id"],
                    "agent_id": identity["agent_id"],
                    "operations": identity["operations"],
                }
            ],
        }
        policy = saved | {"delegation": delegation, "semantic_required": False}
        # Fixture cycles need a bounded root budget, not a reset of persistent usage.
        models = dict(policy["models"])
        models["max_input_bytes"] = 65536
        # Preserve uncertain admissions from failed fixture attempts. A temporary
        # bounded QA concurrency cap allows verification without resetting them.
        models["max_concurrent"] = 16
        for scope in ("root_run", "principal_day", "tenant_day"):
            models[scope] = {"calls": 1000, "tokens": 1000000, "micro_usd": 0}
        policy["models"] = models
        activate(policy)
        trust_row = sql("SELECT generation,config FROM issuer_trust WHERE id=1")
        old_trust = json.loads(trust_row[0][1]) if trust_row else {"version": 1, "profiles": []}
        generation = trust_row[0][0] if trust_row else 0
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {
            "kid": "fixture-" + suffix,
            "alg": "RS256",
            "use": "sig",
        }
        issuer = "https://issuer.invalid/" + suffix
        profile = {
            "profile_id": "fixture-" + suffix,
            "issuer": issuer,
            "audience": "agentgate-smoke",
            "keys": [jwk],
            "tenants": [{"value": "signed-tenant", "tenant_id": identity["tenant_id"]}],
            "groups": [
                {"value": "employees", "roles": [subject_role], "department": "fixture-department"}
            ],
            "parents": [
                {
                    "parent": credential_digest(parent),
                    "agent_id": identity["agent_id"],
                    "tenant_id": identity["tenant_id"],
                    "client_id": "fixture-client",
                }
            ],
            "max_assertion_age": 300,
            "max_auth_age": 300,
            "child_lifetime": 300,
        }
        config_path = ARTIFACTS / ("trust-" + suffix + ".json")
        private_json(config_path, {"version": 1, "profiles": [profile]})
        run_cli(
            "import-issuer-trust",
            "--config-file",
            str(config_path),
            "--expected-generation",
            str(generation),
        )
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": issuer,
                "sub": "fixture-person-" + suffix,
                "aud": "agentgate-smoke",
                "exp": now + 300,
                "iat": now,
                "nbf": now,
                "auth_time": now,
                "idtyp": "user",
                "client_id": "fixture-client",
                "tid": "signed-tenant",
                "groups": ["employees"],
            },
            key,
            algorithm="RS256",
            headers={"kid": jwk["kid"], "typ": "at+jwt"},
        )
        assertion_path = ARTIFACTS / ("assertion-" + suffix + ".token")
        child_path = ARTIFACTS / ("child-" + suffix + ".token")
        assertion_path.write_text(assertion)
        assertion_path.chmod(0o600)
        run_cli(
            "exchange-person-token",
            "--gateway",
            base,
            "--parent-token-file",
            str(data / "client.token"),
            "--access-token-file",
            str(assertion_path),
            "--output-token-file",
            str(child_path),
        )
        child = child_path.read_text().strip()
        assert child_path.stat().st_mode & 0o077 == 0
        headers = {"Authorization": "Bearer " + child}
        with httpx.Client(base_url=base, timeout=15, trust_env=False) as client:
            # Real protected read and denied read; only the permitted one dispatches.
            allow = client.post(
                "/v1/actions/execute",
                headers=headers,
                json={
                    "operation": "documents.read",
                    "arguments": {"document_id": "tenant-a-notes"},
                },
            )
            deny = client.post(
                "/v1/actions/execute",
                headers=headers,
                json={
                    "operation": "documents.read",
                    "arguments": {"document_id": "tenant-a-contact"},
                },
            )
            assert allow.status_code == 200 and allow.json()["executed"]
            assert "quarterly notes" in allow.json()["result"]["content"]
            assert deny.status_code == 403 and not deny.json()["executed"]
            # Existing installed adapters, each must perform model/tool/model.
            for adapter in ("direct-rest", "direct-mcp", "hermes-mcp"):
                before_seq = sql("SELECT COALESCE(MAX(sequence),0) FROM audit_events")[0][0]
                common = [
                    "--gateway",
                    base,
                    "--token-file",
                    str(child_path),
                    "--prompt",
                    "Read fixture notes",
                ]
                if adapter == "hermes-mcp":
                    command = [
                        str(state / "runtime/gateway/bin/agentgate-hermes"),
                        "--source",
                        str(hermes_source),
                        "run",
                        *common,
                    ]
                else:
                    command = [
                        str(state / "runtime/gateway/bin/agentgate-agent"),
                        *common,
                        "--transport",
                        adapter.split("-")[1],
                        "--state",
                        str(ARTIFACTS / (adapter + "-" + suffix + ".json")),
                    ]
                completed = subprocess.run(command, capture_output=True, timeout=320)
                result = json.loads(completed.stdout)
                if completed.returncode != 0:
                    reason = result.get("reason", "unknown_failure")
                    reason = (
                        reason
                        if isinstance(reason, str)
                        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", reason)
                        else "unsanitized_failure_withheld"
                    )
                    report["failure"] = {"adapter": adapter, "reason": reason}
                    raise AssertionError("Installed adapter failed: " + adapter + ": " + reason)
                assert result["status"] == "completed"
                events = [
                    json.loads(row[0])
                    for row in sql("SELECT event FROM audit_events WHERE sequence>?", (before_seq,))
                ]
                dispatch = {
                    op: sum(
                        e["event_type"] == "dispatch_intent" and e["operation"] == op
                        for e in events
                    )
                    for op in ("documents.read", "chat.completions")
                }
                assert dispatch == {"documents.read": 1, "chat.completions": 2}
                assert all(
                    e["root_run_id"] == identity["root_run_id"]
                    and e["principal_id"] == identity["principal_id"]
                    for e in events
                )
                assert all(e.get("authority", {}).get("version") == 2 for e in events)
                report["runs"].append(
                    {
                        "adapter": adapter,
                        "dispatches": dispatch,
                        "status": "pass",
                        "generator": "provider-fixture",
                    }
                )
            # The existing department consumer receives the transactional v2
            # attribution and actual settlement; its report never exposes people.
            measured = admin.get(
                "/admin/department-usage",
                params={
                    "tenant_id": identity["tenant_id"],
                    "start": now,
                    "end": int(time.time()) + 1,
                },
            )
            assert measured.status_code == 200
            usage = measured.json()
            assert usage["totals"]["attempts"] == usage["totals"]["attributed"] == 6
            assert usage["totals"]["settled"] == 6
            assert usage["totals"]["known_input_tokens"] == 120
            assert usage["totals"]["known_output_tokens"] == 18
            assert usage["departments"][0]["provenance"] == [
                {
                    "source": "issuer_asserted",
                    "authority_version": 2,
                    "issuer_id": profile["profile_id"],
                    "trust_version": generation + 1,
                }
            ]
            assert "human_subject" not in measured.text and issuer not in measured.text
            assert "fixture-person-" not in measured.text
            report["department_consumer"] = "minimized_v2_actual_settlement_pass"
            # Exact approved effect and replay proof in the installed outbox.
            arguments = {
                "recipient": "fixture@demo.internal",
                "subject": "Issuer fixture",
                "body": "Synthetic installed payload",
                "idempotency_key": "issuer-" + suffix,
            }
            initial_outbox = sql("SELECT COUNT(*) FROM tool_outbox")[0][0]
            proposed = client.post(
                "/v1/actions/execute",
                headers=headers,
                json={"operation": "mail.send", "arguments": arguments},
            )
            assert (
                proposed.status_code == 202
                and sql("SELECT COUNT(*) FROM tool_outbox")[0][0] == initial_outbox
            )
            aid = proposed.json()["action_id"]
            approval = next(
                row
                for row in admin.get(
                    "/admin/approvals", params={"tenant_id": identity["tenant_id"]}
                ).json()["approvals"]
                if row["action_id"] == aid
            )
            decision = admin.post(
                f"/admin/approvals/{aid}/decision",
                headers=csrf,
                json={
                    "tenant_id": identity["tenant_id"],
                    "fingerprint": approval["fingerprint"],
                    "approve": True,
                },
            )
            assert decision.status_code == 202
            assert decision.json()["action_state"] == "approved"
            assert decision.json()["executed"] is False
            assert sql("SELECT COUNT(*) FROM tool_outbox")[0][0] == initial_outbox
            for _ in range(2):
                resumed = client.post(f"/v1/actions/{aid}/resume", headers=headers, json={})
                assert resumed.status_code == 200 and resumed.json()["executed"]
            assert sql("SELECT COUNT(*) FROM tool_outbox")[0][0] == initial_outbox + 1
            # Issuance audit failure rolls back new subject/admission/binding/child.
            tables = (
                "credentials",
                "human_subjects",
                "delegated_bindings",
                "issuer_assertion_order",
                "issuer_admission",
                "issuer_events",
            )
            snapshot = [sql("SELECT * FROM " + table + " ORDER BY 1") for table in tables]
            rollback_assertion = jwt.encode(
                jwt.decode(
                    assertion, key.public_key(), algorithms=["RS256"], audience="agentgate-smoke"
                )
                | {"sub": "fixture-rollback-person-" + suffix},
                key,
                algorithm="RS256",
                headers={"kid": jwk["kid"], "typ": "at+jwt"},
            )
            with sqlite3.connect(database) as db:
                db.execute(
                    "CREATE TRIGGER issuer_smoke_audit_failure BEFORE INSERT ON issuer_events WHEN NEW.kind='child_issued' BEGIN SELECT RAISE(ABORT,'fixture audit failure'); END"
                )
            try:
                failed = client.post(
                    "/v1/authority/exchange",
                    headers={"Authorization": "Bearer " + parent},
                    json={"access_token": rollback_assertion},
                )
                assert failed.status_code == 503
                assert [
                    sql("SELECT * FROM " + table + " ORDER BY 1") for table in tables
                ] == snapshot
            finally:
                with sqlite3.connect(database) as db:
                    db.execute("DROP TRIGGER issuer_smoke_audit_failure")
            provider_before = json.loads(counts.read_text())["calls"]
            # Trust generation invalidates child at model and tool entry.
            run_cli(
                "import-issuer-trust",
                "--config-file",
                str(config_path),
                "--expected-generation",
                str(generation + 1),
            )
            assert (
                client.post(
                    "/v1/actions/execute",
                    headers=headers,
                    json={
                        "operation": "documents.read",
                        "arguments": {"document_id": "tenant-a-notes"},
                    },
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": "local-demo",
                        "messages": [{"role": "user", "content": "Denied fixture"}],
                    },
                ).status_code
                == 401
            )
            assert json.loads(counts.read_text())["calls"] == provider_before == 6
        report.update(
            status="pass",
            protected_outbox_delta=1,
            provider_fixture_calls=6,
            trust_revocation_nondispatch=True,
            audit_rollback=True,
        )
    finally:
        # Always close clients, delete ephemeral token files and retain a minimized
        # failure report, even if restoring one owned control fails.
        cleanup_errors = []
        try:
            if saved is not None:
                activate(saved)
        except Exception:
            cleanup_errors.append("policy_restore_failed")
        try:
            if old_trust is not None:
                restore_path = ARTIFACTS / ("restore-" + suffix + ".json")
                private_json(restore_path, old_trust)
                generation = sql("SELECT generation FROM issuer_trust WHERE id=1")[0][0]
                run_cli(
                    "import-issuer-trust",
                    "--config-file",
                    str(restore_path),
                    "--expected-generation",
                    str(generation),
                )
        except Exception:
            cleanup_errors.append("trust_restore_failed")
        try:
            if csrf:
                admin.delete("/admin/session", headers=csrf)
        finally:
            admin.close()
            if report["status"] != "pass" or cleanup_errors:
                report["status"] = "fail"
            if cleanup_errors:
                report["cleanup_errors"] = cleanup_errors
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            for path in ARTIFACTS.glob("*" + suffix + ".token"):
                path.unlink()
        if cleanup_errors:
            raise RuntimeError("Owned control restoration failed; see minimized report")
    print(
        json.dumps(
            {
                "status": report["status"],
                "kind": report["kind"],
                "report": str(report_path),
                "adapters": len(report["runs"]),
            }
        )
    )
    assert report["status"] == "pass"


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-provider", action="store_true")
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--base")
    parser.add_argument("--counts", type=Path)
    parser.add_argument(
        "--hermes-source", type=Path, default=Path(os.environ.get("AGENTGATE_HERMES_SOURCE", ""))
    )
    args = parser.parse_args()
    if args.fixture_provider:
        fixture_provider(args.port, args.state, args.counts)
    elif args.installed:
        installed_run(args.state, args.base, args.hermes_source)
    else:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [str(ROOT / ".ai/scripts/test-env-up.sh"), "--force-rebuild", "--no-local-console"],
                check=True,
                cwd=ROOT,
            )
            descriptor = json.loads((ROOT / ".ai/qa/test-env.json").read_text())
            assert descriptor["source"] == str(ROOT) and descriptor["startedByThisRepo"]
            state = Path(descriptor["stateDir"])
            # Stop only owned QA; then its supervisor launches the installed wheel
            # with a private deterministic provider in the same owned provider slot.
            subprocess.run(
                [str(ROOT / "laya"), "stop", "--state-dir", str(state)], check=True, cwd=ROOT
            )
            subprocess.run(
                [
                    str(state / "runtime/gateway/bin/python"),
                    "-I",
                    str(Path(__file__).resolve()),
                    "--installed",
                    "--state",
                    str(state),
                    "--base",
                    descriptor["baseUrl"],
                    "--hermes-source",
                    str(args.hermes_source.resolve()),
                ],
                check=True,
                cwd=ROOT,
            )
        finally:
            subprocess.run([str(ROOT / ".ai/scripts/test-env-down.sh")], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
