## Context

This FastAPI/SQLAlchemy admin shares the DeepTravel MySQL catalog but is a separate repository and deployment. Legacy stops and managed story fragments are the two existing point models used by public discovery. The main DeepTravel repository remains schema authority and will add one empty-default tag column to each point table.

The admin work is limited to making those point tags editable and lossless in the workflows that already touch the records. City recognition and home distance ranking are client/API concerns and create no admin fields.

## Goals / Non-Goals

**Goals:**

- Mirror the main stop/fragment tag columns exactly.
- Give existing point editors one generic ordered-tag control.
- Preserve tags through current graph/package/lifecycle operations.
- Reject malformed tag collections without partial mutations.

**Non-Goals:**

- No city editor change, city geometry, recognition radius, or location sample handling.
- No route order, route tags, route recommendation settings, or recommendation engine.
- No new import/export workflow, database migration, publication state, or broad form rewrite.

## Decisions

### 1. Mirror only the two point tag columns

Add matching SQLAlchemy attributes:

- `Stop.experience_tags_json`
- `StoryFragment.experience_tags_json`

Both are non-null JSON arrays with an empty-list default defined by the main migration. Do not add a city field, route field, discovery order, recognition radius, or admin migration. Missing shared columns fail visibly instead of being created at runtime.

### 2. Use one tag normalization contract

Expose `experience_tags` in admin JSON and map it to `experience_tags_json` internally. Normalize by trimming strings, dropping empty values, and de-duplicating in first-occurrence order. Enforce modest storage limits of at most eight tags and at most 24 Unicode characters per tag. These are shape limits, not a semantic allowlist.

The ten product examples may be shown as help text and used in tests. Future valid strings are preserved unchanged.

### 3. Extend existing paths without creating a new content feature

Update current legacy-stop CRUD, managed fragment graph serialization/save, and package import/export projections so they preserve `experience_tags`. Old inputs without the field normalize to `[]`. Exporting and re-importing an existing package remains deterministic and idempotent under its current package identifier/version rules.

This work does not add an importer, exporter, package version model, endpoint, or editorial workflow. It only prevents the new point field from being lost by paths that already exist.

### 4. Keep tags on the actual point type

The managed fragment editor owns fragment tags. The legacy stop editor owns stop tags. The admin does not copy tags between a fragment and an associated stop and does not infer tags from a route, title, prose, or theme.

### 5. Reuse current lifecycle guards

Published managed content remains protected by the existing lock. Invalid tag metadata participates in existing validation and cannot advance through review/publication. No tag-only publish endpoint or lifecycle bypass is added.

## API and Module Boundaries

- `server/models.py`: matching persistence columns only; no migration ownership.
- `server/content_schema.py`: generic tag normalization shared by simple and graph inputs.
- `server/schemas.py`: legacy stop request field.
- `server/content_graph.py`: managed fragment validation/issue paths.
- `server/main.py`: existing serialization, mutation, and import/export compatibility.
- `app/AdminApp.tsx`: tag presentation and explicit operator input only.
- Main DeepTravel repository: migration and traveler-facing projection authority.

## Failure Behavior

- Invalid tag shape/count/length returns a concrete stop or fragment field/path error and does not partially commit.
- Old records and packages without tags read as empty arrays.
- Unknown valid strings remain unchanged.
- Published managed content rejects direct edits through the current lock.
- If the main migration is missing, the admin does not issue automatic DDL.

## Risks / Trade-offs

- [Two point tables require matching fields] → Reuse one normalization helper and contract fixtures for both models.
- [Comma/newline entry can introduce whitespace or duplicates] → Preview and save the normalized ordered array.
- [Existing packages omit the field] → Default to `[]` and preserve it on later export.
- [Repositories can deploy out of order] → Apply the main migration before starting this admin version.

## Migration Plan

1. Apply the main DeepTravel Alembic migration for the two point-tag columns.
2. Deploy this admin mapping/editor version and verify legacy stop plus managed fragment read/write paths.
3. Verify current package/graph round-trip, arbitrary tag input, invalid tag feedback, and published locks.
4. Roll back admin code independently without dropping the additive shared columns.
