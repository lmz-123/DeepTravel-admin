## Purpose

为运营提供唯一“城市故事”栏目，在不复制正文或音轨的前提下复用既有首页听故事并统一卡片、投放、审核与预览操作。

## ADDED Requirements

### Requirement: One city-story administration entry
The CMS SHALL expose one navigation entry named “城市故事” at the current city-story location and SHALL remove “首页听故事” as an independent active navigation item. The unified workspace SHALL manage canonical source, approved audio, card metadata, city placement, preview, and lifecycle together.

#### Scenario: Operator opens city stories
- **WHEN** the operator activates “城市故事”
- **THEN** one workspace lists eligible existing home stories and catalog stories without requiring a second column

#### Scenario: Existing bookmark targets the old view
- **WHEN** a supported old administration route or state points to home stories
- **THEN** the CMS redirects or delegates to the matching item in the unified workspace during the compatibility window

### Requirement: Existing home stories are reused
For each eligible existing home-story publication, the CMS SHALL show the same canonical story arc, title/introduction/cover, selected approved track, status, and version lineage through the unified catalog item. Saving or publishing MUST NOT create another transcript body or upload duplicate audio bytes.

#### Scenario: Operator edits a migrated card title
- **WHEN** the operator changes presentation metadata for a migrated story
- **THEN** the canonical transcript and approved audio remain unchanged and the unified presentation version advances normally

#### Scenario: Canonical transcript becomes stale
- **WHEN** the backing arc transcript changes
- **THEN** the workspace displays the stale blocker and does not offer an independent legacy publication path around it

### Requirement: City-story placements use structured controls
The unified workspace SHALL provide structured, backend-driven controls for city and supported placement/module values and SHALL preserve unknown valid values. Raw JSON MAY remain as an advanced fallback but MUST NOT be the only normal editing method.

#### Scenario: Operator reuses a story on the city home
- **WHEN** the operator selects a city-story placement and order for an eligible story
- **THEN** the preview reflects the same unified story identity and selected approved presentation variant
