"""Real HTTP integration evidence; classifier accuracy remains a separate result."""

import argparse
import json
import subprocess
from pathlib import Path

import httpx

from agentgate.inference_engine import PROFILES, QUESTION_SET
from agentgate.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=["laya_standard", "laya_coreml"], required=True)
    parser.add_argument("--gateway-port", type=int, required=True)
    parser.add_argument("--worker-port", type=int, required=True)
    parser.add_argument("--question-set", choices=list(PROFILES), default=QUESTION_SET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run_headers = {
        "Authorization": "Bearer " + (args.state_dir / "client.token").read_text().strip()
    }
    worker_headers = {
        "Authorization": "Bearer " + (args.state_dir / "worker.token").read_text().strip()
    }
    gateway = f"http://127.0.0.1:{args.gateway_port}"
    worker = f"http://127.0.0.1:{args.worker_port}/internal/v1/semantic"
    report = {
        "kind": "real_semantic_http_integration",
        "backend": args.backend,
        "question_set_id": args.question_set,
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "actions": [],
        "classification": [],
    }
    with httpx.Client(timeout=10, trust_env=False) as client:
        assert client.get(gateway + "/health/ready").status_code == 200
        assert client.get(worker + "/ready").status_code == 401
        capabilities = client.get(worker + "/ready", headers=worker_headers)
        assert capabilities.status_code == 200
        report["capabilities"] = capabilities.json()
        assert capabilities.json()["question_set_id"] == args.question_set
        before = client.get(worker + "/budget", headers=worker_headers).json()
        if args.question_set == "content-role-v2":
            for version in ("content-role-v1", "unknown"):
                mismatch = client.post(
                    worker + "/evaluate",
                    headers=worker_headers,
                    json={
                        "request_id": "mismatch",
                        "question_set_id": version,
                        "untrusted_content": "data",
                    },
                )
                assert mismatch.status_code == 422
            assert client.get(worker + "/budget", headers=worker_headers).json() == before
            report["mismatched_versions_rejected_before_quota"] = True
        for document, reason in [
            ("tenant-a-notes", None),
            ("tenant-a-instructions", None),
            ("tenant-b-notes", "RESOURCE_NOT_ALLOWED"),
            ("tenant-a-leak", "SECRET_IN_OUTPUT"),
        ]:
            response = client.post(
                gateway + "/v1/actions/execute",
                headers=run_headers,
                json={"operation": "documents.read", "arguments": {"document_id": document}},
            )
            body = response.json()
            event = next(
                event
                for event in reversed(Store(args.state_dir / "agentgate.sqlite3").events())
                if event.action_id == body["action_id"]
            )
            if reason:
                assert body["reason_codes"] == [reason]
                assert event.semantic is None
            else:
                assert event.semantic is not None and event.semantic.backend == args.backend
                assert event.semantic.question_set_id == args.question_set
                label = event.semantic.selected_labels["content_role"]
                expected = {
                    "task_data": "ALLOWED",
                    "behavior_instruction": "SEMANTIC_BLOCKED",
                    "unclear": "SEMANTIC_ABSTAIN",
                }[label]
                assert body["reason_codes"] == [expected]
                if args.question_set == "content-role-v2":
                    wanted = "ALLOWED" if document == "tenant-a-notes" else "SEMANTIC_BLOCKED"
                    assert body["reason_codes"] == [wanted]
                    assert ("result" in body) == (wanted == "ALLOWED")
                    assert response.status_code == (200 if wanted == "ALLOWED" else 403)
                    assert set(event.semantic.raw_scores) == {"task_data", "behavior_instruction"}
            if document == "tenant-b-notes":
                assert body["executed"] is False
            report["actions"].append(
                {
                    "document": document,
                    "http": response.status_code,
                    "reasons": body["reason_codes"],
                    "executed": body["executed"],
                    "semantic": event.semantic.model_dump(mode="json") if event.semantic else None,
                }
            )
        fixtures = json.loads(Path("tests/fixtures/semantic-loading.json").read_text())
        for case in fixtures["cases"]:
            response = client.post(
                worker + "/evaluate",
                headers=worker_headers,
                json={
                    "request_id": "smoke-" + case["id"],
                    "question_set_id": args.question_set,
                    "untrusted_content": case["state"],
                },
            )
            assert response.status_code == 200
            result = response.json()
            actual = result["selected_labels"]["content_role"]
            report["classification"].append(
                {
                    "id": case["id"],
                    "expected": case["expected"],
                    "actual": actual,
                    "matches": actual == case["expected"],
                    "result": result,
                }
            )
        response = client.post(
            worker + "/evaluate",
            headers=worker_headers,
            json={
                "request_id": "smoke-over-capacity",
                "question_set_id": args.question_set,
                "untrusted_content": "word " * 3000,
            },
        )
        result = response.json()
        assert response.status_code == 200 and result["status"] == "incomplete"
        assert result["coverage"]["windows_evaluated"] == 0
        report["over_capacity"] = result
        after = client.get(worker + "/budget", headers=worker_headers).json()
        report["semantic_calls_admitted"] = after["calls"] - before["calls"]
        assert report["semantic_calls_admitted"] == 2 + len(fixtures["cases"]) + 1
    suffix = "" if args.question_set == QUESTION_SET else "-" + args.question_set
    output = args.output or Path("reports/generated") / f"{args.backend}-gateway{suffix}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "status": "integration_pass",
                "backend": args.backend,
                "classification_matches": sum(case["matches"] for case in report["classification"]),
                "classification_cases": len(report["classification"]),
                "report": str(output),
            }
        )
    )


if __name__ == "__main__":
    main()
