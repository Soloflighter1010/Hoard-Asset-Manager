# Architecture roadmap implementation

This branch implements the code foundations in #315 and its linked issues. The
table separates implemented behavior from evidence that still needs a native
machine or CI run. It is not a claim that every acceptance criterion is complete.

| Issue | Implementation and review guide |
| --- | --- |
| #316 | Isolated test homes restore imported aliases; an audit hook catches writes to an earlier fixture. Whole-module CI shards run twice with different shuffle seeds in the same interpreter. JSON summaries retain timings and failures. See [ARCHITECTURE](ARCHITECTURE.md#tests-and-dependencies). A comparable hosted-CI before/after wall-time result remains to be collected. |
| #317 | Versioned public export [schemas](DATA-FORMATS.md), shared Python/C# acceptance examples and generated-bundle drift checks; existing older catalog compatibility is preserved. |
| #318 | Acorn parses JavaScript translation calls; Svelte's parser covers the trial component. Conditional branches contribute keys while condition literals do not. Diagnostics identify similar obsolete English keys. |
| #319 | Domain handlers and one route registry own method, path, authentication, mutation status and request/response descriptions. [API.md](API.md) is generated from that registry. |
| #320 | **Held back behind `HOARD_METADATA=sqlite`; JSON files remain the default.** Sealed SQLite transactions, stable product identities, resumable legacy migration and one-release JSON backups. Public exports retain their formats. [STORAGE](STORAGE.md) documents recovery limits and the measured 50,000-product benchmark. |
| #321 | One persistent Library/Downloads shell, cached projections, history, common windows and product components. [APP-SHELL](APP-SHELL.md) records the bounded Svelte trial, costs and migration boundaries. |
| #322 | One adapter per store, explicit capabilities and request pacing, sanitized offline fixtures and safe health reporting. See [STORES](STORES.md). |
| #323 | One priority scheduler owns background workers and recurring checks; package checkpoints and waiting user intents survive restart. Tasks exposes progress and Pause/Stop/Resume. See [SCHEDULER](SCHEDULER.md). |
| #324 | Pointer drag fallback addresses the failure mode reported in #313. Published size/antivirus evidence and the native comparison protocol are in [DESKTOP-DECISION](DESKTOP-DECISION.md). Cross-OS startup, installed size, memory and tester results remain outstanding. Keep this issue open; macOS signing/notarization is explicitly deferred. |

## Compatibility and rollout

Private metadata migration happens on first access. Keep the retained
`.json.pre-sqlite-v1` files until at least the following release; do not run an old
binary against a home that has newer SQLite changes and expect it to see them.
Read the storage recovery section before rolling back. External download files
and Unity project operations retain their existing safety and recovery paths;
the SQLite transaction is not a cross-filesystem crash journal.

The frontend remains incremental. Existing escaped detail sections, the package
tree and separate view styles are documented compatibility boundaries. Node is
needed to develop/build the Svelte component and run syntax-aware validation,
but the generated bundle ships with Hoard and users do not install Node.

Store fixture tests establish parsing and failure behavior against sanitized
examples; they do not prove a live storefront has kept its layout. Health
messages and previous-result preservation handle that distinction at runtime.

## Reproducing checks

Install the locked Python requirements, Chromium and Mono for the C# tests,
then run:

```sh
npm ci --ignore-scripts
node scripts/build_ui.mjs --check
python scripts/build_schemas.py --check
python scripts/build_api_docs.py --check
python scripts/test_suite.py --seed 1800 --repeat 2 --summary test-results/local.json
python scripts/build_release.py
python scripts/build_vpm.py
```

CI uses `--shard N/6` on Linux and Windows. To reproduce a failure, use its
reported seed and shard with the same timing file. Shuffling preserves each
class fixture's lifecycle while exercising method/class order and repeated
execution. See [Development](../wiki/Development.md) for dependencies.
