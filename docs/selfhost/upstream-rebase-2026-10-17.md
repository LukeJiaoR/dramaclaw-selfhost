# Upstream synchronization, 2026-10-17

Upstream: https://github.com/dramaclaw/dramaclaw, main at
`a627206b3919f78769bd5efe4e6b3cd3946eeb93`.
Previous shared ancestor: `b299bfd9f6fc3e4a1eacc580cc03d5868c2e6e83`.
Selfhost source: `6ac1ca366aea4ac7090beac9cc75cda32a49d677`.

The four selfhost feature/fix commits were rebased individually. The old upstream
merge was not replayed as a merge: its 18-file manual resolution diff was inspected
with `git show --remerge-diff bd416f32` and reconciled as follows.

| Prior resolution | Outcome in rebased code |
| --- | --- |
| `.env.example` | Keep structured extraction concurrency and explicit selfhost Provider Hub image selections. Comments follow current upstream. |
| `agents/content_rewriter.py` | Keep constrained adaptive output together with upstream BrainClaw profile and gateway-aware retry budget. |
| `api/routes/model_gateway.py` | Keep both Provider Hub administration and upstream local-service exclusion guard; retain newer provider model discovery endpoint. |
| `api/routes/projects.py` | Keep voice-design functions and bounded metadata I/O imports. |
| `config.py` | Keep Provider Hub option; supersede globally changed official image defaults with upstream defaults. `.env.example` explicitly opts the selfhost deployment into Hub images. |
| `director_world/scene_overlap_analyzer.py` | Old direct chat-completion replacement superseded by upstream shared scene-analysis gateway, including profile and egress checks. New setting name is `SCENE_OVERLAP_ANALYSIS_MODEL`. |
| `director_world/scene_spatial_contract.py` | Same upstream shared-gateway replacement; custom gateway credentials remain supported. |
| `freezone/mark_node.py` | Accept explicit `provider_hub` alongside legacy `newapi`, preserve upstream vision-egress preparation/completion and upstream default. |
| `freezone/route_helpers.py` | Preserve style manifest loader, logger, unknown-style fallback and Hub option. Restore upstream default to avoid redirecting official-mode requests. |
| `generators/nanobanana_grid.py` | Keep Hub base URL, disabled SDK retries and 660-second Hub timeout; retain upstream 300-second direct OpenAI timeout, organization relay and request logging. Discard removed unused sketch variables. |
| `generators/scene_reference_images.py` | Keep explicit Hub image path alongside newer organization admission and archive-copy handling. |
| `sqlite_store.py` | Advance upstream schema 5 to 6 for selfhost voice_prompt column; do not restore old schema 2 or 4. |
| `stage_asset_tasks.py` | Supersede unconditional panorama analysis with upstream configured-gateway check and organization exclusion. Removes obsolete dependency on OpenRouter keys while preserving the safety boundary. |
| `verification/sketch_visual_gate.py` | Keep Hub fallback and upstream explicit Google/OpenRouter behavior; preserve organization direct-vision denial. |
| `tests/test_api_character_voice_samples.py` | Keep both adopted voice prompt and upstream concurrent upload/delete/trim regression tests. |
| `tests/test_freezone_image_backend.py` | Keep upstream authz fixture/catalog/billing assertions. Update default assertions to upstream; explicit Hub selection remains available. |
| `tests/test_scene_reference_prompt.py` | Keep normalized gateway config test and required config import. |
| `tests/test_sqlite_schema_initialization.py` | Keep dynamic schema-version assertion; add regression for upgrading an already-marked upstream v5 database. |

Upstream removed `docker-compose.selfhosted.yml`; it is not resurrected. Use the
maintained compose files and current README build prerequisites. No production
migration, deployment, model call, remote branch update or force push is part of
this local synchronization.

## Additional compatibility corrections

- The overlap-model frontend feature and Advanced mapping now use upstream
  `SCENE_OVERLAP_ANALYSIS_MODEL`. Existing `SCENE_OVERLAP_MODEL` environment
  overrides remain a fallback when the new key is absent; the new key wins.
  Persisted frontend feature settings migrate the old key without replacing an
  existing new-key choice (settings storage version 19).
- Generated character/narrator voices now use the existing upstream resource
  locks and cancellation-safe media/finalization helpers. Narrator generation
  also uses the current context-based helper signatures. These defects existed
  in the prior selfhost head and were corrected while validating synchronization.

## Local verification

All model/provider responses in these tests are mocked; no production services
or model generation jobs were used.

- 173 tests: provider text gateway, voice design, character voice API, SQLite
  initialization/store, adaptive rewrite, beat props, Freezone text/marks,
  NewAPI images and scene-reference prompts.
- 288 Freezone image backend tests.
- 11 standalone Provider Hub adapter/store tests.
- 76 tests for organization image/mark/subprocess egress and text gateway.
- 7 scene-analysis gateway tests, including old/new overlap setting precedence.
- Explicit upstream-v5 database migration regression passed.
- 34 voice lifecycle/API tests passed after the compatibility corrections.
- 19 frontend tests across six touched rewrite/voice suites passed.
- Full frontend TypeScript project check (`tsc -b`) passed. An initial check
  running concurrently with an over-parallelized test invocation was killed for
  resource exhaustion; the isolated retry passed.
- Python source compilation and `git diff --check` passed.

This is targeted validation, not a claim that the complete upstream test suite
or a real-provider end-to-end generation run has passed.

Final combined backend regression run: **550 passed**, plus **11 passed** in
the separate Provider Hub suite. Frontend feature settings/canvas tests passed
24 cases before the storage migration; the settings suite passes 18 cases
including the two new migration scenarios.

## Repository publication safety

The inherited `publish-official-media-catalog` and `sync-to-gitee` workflows
already existed in the prior selfhost main. Their jobs now require the exact
`dramaclaw/dramaclaw` repository, so a selfhost main update cannot publish to the
upstream OSS catalog or force-push the upstream Gitee mirror. Normal CI is
unchanged. `tests/test_selfhost_workflow_guards.py` pins both job conditions.

The reviewed rebased source is `d1385aecffecbdc4f6882e32e5fe5ac79739b68d`.
Repository publication uses an ordinary snapshot integration commit descended
from existing selfhost main, plus the narrowly scoped workflow guards above.
The available authenticated connector cannot push the full local Git object
graph; the 656-commit rebased history remains preserved on the local branch.
The remote snapshot retains the reviewed source tree and upstream provenance
without rewriting shared history.
