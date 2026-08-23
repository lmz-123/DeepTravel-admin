## Why

Requirement one allows scenic/story point cards to display arbitrary backend-configured experience tags. The independent admin service must map and edit those point fields while preserving the existing publication lifecycle. It does not need any city-recognition or route-recommendation configuration.

## What Changes

- Consume the additive main-repository migration that adds `experience_tags_json` to legacy stops and managed story fragments only.
- Extend matching admin ORM/request/response mappings and the existing stop/fragment editors with generic experience-tag entry.
- Preserve point tags through the existing managed graph and package import/export paths so normal content operations do not discard them.
- Apply the current validation/publication locks and expose field-specific errors.
- Add focused server/frontend tests and the migration-first deployment note.

### Non-goals

- No city recognition radius, city range, city-coordinate matching, city editor changes, or location handling.
- No route discovery order, route tags, route recommendation controls, or route-card configuration.
- No new package/import/export capability; only compatibility of the existing paths with the point field.
- No migration in this repository and no changes to story playback, journey progression, community, narration, or footprints.

### MVP validation goals

- An operator can edit ordered free-form tags on a legacy stop or managed story fragment.
- Current example tags and future valid strings are accepted without an application allowlist.
- Existing graph/package round-trips preserve point tags and publication locks still apply.
- No city/range/order/route-tag field appears in the admin diff.

## Capabilities

### New Capabilities

- `location-aware-catalog-administration`: Defines lifecycle-safe administration of experience tags on published scenic/story point records only.

### Modified Capabilities

None.

## Impact

- Admin API: matching stop/fragment model, schema, serializer, graph, and existing import/export projections.
- Admin frontend: reusable tag input on legacy stop and managed fragment editors.
- Shared MySQL: depends on the main DeepTravel point-tag migration; this repository creates no schema migration.
- Operations: independent admin verification/deployment after the main migration.
