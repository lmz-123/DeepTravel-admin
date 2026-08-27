## 1. Main-schema compatibility and admin contracts

- [x] 1.1 Add schema-compatibility checks for the main repository's pre-departure script/tracks, unified story mapping, media metadata, and required indexes; return actionable 503 details and create no DDL in the admin service.
- [x] 1.2 Capture regression fixtures for current route graph, stop editor, tags, narration, home stories, catalog/pretrip, media upload/list/delete, lifecycle locks, and the legacy local/OSS branch before replacing it with mandatory OSS plus in-memory test fakes.
- [ ] 1.3 Define authorized scenic summary/detail contracts with city/title/cover/status/content counts and consistent user-facing “景点” labels while retaining route IDs internally; add serializer/filter/pagination tests.

## 2. Scenic context and pre-departure admin APIs

- [ ] 2.1 Add aggregate reads for one scenic context and its legacy stops, managed fragments, narration coverage, tags, triggers/tasks, validation, and pre-departure state without creating a second content model; test partial-section failures and publication locks.
- [ ] 2.2 Add lifecycle-aware pre-departure edit, preview, narration generate/upload/select, submit/verify/publish/withdraw operations over the main-owned schema, including optimistic versions and transcript-hash stale blocking; add endpoint and fake-TTS/storage rollback tests.
- [x] 2.3 Preserve `experience_tags` through stop/fragment request/response, graph JSON, structured editing, legacy/single-route and multi-city import/export paths; add unknown-tag, order, normalization, and published-lock tests.
- [ ] 2.4 Add request cancellation/generation support needed by rapid scenic switching and verify a late response or save cannot populate or mutate the newly selected scenic context.

## 3. Unified scenic-content workspace

- [ ] 3.1 Build one shared scenic-context shell with selected ID in URL state, latest-authorized recent restoration, section-scoped loading/errors, refresh, and a shared dirty registry; test invalid recent IDs, reload/deep link, and stale-response protection.
- [ ] 3.2 Build the accessible “选择景点” trigger and focus-trapped searchable picker with city grouping, responsive cover/status/content cards, selected/recent states, keyboard navigation, screen-reader labels, and empty/error handling; add component/e2e tests with a large catalog.
- [x] 3.3 Compose scenic metadata, ordinary stops/stories, managed fragments, narration, tags and pre-departure under one “景点内容” entry; remove independent route/question navigation while preserving route/challenge data and compatible APIs.
- [ ] 3.4 Add save/discard/cancel protection for scenic switches, navigation, refresh, and close; retain failed input and verify no hidden section silently loses changes.
- [ ] 3.5 Embed concise pre-departure text/audio/lifecycle/compact preview in the selected scenic workspace, remove the active standalone pretrip panel, and test text-change audio invalidation and per-scenic isolation.
- [x] 3.6 Reduce each legacy stop or managed fragment to one normal card with title, story copy, address/location/radius and tags; preserve hidden technical graph values and move narration generation to one scenic-level compact control.

## 4. Unified city-story administration

- [ ] 4.1 Consume the main migration dry-run/result and expose legacy arc-to-catalog mappings plus blockers so every eligible homepage story is traceable before UI cutover; add coverage and ambiguous-source tests.
- [x] 4.2 Build a city-card-first “城市故事” workspace whose only business inputs are fixed city, title and story content; remove directory/type/source/metadata/JSON configuration while the API automatically resolves or preserves compatibility metadata.
- [x] 4.3 Remove “首页听故事” from active navigation and redirect supported old state/bookmarks to the mapped unified item; verify no duplicate save/publish path or media upload remains.
- [x] 4.4 Add component/API tests proving minimal edits update the same canonical story identity, stale audio rules still apply, hidden compatibility metadata round-trips, and creation fails atomically when a city has no eligible canonical story.

## 5. Hierarchical and truthful media library

- [ ] 5.1 Add authorized paginated media hierarchy endpoints returning city/scenic summaries and public/private editorial, narration, pre-departure, community, user-photo, footprint, evidence, and preview usages with shared/unassigned classification, OSS object key, MIME, size/checksum, safe delivery mode, and reference counts; add privacy, mixed-reference, and delete-protection tests.
- [x] 5.2 Remove local provider selection/mount assumptions from admin runtime configuration and require production/test API and CMS to use identical public/private OSS buckets, canonical object keys, media references, CDN base, and private-access behavior; fail schema/readiness without complete OSS configuration and retain only in-memory fakes for unit tests.
- [ ] 5.3 Add a sanitized OSS/shared-resource readiness endpoint reporting explicit environment, safe public/private bucket identity, CDN base, public/private counts, production/test public/private key-checksum/reference/access agreement, disposable-test-prefix status, local-reference/read/mount blockers, and audit time without credentials, permanent private URLs, raw environment values, or filesystem roots; add redaction and permission tests.
- [ ] 5.4 Replace the flat media grid with city → scenic expandable browsing, usage filters, shared/unassigned groups, public/private OSS badges, metadata, CDN/protected-access preview/copy/deep-link actions, and accessible loading/empty/error states; add responsive, authorization, and keyboard tests.
- [ ] 5.5 Make upload and narration copy identify public/private OSS scope, show a blocking warning for missing OSS, canonical drift, unsafe test permissions, local references/reads/mounts, CDN bypass, private exposure, or unknown readiness, and provide migration/recheck guidance without running shell commands in the browser.

## 6. Validation, rollout, and independent delivery

- [x] 6.1 Run admin Python tests/Ruff, frontend lint/type/build and interaction/e2e suites, then run `openspec validate unify-scenic-content-and-pretrip-experience --strict`; resolve every failure.
- [ ] 6.2 Test against a disposable MySQL upgraded by the main repository and exercise scenic switching/dirty guards, both content models, pre-departure narration/lifecycle, tag round-trips, unified story migration, in-memory fake OSS media hierarchy, mandatory-configuration failures, shared canonical agreement, and public/private authorization boundaries.
- [ ] 6.3 Deploy the main repository migration/API first, run admin schema health, then deploy admin; keep old endpoints/components available for rollback until mapping, client compatibility, and production OSS audits pass.
- [ ] 6.4 Verify production and test through authorized admin/API checks without exposing secrets: both use identical public/private buckets, canonical keys, references, CDN and private-access behavior; public samples return the same CDN URLs, private samples resolve the same OSS objects through the same authorization rules, disposable tests cannot overwrite/delete canonical keys, counts/checksums reconcile, and no local reference/read/mount or migration blocker remains.
- [ ] 6.5 Inspect the independent worktree, commit and push only reviewed admin/OpenSpec changes to its own `main`, and report the admin commit hash, validation results, compatibility version, and exact idempotent deployment/health commands.
- [x] 6.6 Bound runtime logs with short client-log retention/hard row caps and Docker size/file-count rotation; verify cleanup and compose configuration so the log UI remains a recent diagnostic view rather than permanent storage.
