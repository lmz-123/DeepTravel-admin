## Context

See `proposal.md` for motivation. `Travel-Admin` is an independent FastAPI/SQLAlchemy service and frontend that maps the main repository's MySQL schema without owning Alembic migrations. It already has legacy city/route/stop editing, managed story-fragment and complete-story workflows, media references, lifecycle locks, and a single-route JSON importer. The companion main change adds the database schema and public contracts; this repository supplies authorized operations and UI.

The active complete-story/listening work is a dependency. Catalog editing must select its canonical story sources and approved narration rather than add another transcript or audio authoring path.

## Goals / Non-Goals

**Goals:**

- Add one consistent editor for catalog relations, placements, pre-trip guidance, and lifecycle blockers across existing story source types.
- Preview five home modules and pre-trip content before publication.
- Provide an upload → dry-run → bound confirm workflow for atomic multi-city packages.
- Route manual, legacy single-route, and multi-city changes through shared normalization and validation semantics.

**Non-Goals:**

- Database migration ownership, public mobile endpoints, client offline storage, or favorites UI.
- Binary media upload inside JSON, arbitrary remote media fetching, automatic publication, or best-effort partial imports.
- Replacing existing city/route/point/story/media editors wholesale.

## Decisions

### 1. Map main-owned catalog tables and keep source content read-only in the catalog form

Admin SQLAlchemy mappings mirror the main repository's catalog item, source/presentation revisions, relations, placements, guidance, and import-audit tables. The catalog editor loads a fragment or story arc as read-only canonical context and edits only distribution metadata. It can associate reviewed `short_preview` and `on_site_complete` variants from the same canonical lineage so home/pre-trip and on-site channels can use different approved lengths without copying text or media. Existing fragment/story editors remain the only places that change transcripts and narration.

The service checks the selected source and variant revisions on save and on lifecycle transition. A mismatch is shown as a blocker with links back to the source editor.

Alternative considered: embed transcript/audio fields into the catalog editor. Rejected because that would recreate the data divergence this change is intended to remove.

### 2. Use schema-driven generic chips for content values, fixed controls for product slots

The five home module keys have stable controls because they are product layout slots. Themes, content types, companion labels, and experience tags use generic string/catalog selectors with safe display labels and unknown-value preservation. The preview consumes the same projection shape as the public API, with draft visibility and blocker annotations added for authorized users.

Alternative considered: frontend enums for every content type/tag. Rejected because new editorial values would require deployments.

### 3. Extend existing forms rather than build a parallel content console

City, route, point, fragment, story arc, audio, image, coordinate/range, source/fact, and lifecycle ownership remains in current screens. Catalog panels attach relations and placements; route panels attach pre-trip directions, advisory order, tags, tips, and offline eligibility. Imported records deep-link to those same screens.

Alternative considered: a separate imported-content editor. Rejected because it would create two models and inconsistent validation.

### 4. Share normalized commands across manual and import paths

Admin application services expose normalized create/update commands for the affected entity graph. Form saves, the existing single-route importer, and the new multi-city importer adapt input into these commands. They use existing permissions, optimistic revisions, published locking, validation, and lifecycle services.

This does not require all old endpoints to disappear immediately. Compatibility adapters retain current response shapes while delegating to shared normalization where behavior overlaps.

Alternative considered: let the importer write ORM models directly. Rejected because it would bypass invariants and drift from manual editing.

### 5. Make dry-run server-authoritative and confirmation-bound

The frontend uploads a bounded JSON file to dry-run. The server parses and normalizes the full package, validates relations/media/lifecycle rules, builds per-record diffs, and persists only a short-lived audit/preview plan. The response includes counts, stable IDs, JSON paths, field diffs, blockers, and a confirmation token bound to editor identity, package checksum, expiry, and target revisions.

The UI groups new/updated/unchanged/conflicted/invalid records and disables confirmation for blockers. Confirm sends only the token (and required anti-CSRF/auth context); the server rechecks revisions and executes the planned content writes in one transaction. It never trusts a client-edited diff.

Alternative considered: send the JSON again and trust the browser preview. Rejected due to time-of-check/time-of-use risk and inconsistent diff rendering.

### 6. Treat import publication intent as requested metadata only

Packages may request module/channel placement and desired publication configuration, but normalized records enter draft or the applicable pre-publication state. The admin displays requested intent and remaining blockers. Review, approval, and publish remain separate authorized actions, and published locks apply afterward.

Alternative considered: honor `published: true` during import. Rejected because it bypasses sources, facts, media verification, and editorial accountability.

### 7. Define failure and observability behavior

Dry-run errors include package ID/version when readable, entity kind, stable ID, JSON Pointer-style path, error code, human-readable Chinese message, and optional remediation. Confirmation returns one package outcome; on failure the transaction rolls back and the audit records the actor, checksum, failure stage, and non-sensitive error summary. Logs and audit data never store embedded media bytes or unrestricted raw file contents.

## Risks / Trade-offs

- [Main/admin schema deployment order can break mappings] → Version-gate new routes and deploy main additive migration before enabling admin features.
- [Large previews can overwhelm browser rendering] → Enforce limits, paginate/group record details, and keep aggregate counts always visible.
- [Shared normalization can subtly change legacy import behavior] → Add golden compatibility tests before delegation and retain the adapter until parity is demonstrated.
- [Free-form labels can become inconsistent] → Provide suggestions and warnings while preserving unknown values needed for client independence.
- [Preview tokens retain sensitive draft metadata] → Keep short expiry, bind to editor/permissions, store minimal normalized plans, and redact raw content from logs.
- [Atomic import reduces partial recovery flexibility] → Prefer data integrity; return precise paths so the package can be corrected and replayed safely.

## Migration Plan

1. Land and deploy the companion main repository migrations and service contracts with new routes disabled.
2. Add admin mappings and read-only canonical catalog views; verify against a migrated staging database.
3. Introduce shared normalization behind tests, then delegate the existing single-route importer through its compatibility adapter.
4. Enable catalog/pre-trip editing and draft preview for authorized roles.
5. Enable bounded multi-city dry-run, inspect audit/latency metrics, then enable confirmation for a smaller operator group.
6. Expand access after successful idempotency, rollback, lock, and lifecycle verification.
7. Roll back by disabling new admin routes/UI flags; preserve main-owned additive schema and audit records, and keep legacy editors/import entry points available.
