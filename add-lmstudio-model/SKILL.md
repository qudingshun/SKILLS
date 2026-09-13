---
name: "add-lmstudio-model"
description: "Add a model served by local LM Studio to OpenClaw config and prove it. Trigger: 把模型加到配置, 检查LMSTUDIO新增了哪些模型, qwen3-sex 配置"
---

# Add an LM Studio model to OpenClaw config

Use when the user asks to add a model that the local LM Studio serves (for example "把 qwen3-sex 加到配置里", "检查LMSTUDIO的接口新增了哪些模型，添加它到配置中"), or asks which new models LM Studio now exposes.

## Steps

1. List the models LM Studio actually serves:
   ```
   Invoke-RestMethod -Uri "http://127.0.0.1:1234/v1/models" | ConvertTo-Json -Depth 5
   ```
   Use `/v1/models`; the bare `/models` path returns "Unexpected endpoint or method". Completion: the requested model id appears in `data[].id`; note any other new ids to report.

2. Read the current provider block so existing entries survive the rewrite:
   ```
   openclaw config get models --json
   ```
   Completion: you hold every existing entry under the target provider (id, name, reasoning, input, contextWindow, maxTokens, cost, api).

3. Write a config-shaped patch file that replaces the provider's `models` array with all existing entries plus the new one:
   ```
   { "models": { "providers": { "<provider>": { "models": [ ...existing entries..., { "id": "<new-id>", "name": "<display name>", "reasoning": false, "input": ["text"], "contextWindow": 131072, "maxTokens": 131072, "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }, "api": "openai-completions" } ] } } } }
   ```
   Key rule: `config patch` takes config-shaped JSON — top-level keys are config keys such as `models`. A full config object (`{ "mode": ..., "providers": ... }`) is rejected with "Unrecognized keys". Arrays replace wholesale while objects merge recursively, so only the `models` array needs the complete list. Completion: patch file written.

4. Dry-run, then apply:
   ```
   openclaw config patch --file <patch-file> --dry-run --json
   openclaw config patch --file <patch-file>
   ```
   Expect `"ok": true` on dry-run and "Change will apply without restarting the gateway" on apply. Completion: exit 0 with no schema errors.

5. When probes are blocked by the model policy, extend the allow list:
   ```
   openclaw config get agents.defaults.modelPolicy.allow --json
   ```
   Add the new id through a batch file — PowerShell mangles inline JSON arrays for `--strict-json`, so always use a file:
   ```
   [ { "path": "agents.defaults.modelPolicy.allow", "value": [ ...all existing allow ids..., "<provider>/<new-id>" ] } ]
   ```
   ```
   openclaw config set --batch-file <batch.json> --dry-run --json
   openclaw config set --batch-file <batch.json>
   ```
   Completion: `openclaw models list --agent main` shows the new id tagged `configured`.

6. Prove the model answers:
   - Fast direct check: POST `http://127.0.0.1:1234/v1/chat/completions` with body `{"model":"<new-id>","messages":[{"role":"user","content":"Reply with exactly: PROVIDER-PROOF-OK"}],"max_tokens":20}`; expect the exact string `PROVIDER-PROOF-OK`.
   - Gateway check: `openclaw infer model run --gateway --model <provider>/<new-id> --prompt "Reply with exactly: PROVIDER-PROOF-OK"`.
   The first call can be slow while LM Studio loads the model into memory; a timeout on the first probe is not a failure — retry once with a longer timeout before concluding the route is broken.
