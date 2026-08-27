## Purpose

为运营提供唯一且极简的“城市故事”栏目，按城市进入并只维护标题和故事内容，同时复用既有首页故事的 canonical 身份和音轨。

## ADDED Requirements

### Requirement: One city-story administration entry
The CMS SHALL expose one navigation entry named “城市故事” at the current city-story location and SHALL remove “首页听故事” as an independent active navigation item. Its first level SHALL show available cities as cards; opening a city SHALL list and add stories only for that city.

#### Scenario: Operator opens city stories
- **WHEN** the operator activates “城市故事”
- **THEN** the workspace shows city cards rather than a directory selector or mixed global form

#### Scenario: Existing bookmark targets the old view
- **WHEN** a supported old administration route or state points to home stories
- **THEN** the CMS redirects or delegates to the matching item in the unified workspace during the compatibility window

### Requirement: City story has one kind and three business values
The normal city-story editor SHALL expose only city, title, and story content. City SHALL be fixed by the selected city card. Source kind, source ID, content type, directory item terminology, summary, cover, district, themes, point IDs, fact/review fields, sources, related stories, variants, placements and raw JSON MUST NOT be operator inputs in this workspace. The server SHALL resolve or preserve those compatibility values.

#### Scenario: Operator adds a story
- **WHEN** the operator opens a city and chooses “添加故事”
- **THEN** the form asks only for title and story content and creates the single supported city-story kind for that city

#### Scenario: Operator edits an existing story
- **WHEN** the operator opens a story card
- **THEN** the same title and story content are editable without selecting a directory item or story type

### Requirement: Existing home stories are reused
For each eligible existing home-story publication, the CMS SHALL show the same canonical story identity and approved audio through the city-first workspace. Saving or publishing MUST NOT create another transcript body or upload duplicate audio bytes.

#### Scenario: Operator edits migrated story content
- **WHEN** the operator changes title or story content for a migrated story
- **THEN** the canonical source is updated in place and any now-stale approved audio is handled by the existing revision rules

#### Scenario: Canonical transcript becomes stale
- **WHEN** the backing arc transcript changes
- **THEN** the workspace displays the stale blocker and does not offer an independent legacy publication path around it

### Requirement: Compatibility metadata is automatic
The API SHALL preserve existing placement, variant, source and lifecycle metadata when the minimal form is saved. For a new city story it SHALL choose an eligible canonical complete story in that city and create safe defaults, or return an actionable conflict if no canonical story is available. The UI MUST NOT expose these values as required configuration.

#### Scenario: No canonical story is available
- **WHEN** the operator adds a story in a city whose scenic stories are all already mapped or absent
- **THEN** creation fails with a clear instruction to add scenic content first and no partial catalog record is written
