"""Installed authority/browser E2E; real local records and outbox, no inference.

Owns this checkout's descriptor lifecycle and ALWAYS stops its QA in finally.
Do not point it at a shared/primary installation. Evidence stays ignored.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".ai/qa/artifacts_authority"


def private_json(path, value):
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream)


def main(local_console=False):
    os.umask(0o077)
    artifacts = ARTIFACTS / ("local-console" if local_console else "credential")
    artifacts.mkdir(parents=True, exist_ok=True)
    saved = None
    admin = None
    csrf = None
    try:
        subprocess.run(
            [
                str(ROOT / ".ai/scripts/test-env-up.sh"),
                "--force-rebuild",
                "--local-console" if local_console else "--no-local-console",
            ],
            cwd=ROOT,
            check=True,
        )
        descriptor = json.loads((ROOT / ".ai/qa/test-env.json").read_text())
        assert descriptor["source"] == str(ROOT) and descriptor["startedByThisRepo"]
        assert descriptor["consoleMode"] == ("local" if local_console else "credential")
        installation = Path(descriptor["stateDir"])
        state = installation / "data"
        base = descriptor["baseUrl"]
        gateway = installation / "runtime/gateway/bin/agentgate"
        python = installation / "runtime/gateway/bin/python"
        imported = subprocess.check_output(
            [str(python), "-c", "import agentgate; print(agentgate.__file__)"], text=True
        ).strip()
        assert "site-packages" in imported and str(ROOT / "src") not in imported
        admin = httpx.Client(base_url=base, timeout=15, trust_env=False, headers={"Origin": base})
        login = admin.post(
            "/admin/session/bootstrap" if local_console else "/admin/session",
            json={} if local_console else {"token": (state / "operator.token").read_text().strip()},
        )
        assert login.status_code == 200
        csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
        current = admin.get("/admin/policy").json()
        saved = current["policy"]
        suffix = uuid.uuid4().hex[:12]
        subject = "qa-hr-" + suffix
        human_role = "qa-human-" + suffix
        delegation = {
            "version": 1,
            "required": [
                {
                    "tenant_id": "tenant-a",
                    "agent_id": "demo-client",
                    "operations": [
                        "documents.read",
                        "memory.query",
                        "mail.send",
                        "chat.completions",
                    ],
                }
            ],
            "profiles": [
                {
                    "role_id": role,
                    "grants": [
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
                    ],
                }
                for role in (human_role, "analyst")
            ],
        }
        candidate = saved | {"revision": saved["revision"] + 1, "delegation": delegation}
        activate = admin.post(
            "/admin/policy/activate",
            headers=csrf,
            json={"policy": candidate, "expected_version": current["version"]},
        )
        assert activate.status_code == 200
        record = artifacts / f"human-{suffix}.json"
        private_json(
            record,
            {
                "subject_id": subject,
                "tenant_id": "tenant-a",
                "roles": [human_role],
                "department": "HR",
                "revision": 1,
            },
        )
        child = artifacts / f"child-{suffix}.token"

        def command(*arguments):
            subprocess.run(
                [str(gateway), "--state-dir", str(state), *arguments],
                check=True,
                capture_output=True,
                text=True,
            )

        command("provision-local-human", "--record-file", str(record))
        command(
            "delegate-local",
            "--parent-token-file",
            str(state / "client.token"),
            "--subject",
            subject,
            "--output-token-file",
            str(child),
        )
        assert child.stat().st_mode & 0o777 == 0o600
        with httpx.Client(
            base_url=base,
            timeout=15,
            trust_env=False,
            headers={"Authorization": "Bearer " + child.read_text().strip()},
        ) as client:

            def execute(operation, arguments):
                return client.post(
                    "/v1/actions/execute", json={"operation": operation, "arguments": arguments}
                )

            assert execute("documents.read", {"document_id": "tenant-a-notes"}).status_code == 200
            denied = execute("documents.read", {"document_id": "tenant-a-contact"})
            assert denied.status_code == 403 and not denied.json()["executed"]
            memory = execute("memory.query", {"query": "Quarterly"})
            assert memory.status_code == 200 and all(
                r["entry_id"] == "demo-notes" for r in memory.json()["result"]["entries"]
            )
            # Globally supported alias has no human/agent grant: no provider call.
            model = client.post(
                "/v1/chat/completions",
                json={
                    "model": "local-demo",
                    "messages": [{"role": "user", "content": "No model permission"}],
                    "max_tokens": 1,
                },
            )
            assert model.status_code == 403 and not model.json()["executed"]
            parent_denial = client.post(
                "/v1/actions/execute",
                headers={"Authorization": "Bearer " + (state / "client.token").read_text().strip()},
                json={
                    "operation": "documents.read",
                    "arguments": {"document_id": "tenant-a-notes"},
                },
            )
            assert parent_denial.status_code == 403 and not parent_denial.json()["executed"]
            arguments = {
                "recipient": "review@demo.internal",
                "subject": "QA local authority " + suffix,
                "body": "Exact synthetic HR payload",
                "idempotency_key": "qa-authority-" + suffix,
            }
            proposed = execute("mail.send", arguments)
            assert proposed.status_code == 202 and not proposed.json()["executed"]
            action_id = proposed.json()["action_id"]
            with sqlite3.connect(state / "agentgate.sqlite3") as db:
                assert (
                    db.execute(
                        "SELECT COUNT(*) FROM tool_outbox WHERE action_id=?", (action_id,)
                    ).fetchone()[0]
                    == 0
                )
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
                    )
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base)
                    if local_console:
                        expect(page.locator("#topbar-mode")).to_have_text(
                            "Local console / trusted computer"
                        )
                        expect(page.get_by_label("Operator credential")).to_be_hidden()
                    else:
                        page.get_by_label("Operator credential").fill(
                            (state / "operator.token").read_text().strip()
                        )
                        page.get_by_role("button", name="Unlock console").click()
                    page.get_by_role("navigation").get_by_role(
                        "link", name="Approvals", exact=False
                    ).click()
                    card = page.locator("article.approval").filter(
                        has=page.get_by_role("heading", name=action_id, exact=True)
                    )
                    expect(card).to_be_visible()
                    expect(card).to_contain_text(subject)
                    expect(card).to_contain_text("analyst-demo")
                    expect(card).to_contain_text("local_demo")
                    card.screenshot(path=str(artifacts / "exact-approval.png"))
                    card.get_by_role("checkbox").check()
                    card.get_by_role("button", name="Approve exact action", exact=True).click()
                    expect(card).to_contain_text("Decision returned")
                    assert not errors and page.evaluate("Object.keys(localStorage).length") == 0
                    assert page.evaluate("Object.keys(sessionStorage).length") == 0
                    if not local_console:
                        page.get_by_role("button", name="Lock & sign out").click()
                finally:
                    browser.close()
            with sqlite3.connect(state / "agentgate.sqlite3") as db:
                assert (
                    db.execute(
                        "SELECT COUNT(*) FROM tool_outbox WHERE action_id=?", (action_id,)
                    ).fetchone()[0]
                    == 0
                )
            assert client.post(f"/v1/actions/{action_id}/resume", json={}).status_code == 200
            assert client.post(f"/v1/actions/{action_id}/resume", json={}).status_code == 200
            assert execute("mail.send", arguments | {"body": "mutated"}).status_code == 409
            command("revoke-local-credential", "--token-file", str(child))
            assert execute("documents.read", {"document_id": "tenant-a-notes"}).status_code == 401
            with sqlite3.connect(state / "agentgate.sqlite3") as db:
                outbox = db.execute(
                    "SELECT COUNT(*) FROM tool_outbox WHERE action_id=?", (action_id,)
                ).fetchone()[0]
                events = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT event FROM audit_events WHERE action_id=?", (action_id,)
                    )
                ]
                assert outbox == 1
                decisions = [e for e in events if e["event_type"] == "approval_decided"]
                assert len(decisions) == 1 and decisions[0]["approval_actor"]["mode"] == (
                    "local_console" if local_console else "credential"
                )
                assert decisions[0]["authority"]["human_subject"] == subject
                assert (
                    decisions[0]["principal_id"]
                    == decisions[0]["authority"]["accounting_principal"]
                    == "analyst-demo"
                )
                assert not db.execute(
                    "SELECT 1 FROM model_attempts WHERE action_id=?", (model.json()["action_id"],)
                ).fetchone()
                evidence = {
                    "console_mode": "local" if local_console else "credential",
                    "imported_module": imported,
                    "action_id": action_id,
                    "outbox_effects": outbox,
                    "approval_actor": decisions[0]["approval_actor"],
                    "authority": decisions[0]["authority"],
                    "denied_read": denied.json(),
                    "denied_model": model.json(),
                    "inference": "not run",
                }
                (artifacts / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(
            "PASS: installed local child; REST/read/model denials; browser exact approval; one outbox effect; replay/mutation/revocation; separate human/accounting/approver; no inference."
        )
    finally:
        try:
            if admin is not None and saved is not None:
                current = admin.get("/admin/policy").json()
                restore = admin.post(
                    "/admin/policy/activate",
                    headers=csrf,
                    json={
                        "policy": saved | {"revision": current["policy"]["revision"] + 1},
                        "expected_version": current["version"],
                    },
                )
                assert restore.status_code == 200, "QA policy restoration failed"
            if admin is not None:
                admin.delete("/admin/session", headers=csrf)
                admin.close()
        finally:
            subprocess.run([str(ROOT / ".ai/scripts/test-env-down.sh")], cwd=ROOT, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-console", action="store_true")
    main(parser.parse_args().local_console)
