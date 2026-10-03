"""A genuine bounded model → discovered tool → model client, without local tools."""

import argparse
import asyncio
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from agentgate.agents.client import MAX_BYTES, ClientFailure, GatewayClient, decode


def private_read(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > MAX_BYTES:
                raise ClientFailure("file_must_be_private_and_bounded")
            return stream.read(MAX_BYTES + 1)
    except OSError as error:
        raise ClientFailure("private_file_unavailable") from error


def save_state(path: Path, state: dict[str, Any]) -> None:
    data = json.dumps(state, ensure_ascii=False)
    if len(data.encode()) > MAX_BYTES:
        raise ClientFailure("conversation_too_large")
    # State contains inspected transcript, not credentials; owner-only, no overwrite.
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(data)
    except OSError as error:
        raise ClientFailure("state_path_exists_or_unavailable") from error


class DirectAgent:
    def __init__(
        self,
        client: GatewayClient,
        *,
        model: str = "local-demo",
        transport: str = "rest",
        max_turns: int = 6,
        max_tokens: int = 256,
    ) -> None:
        if (
            not 2 <= max_turns <= 16
            or not 1 <= max_tokens <= 4096
            or transport not in ("rest", "mcp")
        ):
            raise ClientFailure("invalid_run_bounds")
        self.client, self.model, self.transport = client, model, transport
        self.max_turns, self.max_tokens = max_turns, max_tokens

    async def run(self, prompt: str, *, state: dict[str, Any] | None = None) -> dict[str, Any]:
        tools = await self.client.discover()
        status, models, _ = await self.client.request("GET", "/v1/models")
        if status != 200 or self.model not in [m.get("id") for m in models.get("data", [])]:
            raise ClientFailure("model_not_discovered")
        if state is None:
            state = {"messages": [{"role": "user", "content": prompt}], "turns": 0, "seen": []}
        elif state.get("pending"):
            pending = state["pending"]
            result = await self.client.resume(pending["action_id"])
            if result.get("status") == "pending_approval":
                return {"status": "pending_approval", "state": state}
            self.append_result(state, pending["call_id"], result)
            del state["pending"]
        else:
            raise ClientFailure("only_pending_actions_can_resume")
        while state["turns"] < self.max_turns:
            if len(json.dumps(state).encode()) > MAX_BYTES or len(state["messages"]) > 60:
                raise ClientFailure("conversation_too_large")
            payload = {
                "model": self.model,
                "messages": state["messages"],
                "max_tokens": self.max_tokens,
                "temperature": 0,
                "stream": False,
            }
            if tools:
                payload["tools"] = tools
            response = await self.client.complete(payload)
            state["turns"] += 1
            try:
                choice = response["choices"][0]
                message = choice["message"]
                calls = message.get("tool_calls")
                if message.get("role") != "assistant":
                    raise ClientFailure("invalid_assistant")
                if not calls:
                    if choice.get("finish_reason") != "stop" or not isinstance(
                        message.get("content"), str
                    ):
                        raise ClientFailure("incomplete_model_response")
                    return {
                        "status": "completed",
                        "text": message["content"],
                        "turns": state["turns"],
                    }
                if len(calls) != 1 or state["turns"] == self.max_turns:
                    raise ClientFailure("turn_or_tool_limit")
                call = calls[0]
                call_id, name = call["id"], call["function"]["name"]
                if (
                    not isinstance(call_id, str)
                    or not 1 <= len(call_id) <= 128
                    or call_id in state["seen"]
                ):
                    raise ClientFailure("invalid_or_repeated_call_id")
                arguments = decode(call["function"]["arguments"])
            except (KeyError, IndexError, TypeError) as error:
                raise ClientFailure("invalid_completion") from error
            state["seen"].append(call_id)
            # Preserve the complete inspected assistant tool proposal and exact ID.
            state["messages"].append(message)
            result = await self.client.execute(name, arguments, transport=self.transport)
            if result.get("status") == "pending_approval" and result.get("executed") is False:
                state["pending"] = {"action_id": result["action_id"], "call_id": call_id}
                return {"status": "pending_approval", "state": state}
            self.append_result(state, call_id, result)
        raise ClientFailure("turn_limit")

    @staticmethod
    def append_result(state: dict[str, Any], call_id: str, result: dict[str, Any]) -> None:
        if result.get("status") != "completed" or result.get("executed") is not True:
            raise ClientFailure("tool_not_completed_no_retry")
        state["messages"].append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            }
        )


async def cli_run(args: argparse.Namespace) -> dict[str, Any]:
    token = private_read(args.token_file).strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    client = GatewayClient(args.gateway, token)
    binding = {
        "gateway": client.origin,
        "credential_sha256": digest,
        "model": args.model,
        "transport": args.transport,
        "max_turns": args.max_turns,
        "max_tokens": args.max_tokens,
    }
    state = None
    if args.resume:
        saved = decode(private_read(args.resume))
        if saved.get("binding") != binding:
            raise ClientFailure("resume_binding_mismatch")
        state = saved["state"]
    try:
        async with asyncio.timeout(300):
            result = await DirectAgent(
                client,
                model=args.model,
                transport=args.transport,
                max_turns=args.max_turns,
                max_tokens=args.max_tokens,
            ).run(args.prompt or "", state=state)
        if result["status"] == "pending_approval":
            save_state(args.state, {"binding": binding, "state": result.pop("state")})
            result["state_file"] = str(args.state)
        result["trace"] = client.traces
        return result
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gateway", required=True, help="Explicit loopback origin, e.g. http://127.0.0.1:8080"
    )
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--model", default="local-demo")
    parser.add_argument("--transport", choices=("rest", "mcp"), default="rest")
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=256)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt")
    source.add_argument("--resume", type=Path)
    parser.add_argument(
        "--state",
        type=Path,
        required=True,
        help="New private pending-state file; never overwritten",
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(cli_run(args))
    except (ClientFailure, TimeoutError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": str(error)
                    if isinstance(error, ClientFailure)
                    else "deadline_no_retry",
                }
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] == "pending_approval":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
