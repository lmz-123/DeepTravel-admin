## Context

See `proposal.md` for motivation. `Travel-Admin` is an independent React/FastAPI service mapping the main repository's MySQL schema without owning Alembic. The current app has separate navigation and large workspace components for legacy stops, fragmented content, home stories, catalog/pre-trip, and a flat media grid. Route selection in fragmented content is a native `<select>`. Media uploads currently go through a provider-neutral local/OSS port, but the confirmed target removes local runtime persistence: production and test use an identical public/private canonical OSS resource set, with public CDN and private authorized delivery.

The main repository's same-named change owns any additive schema, public projections, compatibility migration, global audio behavior, and production media migration. This companion design focuses on authorized administration behavior.

## Goals / Non-Goals

**Goals:**

- Make selected scenic area the single explicit UI context without conflating legacy and managed persistence models.
- Replace raw-ID/JSON-first normal flows with searchable structured controls while retaining advanced escape hatches.
- Expose enough media lineage and provider health for operators to answer where a resource is stored and used.
- Make OSS-only, complete production/test public/private canonical-resource identity, and delivery boundaries visible and blocking when invalid.

**Non-Goals:**

- Rebuild the CMS framework, move the admin into the Flask process, or create DDL from FastAPI startup.
- Store full graph drafts only in browser state or bypass current authorization/lifecycle locks.
- Delete legacy endpoints or resources during the first rollout.
- Expose private object URLs/credentials or let automated tests overwrite/delete canonical keys shared by production and test.

## Decisions

### 1. Introduce a reusable scenic-context shell

One shell owns `selectedScenicId`, the latest authorized route summaries, dirty-section registry, request generation, and refresh actions. It renders section navigation for overview, stops/fragments, narration, tags, triggers/tasks, and pre-departure. Each section continues to call its normalized existing or additive API; the shell does not merge stop and fragment records in memory or persistence.

The selected ID is reflected in the URL query for shareable/reloadable context and may also store the most recent ID locally. IDs are always revalidated against the latest authorized list. A monotonic request generation or abort signal prevents stale responses from replacing a newer selection.

Alternative considered: concatenate existing pages under one navigation label but let each keep its own selector. Rejected because operators could still edit different scenic areas in adjacent panels.

### 2. Use a command-palette style scenic picker

The trigger displays the current scenic cover thumbnail, city/title, lifecycle badge, and content counts. Activating it opens a focus-trapped dialog/sheet with search, city-grouped responsive cards, selected check, and recent valid items. Search covers city, title, subtitle, and slug. Keyboard arrows/tab/enter/escape and screen-reader names are tested.

Alternative considered: a styled `<select>` with city optgroups. Rejected because it still cannot show cover, status, content summary, search, or strong selected context at scale.

### 3. Compose forms over existing lifecycle-aware commands

The merged workspace reuses current route graph, stop, narration, pre-trip, validate, and lifecycle endpoints where their contracts remain correct. The main change adds only missing pre-departure script/track and aggregate summary contracts. Structured editors are the default; advanced JSON remains behind a disclosure and round-trips through the same normalizer. Dirty state is per section, and context switches present save/discard/cancel rather than silently resetting forms.

Alternative considered: one giant save payload for every scenic concern. Rejected because a failure would make unrelated sections contend, increase stale-write conflicts, and weaken current locks.

### 4. Merge city-story operations by canonical source identity

The “城市故事” workspace loads unified catalog items after the main migration. A migrated legacy home story opens the same editor with read-only canonical source, structured card metadata, approved variants, city/module placement, blockers, preview, and lifecycle actions. Compatibility links translate legacy arc IDs to the unified catalog ID. The old `HomeStoriesWorkspace` is removed from active navigation only after mapping coverage is complete.

Alternative considered: visually embed both old components in one page. Rejected because it preserves duplicate save/publish commands and contradicts the one-source requirement.

### 5. Build media hierarchy from a server aggregation

The admin API returns paginated city/scenic summary counts and asset details with typed usages from the main schema. The browser does not download all content graphs and infer ownership. Assets remain unique rows; the UI presents multiple usage links for shared assets and a separate unassigned group. Delete checks continue server-side against every reference and publication state.

OSS readiness comes from a sanitized health/audit endpoint containing required-configuration status, authorized safe public/private bucket identities, CDN base, production/test canonical agreement, scope counts, local-reference/mount blockers, audit timestamp, and status. It never returns bucket secrets, access keys, permanent private URLs, filesystem roots, or raw environment values. The upload panel uses this response to show the public/private target and delivery mode; there is no provider selector.

Alternative considered: group by object-key folder names. Rejected because current keys are checksum/date/narration oriented and do not reliably encode content ownership.

### 6. Treat any non-OSS or shared-resource mismatch as an operational blocker

The CMS reads an explicit non-secret environment label supplied by the server, not the browser hostname. API and admin must both require OSS. Production and test must report identical public/private bucket identities, canonical object keys, media references, CDN base, and private-access behavior; business resources are not environment-prefixed or copied. Optional disposable integration-test mutation is confined to a temporary prefix and cannot overwrite/delete canonical objects. If configuration is missing, identities/checksums drift, any local provider/path/read/mount remains, a public object bypasses CDN, or a private object is publicly exposed, the media page shows a blocking state and disables upload/publication readiness. It provides copyable migration/recheck guidance, but the browser never runs shell migration or receives credentials.

### 7. Preserve service boundaries and failure behavior

- Main repository: Alembic, canonical content/media tables, public API, migration commands.
- Admin API: authorized aggregation and commands, OSS/shared-resource health, optimistic-version enforcement.
- Admin UI: context/picker/forms/preview only; no authoritative lifecycle inference.

If one section fails to load, other already-loaded sections remain usable and the failure stays scoped. A failed save retains dirty input. An OSS/shared-resource audit failure is “unknown/not ready” and never falls back to local persistence. Compatibility endpoints remain until logs show supported clients and bookmarks have moved; public legacy asset requests may redirect to CDN but never read local disk.

## Risks / Trade-offs

- [The combined workspace can become visually dense] → Use section navigation, concise summaries, progressive disclosure, and one sticky scenic-context header rather than one continuous mega-form.
- [Unsaved guards become inconsistent across sections] → Use one shared dirty registry and navigation interceptor with component tests for switch, refresh, close, and browser navigation.
- [Legacy records lack a direct media reference graph] → Return explicit unresolved usages and unassigned assets; never guess ownership from filenames.
- [Admin and main service report different OSS identities] → Treat mismatch as blocking and show both sanitized states with last audit time.
- [Production and test completely share canonical objects] → Display complete public/private identity agreement and temporary-test-prefix status, and block readiness if automated tests can overwrite/delete canonical keys.
- [Existing automation depends on old endpoints] → Retain delegating compatibility handlers and test response shapes through the observation window.

## Migration Plan

1. Wait for the main repository to deploy additive schema and compatibility APIs; run schema compatibility health before enabling new sections.
2. Add sanitized scenic summaries, unified story mapping, media hierarchy, and provider audit endpoints with authorization and pagination tests.
3. Ship the scenic shell/picker behind the existing content navigation, verify every legacy/managed edit and dirty-state path, then replace the two old navigation entries with “景点内容”.
4. Run the main repository's dry-run story migration and verify coverage; enable the unified “城市故事” workspace and redirect old UI state.
5. Enable hierarchical media UI and audit API/admin plus production/test agreement. Do not mark rollout complete until OSS configuration is mandatory, public/private bucket identities, object keys, references, checksums, CDN and private-access behavior match completely, and no local reference/read/mount remains.
6. After the compatibility observation window, separately propose removal of unused UI code/endpoints; do not delete OSS media or schema in this rollout.

Rollback restores old navigation components while keeping additive endpoints and story/media mappings. OSS configuration and migrated objects are not rolled back destructively, and rollback must use the same OSS resources; local media persistence/read compatibility is not re-enabled.
