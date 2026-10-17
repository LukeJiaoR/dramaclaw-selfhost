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
| `config.py` | The initial synchronization incorrectly replaced the selfhost sketch/render/fallback defaults with upstream NewAPI defaults. The correction restores Provider Hub defaults while retaining current upstream gateway and egress behavior. |
| `director_world/scene_overlap_analyzer.py` | Old direct chat-completion replacement superseded by upstream shared scene-analysis gateway, including profile and egress checks. New setting name is `SCENE_OVERLAP_ANALYSIS_MODEL`. |
| `director_world/scene_spatial_contract.py` | Same upstream shared-gateway replacement; custom gateway credentials remain supported. |
| `freezone/mark_node.py` | Accept explicit `provider_hub` alongside legacy `newapi`, preserve upstream vision-egress preparation/completion and upstream default. |
| `freezone/route_helpers.py` | Preserve style manifest loader, logger, unknown-style fallback and explicit provider choices. The correction restores the selfhost default and shares its selection with schemas and presets instead of hardcoding upstream NewAPI. |
| `generators/nanobanana_grid.py` | Keep Hub base URL, disabled SDK retries and 660-second Hub timeout; retain upstream 300-second direct OpenAI timeout, organization relay and request logging. Discard removed unused sketch variables. |
| `generators/scene_reference_images.py` | Keep explicit Hub image path alongside newer organization admission and archive-copy handling. |
| `sqlite_store.py` | Advance upstream schema 5 to 6 for selfhost voice_prompt column; do not restore old schema 2 or 4. |
| `stage_asset_tasks.py` | Supersede unconditional panorama analysis with upstream configured-gateway check and organization exclusion. Removes obsolete dependency on OpenRouter keys while preserving the safety boundary. |
| `verification/sketch_visual_gate.py` | Keep Hub fallback and upstream explicit Google/OpenRouter behavior; preserve organization direct-vision denial. |
| `tests/test_api_character_voice_samples.py` | Keep both adopted voice prompt and upstream concurrent upload/delete/trim regression tests. |
| `tests/test_freezone_image_backend.py` | Keep upstream authz fixture/catalog/billing assertions. The initial synchronization incorrectly changed Hub default and masked-redraw assertions to NewAPI; the correction restores the original selfhost contract. |
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


## Correction: preserve selfhost image defaults

The initial synchronization did not preserve the selfhost image-default contract.
It retained explicit Hub selection, but changed unconfigured sketch/render and
Freezone image requests and new preset nodes to NewAPI. The default assertions
were also changed to accept that regression. The earlier passing test totals are
historical targeted results, not evidence that this default behavior was preserved.

The correction restores the three config fallbacks to `provider_hub_image` and
uses one shared selfhost default constant for pipeline fallbacks and Freezone.
That default covers the seven image-request schemas, missing/non-strict-invalid
provider resolution, new preset image nodes, and workflow recommendations.
Explicit provider/model selections and saved project/canvas choices remain intact.
As before the synchronization, sketch/render environment overrides affect their
respective pipeline entrypoints; they do not override Freezone defaults. Explicit
Freezone provider/model requests still select Hub, NewAPI, or another supported
provider. This correction does not introduce a new cross-entrypoint precedence.

The historical empty-environment character default remains `newapi_nanobanana2`
because `CHARACTER_IMAGE_MODEL=nanobanana` has legacy priority. Explicit character
Hub selection was not removed by the synchronization. Changing that older behavior
is outside this repair. Gateway modes, official credential isolation, organization
egress admission/relay, scene-analysis checks, and CE local-service guards are not
changed. A catalog-bound request still requires Hub to be present in its
authenticated visible catalog; selecting the selfhost default does not bypass
Official/Hybrid/Advanced or organization model availability checks. No live
provider requests or production deployment are part of validation.

Separate deployment note: the removed legacy selfhost compose file supplied a
`host.docker.internal:host-gateway` mapping. The maintained compose files do not
currently supply that mapping. Linux Docker users selecting a Hub on the host
must verify container-to-host reachability; a small supported compose override
adding that mapping to the API/worker services is preferable to restoring the
obsolete deployment file. This repair does not change deployment configuration.

### Correction validation

Targeted offline/mock verification of this correction passed **630 tests** in four
separate runs:

- 9 fresh-interpreter cases for empty environment, sample Hub settings including
  character selection, explicit NewAPI/NB2, invalid defaults, individual
  sketch/render overrides, and legacy provider priority. Each checks all seven
  schema defaults, helper/preset defaults, explicit choices, and workflow
  recommendation catalog admission.
- 356 Freezone image, workflow-preflight, preset-canvas and selection tests,
  including restored Hub redraw/billing assertions and a new test proving the
  Hub default is rejected when absent from the authenticated visible catalog.
- 205 gateway settings, Provider Hub text, scene-analysis, organization image/
  grid/panorama/mark/vision egress and selfhost workflow-guard tests.
- 60 NewAPI image, scene-360 provider and Freezone image-node tests.

Changed-file Ruff, Python compilation, `git diff --check`, and Gitleaks scanning
of the complete patch passed. These are targeted regression results; the complete
repository suite and real-provider generation were not run.
