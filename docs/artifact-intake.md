# Safe artifact intake demonstration

`agentgate-artifacts` checks a proposed metadata manifest against an operator's
exact approved registry and the current threat feed. It never fetches the URL,
opens checkpoint bytes, loads a serializer or executes model code. Output always
identifies `metadata_policy_simulation`, `bytes_verified: false` and
`artifact_executed: false`. This demonstrates the architecture T35/T36 control
class; it is not a TorchServe exploit or a certification that model bytes are safe.

```sh
uv run agentgate-artifacts config/artifact-demo/approved.json \
  --approved config/artifact-demo/registry.json \
  --feed config/artifact-demo/feed.json
```

The synthetic fixture uses a reserved `.invalid` hostname and placeholder hashes.
Exit 0 means that exact asset ID, pinned revision, SHA-256, canonical HTTPS source
and serialization tuple is registered and not blocked. Run the same command with
`changed-digest.json`, `unapproved-source.json`, or `unsafe-serializer.json` for
exit 2 policy denials. Exit 1 means invalid/missing metadata. No arbitrary remote
code loader is accepted, and executable serialization cannot enter the registry.

Use `--state-dir /path/to/installation/state` instead of `--feed` to read the
currently activated operator feed. Adding its digest/source/domain at the
`artifact_intake` stage can revoke even an exact approved manifest. This local
operator check does not alter installation state or emit an execution audit event.
Agent REST/MCP discovery provides no artifact-import operation or permission.

The approved registry is separate from the incoming manifest. Operators own its
contents and revision; maximum 32 unique asset/revision entries and 64 KiB per
input file. Duplicate JSON keys, unknown fields, unpinned revisions and malformed
sources fail closed. Copying an attacker's manifest into the approved registry
would grant approval and is outside this trust boundary. Actual offline assets
continue to require the existing downloader's pinned file-digest verification;
a claimed digest in this simulator does not verify any bytes.

`tests/test_artifacts.py` verifies exact approval, changed metadata, all rejected
executable serializers, active-feed revocation, CLI outcomes and absence of
artifact I/O. A future production intake system would additionally verify bytes,
provenance and reviewed loaders in a quarantined process.
