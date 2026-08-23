## 1. Companion schema baseline

- [x] 1.1 Verify the deployed main-repository migration/API contract and add admin SQLAlchemy mappings for catalog, relations, placements, guidance, and import audit/preview records without creating Alembic files.
- [ ] 1.2 Add mapping and schema-version guard tests that fail clearly when the required main migration is absent or incompatible.
- [ ] 1.3 Capture golden tests for existing city/route/point/story/media editors and the supported single-route importer before sharing implementation paths.

## 2. Shared catalog administration services

- [x] 2.1 Implement authorized catalog create/read/update operations that select a canonical fragment or story arc, configure reviewed short-preview/on-site-complete variants, and expose transcript/audio revision and lineage as read-only context.
- [x] 2.2 Implement shared validation for city/district/theme/point/story relations with advisory order, observable details, attention hints, sources, fact/review state, arbitrary labels, canonical staleness, duration warnings, and lifecycle locks.
- [x] 2.3 Implement home placement and route pre-trip guidance operations for the five module slots, channel eligibility, editorial order/weight, tags, tips, and offline resources.
- [ ] 2.4 Add permission, optimistic revision, published-lock, canonical invalidation, arbitrary-label, and lifecycle transition tests.

## 3. Catalog and pre-trip user interface

- [x] 3.1 Add catalog list/detail forms with canonical source selection, read-only source preview, all required metadata/relations, warnings, and blocker links to existing source editors.
- [x] 3.2 Add five-module city placement controls and a draft/public projection preview with empty-module and publication-blocker states.
- [x] 3.3 Extend existing route forms with theme story directions, advisory order, companion tags, safety/rest/accessibility/weather-adaptation tips, and offline eligibility; add no quiz/exam fields.
- [ ] 3.4 Preserve unknown safe type/theme/tag values in generic controls and add frontend tests proving new values do not require code changes.
- [ ] 3.5 Add UI tests for authorization, validation paths, duration warning, stale source, published locking, module preview, and continued editing of imported records.

## 4. Shared normalization and compatibility

- [ ] 4.1 Define normalized application commands used by manual forms, supported single-route packages, and multi-city packages for all overlapping entities and relations.
- [ ] 4.2 Adapt the existing single-route importer through shared normalization while retaining its route, response shape, stable-ID behavior, and lifecycle semantics.
- [ ] 4.3 Run golden compatibility tests and keep the compatibility adapter until current clients and representative packages produce equivalent results.

## 5. Multi-city upload and dry-run

- [x] 5.1 Add an authorized bounded JSON file upload route with parse/schema errors, entity limits, package ID/version/checksum handling, and explicit rejection of embedded or arbitrary remote media.
- [x] 5.2 Implement server-authoritative whole-graph normalization, relation/media/lifecycle validation, and new/updated/unchanged/conflicted/invalid diffs with stable IDs and JSON Pointer paths.
- [x] 5.3 Persist only a short-lived redacted preview/audit plan and issue confirmation tokens bound to editor, permissions, package checksum, expiry, and target revisions.
- [ ] 5.4 Build the upload and paginated/grouped preview UI with aggregate counts, field diffs, missing-media blockers, and disabled confirmation for invalid previews.
- [ ] 5.5 Add tests proving dry-run creates no content writes and reports malformed JSON, missing fields, invalid relations, media issues, conflicts, limits, and mixed diffs precisely.

## 6. Atomic confirmation and continued editing

- [x] 6.1 Implement token-only confirmation with permission, expiry, checksum, and target-revision revalidation before mutation.
- [x] 6.2 Apply the normalized graph in one transaction, force draft/pre-publication lifecycle states, audit the outcome, roll back every content write on failure, and treat identical replays as unchanged.
- [ ] 6.3 Add result links from imported cities/routes/points/stories to existing manual editors and display requested placement intent plus remaining review blockers.
- [ ] 6.4 Add integration tests for multi-city success, TOCTOU rejection, transaction rollback, idempotent replay, conflicting checksums, no automatic publication, and immediate manual edit/review.

## 7. Verification and delivery

- [ ] 7.1 Run backend/admin frontend tests, type/lint/build checks, and a representative manual catalog/module/pre-trip workflow against the migrated main database.
- [ ] 7.2 Complete an end-to-end multi-city upload → dry-run → confirm → edit → submit-review smoke test and verify existing single-route and legacy CRUD workflows still function.
- [x] 7.3 Update operator/import documentation, permission notes, package examples, and run `openspec validate add-city-story-preview-and-import --strict` in both repositories.
- [x] 7.4 Commit and push scoped independent-admin changes after companion main contracts are ready, without adding migrations or unrelated workspace files.
