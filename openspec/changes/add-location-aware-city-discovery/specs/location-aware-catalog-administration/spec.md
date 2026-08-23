## Purpose

Allow operators to configure generic experience tags on the scenic/story point records used by home discovery, without adding city-recognition or route-recommendation administration.

## ADDED Requirements

### Requirement: Operators can manage point experience tags
The admin SHALL allow authorized operators to view and edit ordered `experience_tags` on legacy stops and managed story fragments. It SHALL accept arbitrary display strings within documented storage limits and MUST NOT rely on a semantic allowlist. Requirement one SHALL NOT add a city recognition/range field, route discovery order, or route tags.

#### Scenario: Edit a legacy scenic stop
- **WHEN** an authorized operator saves valid experience tags on a legacy stop
- **THEN** the admin persists and returns the normalized ordered tags for that stop

#### Scenario: Edit a managed story point
- **WHEN** an authorized operator saves valid experience tags on a managed story fragment
- **THEN** the admin persists and returns the normalized ordered tags for that fragment

#### Scenario: Configure a future tag
- **WHEN** an operator enters a valid tag unknown to the current application release
- **THEN** the admin accepts and preserves it without a software allowlist update

### Requirement: Point tags are normalized and validated consistently
The admin SHALL trim tag whitespace, remove empty values, and remove duplicates while retaining first occurrence order. It SHALL accept no more than eight tags of at most 24 Unicode characters each. Invalid values SHALL return a point-specific field/path error and MUST NOT be partially committed.

#### Scenario: Duplicate and padded tags are submitted
- **WHEN** an operator submits surrounding whitespace, empty values, and repeated tags
- **THEN** the saved result contains trimmed unique non-empty values in first occurrence order

#### Scenario: A tag collection is invalid
- **WHEN** a stop or fragment exceeds the tag count or length limit or contains a non-string value
- **THEN** validation identifies that point field/path and no partial mutation is committed

#### Scenario: Product examples are used
- **WHEN** tags include “安静”, “适合约会”, “网红打卡”, “随便逛逛”, “适合一个人”, “适合朋友同行”, “老建筑”, “城市历史”, “社区生活”, or “海边或自然景观” within limits
- **THEN** they pass validation exactly like any other valid strings

### Requirement: Existing content paths preserve point tags
Existing legacy-stop CRUD, managed graph save/preview, and package import/export SHALL preserve `experience_tags` using the same normalization rules. Inputs that predate the field SHALL behave as `[]`. This compatibility MUST NOT create a new import/export workflow.

#### Scenario: Existing graph round-trip
- **WHEN** a managed graph containing fragment tags is saved and read again
- **THEN** the normalized fragment tags are preserved without copying them to routes or stops

#### Scenario: Existing package round-trip
- **WHEN** a valid existing package with point tags is imported and exported
- **THEN** tags are preserved and repeated import retains the current idempotent behavior

#### Scenario: Old content omits tags
- **WHEN** an old record or package contains no `experience_tags` field
- **THEN** the admin exposes an empty list without rejecting the content

### Requirement: Point tag edits obey the current publication lifecycle
Point tag changes SHALL use the existing draft, validation, review, publication, and archive boundaries. Published managed content MUST remain protected from direct mutation, and draft tag edits MUST NOT become traveler-visible before publication.

#### Scenario: Edit a locked published route fragment
- **WHEN** an operator attempts to directly change tags on a fragment owned by locked published managed content
- **THEN** the admin rejects the mutation through the existing publication lock

#### Scenario: Publish reviewed point tags
- **WHEN** valid point tag changes complete the existing review and publication transitions
- **THEN** the saved tags become eligible for the main API's public point projection

### Requirement: Admin deployment consumes the main point-tag migration
The admin release SHALL document that the main DeepTravel Alembic migration for stop and story-fragment tag columns must be applied before this service version starts. It MUST NOT create a competing migration or runtime DDL for those shared tables.

#### Scenario: Coordinated deployment
- **WHEN** operators deploy requirement one
- **THEN** they apply the main migration before starting the new admin service and verify both point editors

#### Scenario: Rollback admin code
- **WHEN** the admin version is rolled back after the additive migration
- **THEN** the shared point-tag columns remain intact without a destructive automatic downgrade
