## 1. Main-schema compatibility and admin contracts

- [ ] 1.1 Add schema-compatibility checks for the main repository's pre-departure script/tracks, unified story mapping, media metadata, and required indexes; return actionable 503 details and create no DDL in the admin service.
- [ ] 1.2 Capture regression fixtures for current route graph, stop editor, tags, narration, home stories, catalog/pretrip, media upload/list/delete, lifecycle locks, and local/fake-OSS providers before changing surfaces.
- [ ] 1.3 Define authorized scenic summary/detail contracts with city/title/cover/status/content counts and consistent user-facing “景点” labels while retaining route IDs internally; add serializer/filter/pagination tests.

## 2. Scenic context and pre-departure admin APIs

- [ ] 2.1 Add aggregate reads for one scenic context and its legacy stops, managed fragments, narration coverage, tags, triggers/tasks, validation, and pre-departure state without creating a second content model; test partial-section failures and publication locks.
- [ ] 2.2 Add lifecycle-aware pre-departure edit, preview, narration generate/upload/select, submit/verify/publish/withdraw operations over the main-owned schema, including optimistic versions and transcript-hash stale blocking; add endpoint and fake-TTS/storage rollback tests.
- [ ] 2.3 Preserve `experience_tags` through stop/fragment request/response, graph JSON, structured editing, legacy/single-route and multi-city import/export paths; add unknown-tag, order, normalization, and published-lock tests.
- [ ] 2.4 Add request cancellation/generation support needed by rapid scenic switching and verify a late response or save cannot populate or mutate the newly selected scenic context.

## 3. Unified scenic-content workspace

- [ ] 3.1 Build one shared scenic-context shell with selected ID in URL state, latest-authorized recent restoration, section-scoped loading/errors, refresh, and a shared dirty registry; test invalid recent IDs, reload/deep link, and stale-response protection.
- [ ] 3.2 Build the accessible “选择景点” trigger and focus-trapped searchable picker with city grouping, responsive cover/status/content cards, selected/recent states, keyboard navigation, screen-reader labels, and empty/error handling; add component/e2e tests with a large catalog.
- [ ] 3.3 Compose overview, ordinary stops/stories, managed fragments, narration, tags, triggers/tasks, advanced JSON, validation, and lifecycle controls under one “景点内容” navigation entry while preserving section APIs and locks; add legacy-only, fragmented-only, and mixed-content tests.
- [ ] 3.4 Add save/discard/cancel protection for scenic switches, navigation, refresh, and close; retain failed input and verify no hidden section silently loses changes.
- [ ] 3.5 Embed concise pre-departure text/audio/lifecycle/compact preview in the selected scenic workspace, remove the active standalone pretrip panel, and test text-change audio invalidation and per-scenic isolation.

## 4. Unified city-story administration

- [ ] 4.1 Consume the main migration dry-run/result and expose legacy arc-to-catalog mappings plus blockers so every eligible homepage story is traceable before UI cutover; add coverage and ambiguous-source tests.
- [ ] 4.2 Build one “城市故事” workspace at the current catalog location with canonical read-only context, structured title/summary/cover/variant/placement controls, approved audio preview, blockers, lifecycle, and published projection preview; keep raw JSON only as advanced fallback.
- [ ] 4.3 Remove “首页听故事” from active navigation and redirect supported old state/bookmarks to the mapped unified item; verify no duplicate save/publish path or media upload remains.
- [ ] 4.4 Add component/API tests proving migrated title edits do not alter transcript/audio, stale canonical revisions block publication, unknown backend placement values round-trip, and the same story identity appears in previews.

## 5. Hierarchical and truthful media library

- [ ] 5.1 Add authorized paginated media hierarchy endpoints returning city/scenic summaries, one asset with typed usages, shared/unassigned classification, provider/object key/safe path, MIME, size/checksum, canonical URL, and reference counts; add mixed-reference and delete-protection tests.
- [ ] 5.2 Add a sanitized provider/readiness endpoint that reports explicit environment, main/admin provider agreement, safe public base, published-local blockers, counts, and audit time without credentials, raw environment values, private references, or filesystem roots; add redaction tests.
- [ ] 5.3 Replace the flat media grid with city → scenic expandable browsing, usage filters, shared/unassigned groups, provider badges, metadata, preview/copy/deep-link actions, and accessible loading/empty/error states; add responsive and keyboard tests.
- [ ] 5.4 Make upload and narration copy name the active provider, show a blocking production warning for local/mismatched/unknown readiness, and provide migration/recheck guidance without running shell commands in the browser; test local, OSS, mismatch, and audit-failure states.

## 6. Validation, rollout, and independent delivery

- [ ] 6.1 Run admin Python tests/Ruff, frontend lint/type/build and interaction/e2e suites, then run `openspec validate unify-scenic-content-and-pretrip-experience --strict`; resolve every failure.
- [ ] 6.2 Test against a disposable MySQL upgraded by the main repository and exercise scenic switching/dirty guards, both content models, pre-departure narration/lifecycle, tag round-trips, unified story migration, local/fake-OSS media hierarchy, and provider mismatch.
- [ ] 6.3 Deploy the main repository migration/API first, run admin schema health, then deploy admin; keep old endpoints/components available for rollback until mapping, client compatibility, and production OSS audits pass.
- [ ] 6.4 Verify production through authorized admin/API checks without exposing secrets: both providers agree on OSS, published samples are OSS/CDN URLs, media counts/references reconcile, and no missing/checksum blocker remains.
- [ ] 6.5 Inspect the independent worktree, commit and push only reviewed admin/OpenSpec changes to its own `main`, and report the admin commit hash, validation results, compatibility version, and exact idempotent deployment/health commands.
