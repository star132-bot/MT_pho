# Changelog

## Unreleased

- 2026-06-17: Connected the internal Manage editor to the local SQLite archive for existing seeded work metadata and grouped tags via `PATCH /api/archive/images/{id}`.
- 2026-06-17: Connected the public Works Archive to a read-only local SQLite API (`GET /api/archive/images`) with browser fallback to local samples and IndexedDB records.
- 2026-06-17: Added a database validation workflow for the local SQLite archive seed, including schema/view, foreign key, asset, tag JSON, ratio, and local path checks in CI.
- 2026-06-15: Reworked the Works Archive enlarged viewer into a full-screen image detail system with fit/actual-size zoom, a side information rail, and grouped tag rendering; expanded derived tags to include subject categories such as landscape, house/building, architecture, animals, objects, coast/water, stone, and surface/pattern.
- 2026-06-15: Compacted the Works Archive top navigation/search/filter chrome and synchronized the internal Manage tag editor with the same seven grouped tag taxonomy used by the public viewer and SQLite seed.
- 2026-06-14: Added a local SQLite Works Archive verification database and seed script that imports sample image metadata, assets, grouped tags, taggings, analysis rows, and an archive-featured collection from `archive-data.js`.
- 2026-06-10: Added the Works Archive work viewer with enlarged display images, catalog-style metadata, grouped tag visualization, keyboard navigation, scroll locking, and deferred database fields for curatorial notes, artist statements, series, and tag groups.
- 2026-06-08: Added the `4:3` Works Archive ratio category across filters, upload classification, local samples, and deferred database schema.
- 2026-06-08: Added local upload compression and multi-version asset records for Works Archive uploads, including original, display, thumbnail, and square slice assets aligned with the deferred database schema.
- 2026-06-08: Refined the Works Archive visual system with smaller radii, serif/sans typography roles, thin-line functional icons, grouped filter/manage controls, and icon-based Arrange actions.
- Moved Selected Works above the homepage Statement and rebuilt Statement as four image/text moments with per-moment entrance animation.
- Added Works Archive Arrange mode with drag ordering, Earlier/Later controls, local order saving, and refresh recovery.
- Added the Contact Artist page linked from the homepage and Works Archive page.
- Removed the local Messages inbox/API path; Contact now opens a mail draft and no longer stores local messages.

## v1.0.0 - 2026-06-07

- Created the first public project version for GitHub.
- Built the static MT Presence homepage with a sticky black-and-white to color hero transition.
- Added the Infinite Marquee Gallery for selected works.
- Added the Works Archive page with local image samples, upload support, ratio classification, Abstract/Concrete filters, and IndexedDB persistence.
- Added deferred PostgreSQL/Supabase database design files for future backend integration.
- Confirmed the database is not active in this version; the project currently runs as a static frontend.
