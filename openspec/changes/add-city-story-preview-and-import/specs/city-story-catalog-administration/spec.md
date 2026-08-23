## Purpose

让运营人员在不复制故事正文或音频的前提下，统一维护城市故事关系、首页投放、旅行前信息与审核发布状态，并预览真实客户端结果。

## ADDED Requirements

### Requirement: Canonical story selection
The admin SHALL let an authorized editor create or edit a catalog item by selecting an existing story fragment or complete story arc, configure approved short-preview and on-site-complete presentation variants where available, and display each selected canonical transcript, narration revision, lineage, and current publication blockers as read-only source context.

#### Scenario: Editor selects a complete story
- **WHEN** an authorized editor chooses an existing story arc as the canonical source
- **THEN** the catalog form references that source without creating a copied transcript or audio body

#### Scenario: Editor configures two audio forms
- **WHEN** an editor selects an approved related short presentation for home/pre-trip and an approved complete arc track for on-site use
- **THEN** the admin preserves both channel roles in the same canonical story lineage without duplicating either audio file

#### Scenario: Canonical source changed
- **WHEN** the referenced transcript revision no longer matches the reviewed catalog revision
- **THEN** the admin displays a stale-source blocker and prevents silent publication

### Requirement: Complete manual metadata editing
The admin SHALL support manual editing of title, summary, cover, city, district, themes, related points, related stories, advisory relation order, content type, observable details, optional attention hints, sources, fact status, review status, channel eligibility, and publication state using the same validation and lock rules as imported content.

#### Scenario: Required fact metadata is missing
- **WHEN** an editor submits a catalog item without required source or fact status
- **THEN** the form identifies the affected field and does not advance publication state

#### Scenario: Story duration falls outside guidance
- **WHEN** an otherwise valid story is estimated outside three to eight minutes
- **THEN** the admin shows a warning without treating duration alone as a hard blocker

### Requirement: Home module placement and preview
The admin SHALL let authorized editors configure and preview placements for the five required home modules by city, editorial order or weight, eligibility, and lifecycle state, with “今天听一段城市故事” visibly treated as the primary home entry.

#### Scenario: Editor previews a city home
- **WHEN** draft placements exist for a selected city
- **THEN** the preview shows the five module slots, their draft content, and the public blockers without publishing them

#### Scenario: New content tag is entered
- **WHEN** an editor enters a safe theme or tag value not previously known to the UI
- **THEN** the value is preserved and previewed without a frontend release

### Requirement: Pre-trip guidance editing
The admin SHALL let editors configure reusable theme stories, major story directions, advisory roam order, companion tags, safety, rest, accessibility, weather-adaptation tips, and offline-eligible resources without quiz fields or forced progression.

#### Scenario: Editor changes recommended order
- **WHEN** an editor reorders pre-trip story directions
- **THEN** the preview labels the order as advisory and leaves every eligible direction independently openable

### Requirement: Existing content editing remains available
The admin SHALL continue to support manual city, route, point, story, audio, image, WGS-84 coordinate, location range, tag, source, fact, review, and publication editing after catalog capabilities are added.

#### Scenario: Imported point is opened
- **WHEN** an editor opens a point created by multi-city import
- **THEN** the existing point editor can modify it through normal validation and review

### Requirement: Explicit lifecycle transitions
Catalog metadata, placements, and pre-trip guidance SHALL use the established draft, validation, review, approval, and explicit publication controls, including published-content locking.

#### Scenario: Editor saves a published placement change
- **WHEN** a locked published placement requires modification
- **THEN** the admin requires the established revision/unpublish workflow instead of mutating public content in place
