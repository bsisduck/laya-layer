import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../../node_modules/@open-mercato/cezar/dist/config.js";
import { loadWorkflows } from "../../node_modules/@open-mercato/cezar/dist/workflows/load.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const expected = JSON.parse(await readFile(new URL("../cezar/config.json", import.meta.url), "utf8"));
const config = await loadConfig(root);
for (const key of Object.keys(expected)) {
  assert.deepEqual(config[key], expected[key], `Cezar did not load configured ${key}`);
}
const { workflows, issues } = await loadWorkflows(root);
assert.deepEqual(issues, [], "Cezar reported an invalid workflow");
const workflow = workflows.find(({ name }) => name === "agentgate-local");
assert.ok(workflow, "Local AgentGate workflow is missing");
assert.ok(workflow.steps.some(({ command }) => command === "make validate"));
console.log("PASS: Cezar loaded the pinned skills source, Codex config, and local workflow");
