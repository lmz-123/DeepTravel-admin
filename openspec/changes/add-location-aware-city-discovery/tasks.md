## 1. Point tag mapping and validation

- [x] 1.1 Add admin SQLAlchemy mappings for `experience_tags_json` on stops and story fragments only, matching the main migration and adding no admin DDL.
- [x] 1.2 Implement one reusable tag normalizer/validator and tests for trimming, ordered de-duplication, empty values, eight-tag/24-character limits, current examples, and arbitrary future tags.
- [x] 1.3 Extend legacy stop and managed fragment request/response mappings using the editorial field name `experience_tags`.

## 2. Existing content paths and lifecycle

- [x] 2.1 Extend legacy stop CRUD and managed fragment graph serialization/save to round-trip point tags transactionally.
- [x] 2.2 Preserve point tags through existing package import/export with `[]` compatibility for old packages and unchanged idempotency.
- [x] 2.3 Add field/path-specific validation issues and server tests for both point models, invalid input rollback, arbitrary tags, and existing published-content locks.

## 3. Admin interface

- [x] 3.1 Add the same generic comma/newline tag control to legacy stop and managed fragment editors, with normalized preview and field-level feedback.
- [x] 3.2 Keep existing navigation/save/lifecycle behavior and use product tag examples only as non-binding help.
- [x] 3.3 Add rendered-interface tests for both editors, normalization, unknown tags, validation feedback, accessibility, and publication-lock messaging.

## 4. Verification and delivery

- [x] 4.1 Run the full admin Python suite and a migrated-schema smoke test proving the service consumes but does not create the main columns.
- [x] 4.2 Run frontend tests, lint, and the production build.
- [x] 4.3 Add only the main-migration-first rollout and non-destructive rollback note required by these two fields.
- [x] 4.4 Run strict OpenSpec validation and inspect the diff to prove no city range/coordinate field, route order/tag field, location logic, unrelated file, or secret was added.
