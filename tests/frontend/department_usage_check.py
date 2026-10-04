"""Owned installed browser E2E, labelled HTTP fixture behind private LiteLLM.

No real model inference. Retains QA evidence; restores controls/config and tears
down only this worktree's installation, browser and fixture server in finally.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def private_file(path, value):
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write(value)


def main(local_console=False):
    os.umask(0o077)
    suffix = uuid.uuid4().hex[:12]
    artifacts = ROOT / ".ai/qa/artifacts_department" / suffix
    artifacts.mkdir(parents=True)
    saved_policy = saved_proxy = proxy_file = admin = csrf = server = thread = None
    tenant = "usage-" + suffix
    calls = []
    started = time.monotonic()
    try:
        subprocess.run(
            [
                str(ROOT / ".ai/scripts/test-env-up.sh"),
                "--local-console" if local_console else "--no-local-console",
            ],
            cwd=ROOT,
            check=True,
        )
        descriptor = json.loads((ROOT / ".ai/qa/test-env.json").read_text())
        assert descriptor["source"] == str(ROOT) and descriptor["startedByThisRepo"]
        installation = Path(descriptor["stateDir"])
        state = installation / "data"
        database = state / "agentgate.sqlite3"
        base = descriptor["baseUrl"]
        python = installation / "runtime/gateway/bin/python"
        gateway = installation / "runtime/gateway/bin/agentgate"
        imported = subprocess.check_output(
            [str(python), "-c", "import agentgate; print(agentgate.__file__)"], text=True
        ).strip()
        assert "site-packages" in imported and str(ROOT / "src") not in imported

        class Fixture(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                text = payload["messages"][-1]["content"]
                calls.append(text)
                if text == "fixture-unknown":
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        b'{"error":{"message":"deterministic fixture unknown outcome"}}'
                    )
                    return
                out = 10000000 if text == "fixture-overrun" else 3
                content = (
                    "AGENTGATE_SECRET[fixture-only]"
                    if text == "fixture-output-denied"
                    else "Deterministic fixture provider response"
                )
                response = {
                    "id": "fixture-" + uuid.uuid4().hex,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "department-fixture",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": out,
                        "total_tokens": 20 + out,
                    },
                }
                body = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def product(command):
            subprocess.run(
                [str(ROOT / "laya"), command, "--state-dir", str(installation)],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )

        proxy_file = state / "litellm.yaml"
        saved_proxy = proxy_file.read_bytes()
        product("stop")
        # Only this stopped QA proxy is changed; shared Ollama is never invoked.
        proxy_file.write_text(
            json.dumps(
                {
                    "model_list": [
                        {
                            "model_name": "local-demo",
                            "litellm_params": {
                                "model": "openai/department-fixture",
                                "api_base": f"http://127.0.0.1:{server.server_port}/v1",
                                "api_key": "fixture-only",
                                "timeout": 5,
                            },
                        }
                    ],
                    "router_settings": {"num_retries": 0, "timeout": 5, "fallbacks": []},
                    "litellm_settings": {
                        "num_retries": 0,
                        "request_timeout": 5,
                        "telemetry": False,
                        "set_verbose": False,
                        "turn_off_message_logging": True,
                        "drop_params": False,
                        "success_callback": [],
                        "failure_callback": [],
                    },
                    "general_settings": {
                        "master_key": "os.environ/LITELLM_MASTER_KEY",
                        "disable_spend_logs": True,
                    },
                }
            )
        )
        product("start")
        admin = httpx.Client(base_url=base, timeout=15, trust_env=False, headers={"Origin": base})
        path = f"/admin/department-usage?tenant_id={tenant}&start=1&end=2"
        assert admin.get(path).status_code == 401
        login = admin.post(
            "/admin/session/bootstrap" if local_console else "/admin/session",
            json={} if local_console else {"token": (state / "operator.token").read_text().strip()},
        )
        assert login.status_code == 200
        csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
        saved_policy = admin.get("/admin/policy").json()["policy"]
        human_role, agent_role = "human-" + suffix, "agent-" + suffix

        def activate(document):
            current = admin.get("/admin/policy").json()
            response = admin.post(
                "/admin/policy/activate",
                headers=csrf,
                json={
                    "policy": document | {"revision": current["policy"]["revision"] + 1},
                    "expected_version": current["version"],
                },
            )
            assert response.status_code == 200
            return response.json()["policy"]

        delegation = saved_policy.get("delegation") or {
            "version": 1,
            "profiles": [],
            "required": [],
        }
        delegation = delegation | {
            "profiles": delegation["profiles"]
            + [
                {
                    "role_id": role,
                    "grants": [{"operation": "chat.completions", "models": ["local-demo"]}],
                }
                for role in (human_role, agent_role)
            ]
        }
        limits = {"calls": 1000, "tokens": 10**9, "micro_usd": 10**12}
        policy = activate(
            saved_policy
            | {
                "delegation": delegation,
                "models": saved_policy["models"]
                | {
                    "tenant_day": limits,
                    "principal_day": limits,
                    "root_run": limits,
                    "max_concurrent": 16,
                    "input_micro_usd": 7,
                    "output_micro_usd": 11,
                },
            }
        )
        parent = artifacts / "parent.token"
        identity = {
            "principal_id": "owner-" + suffix,
            "tenant_id": tenant,
            "agent_id": "agent-" + suffix,
            "root_run_id": "root-" + suffix,
            "roles": [agent_role],
            "operations": ["chat.completions"],
        }
        subprocess.run(
            [
                str(python),
                "-c",
                "import os,json,time,sys; from pathlib import Path; from agentgate.storage import Store; from agentgate.contracts import Identity; t=Store(Path(sys.argv[1])).issue(Identity.model_validate_json(sys.argv[3]),time.time()+3600); fd=os.open(sys.argv[2],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,t.encode()); os.close(fd)",
                str(database),
                str(parent),
                json.dumps(identity),
            ],
            check=True,
            capture_output=True,
        )

        def command(*args):
            subprocess.run(
                [str(gateway), "--state-dir", str(state), *args], check=True, capture_output=True
            )

        children = []
        for department in ("Research", "Support"):
            subject = "subject-" + department + "-" + suffix
            record, child = artifacts / (department + ".json"), artifacts / (department + ".token")
            private_file(
                record,
                json.dumps(
                    {
                        "subject_id": subject,
                        "tenant_id": tenant,
                        "roles": [human_role],
                        "department": department,
                        "revision": 1,
                    }
                ),
            )
            command("provision-local-human", "--record-file", str(record))
            command(
                "delegate-local",
                "--parent-token-file",
                str(parent),
                "--subject",
                subject,
                "--output-token-file",
                str(child),
            )
            children.append(child)

        period_start = int(time.time()) - 1

        def call(token_file, text="fixture-success", **changes):
            return admin.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer " + token_file.read_text().strip()},
                json={
                    "model": "local-demo",
                    "messages": [{"role": "user", "content": text}],
                    "max_tokens": 64,
                }
                | changes,
            )

        assert (
            call(children[0]).status_code
            == call(children[1]).status_code
            == call(parent).status_code
            == 200
        )
        blocked = call(children[0], "fixture-output-denied")
        assert (
            blocked.status_code == 403
            and blocked.json()["executed"]
            and "AGENTGATE_SECRET" not in blocked.text
        )
        assert call(children[0], model="forbidden").status_code == 403
        assert call(parent, department="forged").status_code == 422
        assert len(calls) == 4
        with sqlite3.connect(database) as db:
            spent_before = db.execute(
                "SELECT scope,scope_key,resource,spent FROM model_accounts ORDER BY scope,scope_key,resource"
            ).fetchall()
            db.execute(
                "CREATE TRIGGER qa_department_rollback BEFORE INSERT ON model_settlement WHEN EXISTS(SELECT 1 FROM model_attempts WHERE action_id=NEW.action_id AND tenant_id='"
                + tenant
                + "') BEGIN SELECT RAISE(ABORT,'QA fixture settlement failure'); END"
            )
        try:
            rollback = call(parent, "fixture-rollback")
            assert rollback.status_code == 503
            with sqlite3.connect(database) as db:
                assert (
                    db.execute(
                        "SELECT scope,scope_key,resource,spent FROM model_accounts ORDER BY scope,scope_key,resource"
                    ).fetchall()
                    == spent_before
                )
                assert (
                    db.execute(
                        "SELECT state FROM model_attempts WHERE action_id=?",
                        (rollback.json()["action_id"],),
                    ).fetchone()[0]
                    == "dispatched"
                )
                assert (
                    db.execute(
                        "SELECT COUNT(*) FROM model_settlement WHERE action_id=?",
                        (rollback.json()["action_id"],),
                    ).fetchone()[0]
                    == 0
                )
                assert (
                    db.execute(
                        "SELECT COUNT(*) FROM audit_events WHERE action_id=?",
                        (rollback.json()["action_id"],),
                    ).fetchone()[0]
                    == 1
                )
        finally:
            with sqlite3.connect(database) as db:
                db.execute("DROP TRIGGER IF EXISTS qa_department_rollback")
        unknown = call(parent, "fixture-unknown")
        assert unknown.status_code == 503
        # Admitted one-output-token reservation, then huge validated actual usage.
        tariff = 10**12 - 1000000
        policy = activate(
            policy
            | {"models": policy["models"] | {"input_micro_usd": 0, "output_micro_usd": tariff}}
        )
        overrun = call(parent, "fixture-overrun", max_tokens=1)
        assert overrun.status_code == 503
        assert call(parent).status_code == 429
        assert len(calls) == 7
        period_end = int(time.time()) + 2
        query = f"/admin/department-usage?tenant_id={tenant}&start={period_start}&end={period_end}"
        data = admin.get(query).json()
        t = data["totals"]
        assert (
            t["attempts"] == 7
            and t["known_usage_attempts"] == 5
            and t["unknown_usage_attempts"] == 2
        )
        assert t["settled"] == 5 and t["uncertain"] == t["dispatch_intent"] == 1
        exact = str(4 * 173 + 10000000 * tariff)
        assert t["known_simulated_micro_usd"] == exact and t["over_bound_attempts"] == 1
        assert t["outstanding_calls"] == 2 and t["outstanding_input_tokens"] > 0
        assert {b["department"] for b in data["departments"]} == {None, "Research", "Support"}
        with sqlite3.connect(database) as db:
            actual = db.execute(
                "SELECT s.input_tokens,s.output_tokens,s.simulated_micro_usd FROM model_settlement s JOIN model_attempts a USING(action_id) WHERE a.tenant_id=?",
                (tenant,),
            ).fetchall()
            assert sum(int(r[2]) for r in actual) == int(exact)
            assert sum(r[0] for r in actual) == t["known_input_tokens"] == 100
            assert sum(r[1] for r in actual) == t["known_output_tokens"] == 10000012
            assert (
                db.execute(
                    "SELECT COUNT(DISTINCT accounting_principal) FROM model_attribution p JOIN model_attempts a USING(action_id) WHERE a.tenant_id=?",
                    (tenant,),
                ).fetchone()[0]
                == 1
            )
            assert all(
                r[0] == "text"
                for r in db.execute(
                    "SELECT typeof(spent) FROM model_accounts WHERE resource='micro_usd' AND scope_key LIKE ?",
                    ('%"' + tenant + '"%',),
                )
            )

        product("stop")
        product("start")
        assert admin.get(query).json() == data, "Installed restart changed persisted evidence"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                shell_started = time.monotonic()
                page.goto(base)
                if local_console:
                    expect(page.get_by_label("Operator credential")).to_be_hidden()
                else:
                    page.get_by_label("Operator credential").fill(
                        (state / "operator.token").read_text().strip()
                    )
                    page.get_by_role("button", name="Unlock console").click()
                section = page.locator("section").filter(
                    has=page.get_by_role("heading", name="Department model usage", exact=True)
                )
                expect(section.get_by_role("button", name="Load usage")).to_be_enabled()
                shell_seconds = round(time.monotonic() - shell_started, 3)
                page.get_by_label("Department report tenant").fill(tenant)
                page.get_by_label("UTC start", exact=True).fill(
                    time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(period_start))
                )
                page.get_by_label("UTC end", exact=True).fill(
                    time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(period_end))
                )
                page.get_by_label("Department report tenant").press("Enter")
                expect(
                    section.get_by_text(exact + " · 5/7 contributing attempts", exact=True)
                ).to_be_visible()
                expect(section.get_by_role("row").filter(has_text="Research")).to_have_count(1)
                expect(section.get_by_role("row").filter(has_text="Support")).to_have_count(1)
                expect(section.get_by_text("Unknown / unassigned", exact=True)).to_be_visible()
                expect(section).to_contain_text("local_demo · trusted local demo subject")
                expect(
                    page.get_by_role("heading", name="Standards controls, evidence and gaps")
                ).to_be_visible()
                section.screenshot(path=str(artifacts / "desktop.png"))
                page.get_by_role("button", name="Refresh", exact=False).click()
                page.get_by_text("Full budget evidence", exact=True).click()
                expect(page.locator("pre").filter(has_text=exact)).to_be_visible()
                # Reload exact period after refreshing the overview shell.
                page.get_by_label("Department report tenant").fill(tenant)
                page.get_by_role("button", name="Load usage", exact=True).click()
                held = []
                page.route("**/admin/department-usage?*", lambda route: held.append(route))
                page.get_by_role("button", name="Load usage", exact=True).click()
                expect(section.get_by_text("Loading department usage…", exact=True)).to_be_visible()
                expect(section.get_by_role("button", name="Load usage")).to_be_disabled()
                assert len(held) == 1
                held[0].continue_()
                page.unroute("**/admin/department-usage?*")
                expect(section.get_by_role("button", name="Load usage")).to_be_enabled()
                page.route(
                    "**/admin/department-usage?*",
                    lambda route: route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"fixture unavailable"}',
                    ),
                )
                page.get_by_role("button", name="Load usage", exact=True).click()
                expect(
                    section.get_by_text(
                        "No current department data. Check the period and service, then load usage again.",
                        exact=True,
                    )
                ).to_be_visible()
                page.unroute("**/admin/department-usage?*")
                page.get_by_label("Department report tenant").fill("empty-" + suffix)
                page.get_by_role("button", name="Load usage", exact=True).click()
                expect(
                    section.get_by_text(
                        "No model attempts in this tenant and reservation period.", exact=True
                    )
                ).to_be_visible()
                page.get_by_label("Department report tenant").fill(tenant)
                page.get_by_role("button", name="Load usage", exact=True).click()
                expect(section).to_contain_text(exact)
                page.set_viewport_size({"width": 390, "height": 844})
                expect(section.get_by_role("button", name="Load usage")).to_be_visible()
                section.get_by_role("region", name="Scrollable records").focus()
                expect(section.get_by_role("region", name="Scrollable records")).to_be_focused()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                section.screenshot(path=str(artifacts / "mobile.png"))
                assert (
                    not errors
                    and page.evaluate(
                        "Object.keys(localStorage).length + Object.keys(sessionStorage).length"
                    )
                    == 0
                )
                if not local_console:
                    page.get_by_role("button", name="Lock & sign out").click()
            except Exception:
                page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
                raise
            finally:
                browser.close()
        (artifacts / "result.json").write_text(
            json.dumps(
                {
                    "fixture_provider": "HTTP deterministic fixture behind installed private LiteLLM; no real inference",
                    "mode": "local" if local_console else "credential",
                    "imported_module": imported,
                    "report": data,
                    "provider_calls": len(calls),
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "initial_authenticated_shell_seconds": shell_seconds,
                    "restart_evidence_unchanged": True,
                },
                indent=2,
            )
        )
        print(
            f"PASS: installed {('local' if local_console else 'credential')} mode, seven persisted fixture attempts, five known/two unknown, exact {exact} simulated micro-USD, rollback/freeze/denied effects, UI totals/loading/error/empty/mobile/auth."
        )
    finally:
        try:
            if admin is not None:
                if saved_policy is not None:
                    current = admin.get("/admin/policy").json()
                    result = admin.post(
                        "/admin/policy/activate",
                        headers=csrf,
                        json={
                            "policy": saved_policy
                            | {"revision": current["policy"]["revision"] + 1},
                            "expected_version": current["version"],
                        },
                    )
                    assert result.status_code == 200, "Owned QA policy restoration failed"
                if csrf is not None:
                    admin.delete("/admin/session", headers=csrf)
                admin.close()
        finally:
            try:
                subprocess.run([str(ROOT / ".ai/scripts/test-env-down.sh")], cwd=ROOT, check=True)
                if saved_proxy is not None:
                    proxy_file.write_bytes(saved_proxy)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-console", action="store_true")
    main(parser.parse_args().local_console)
