# MT Presence

MT Presence is a fine art photography portfolio prototype. Version `v1.0.0` started as a static first version; the current workspace is a static site with browser-local Works management.

## Current Version

- Version: `1.0.0`
- Release label: `v1.0.0`
- Status: static frontend plus browser-local Works management
- Database: Works Archive backend deferred; local SQLite archive seed, validation workflow, read API, and existing-work metadata write API available for metadata/design verification

## Features

- Sticky homepage hero transition from abstract black-and-white scenery to concrete color scenery.
- Infinite horizontal selected works gallery.
- Four-moment image-led Statement section, placed after Selected Works, with one image per text passage and a final Enter Works call to action.
- Works Archive page with read-only local SQLite API data when `data/archive.db` exists, with local photography sample fallback.
- Works Archive work viewer with full-screen enlarged images, fit/actual-size zoom, catalog-style metadata, keyboard navigation, and grouped visual tags.
- Internal Works Viewer Editor for importing works; maintaining the viewer title, series, notes, metadata, visibility, sort order, and grouped tags; and editing homepage hero images/text in the IndexedDB transition layer.
- Upload flow that reads original image dimensions, checksum, and basic EXIF in the browser.
- Local multi-version image asset generation for uploads: original, display, thumbnail, and square slices.
- Automatic ratio classification: `1:1`, `4:3`, `4:5`, `2:3`, `3:2`, `16:9`, `Panorama`.
- Abstract and Concrete filters.
- Arrange mode for ordering Works Archive items, with drag controls, Earlier/Later buttons, and local order persistence.
- IndexedDB local persistence for uploaded images and generated asset metadata, aligned with the deferred `images` / `image_assets` / `image_square_slices` schema.
- Contact Artist page linked from the homepage and Works Archive page.
- Deferred PostgreSQL/Supabase schema and database design documentation for future backend work.
- Local SQLite archive seed, Archive read/write metadata API, and automated validation workflow for checking image metadata, assets, grouped tags, collections, and Archive view output before backend integration.

## Run Locally

This project has no package install step.

Use the local static server:

```bash
python3 server.py --port 8131
```

Then open:

```text
http://127.0.0.1:8131/
```

Works Archive:

```text
http://127.0.0.1:8131/works.html
```

Internal Works Viewer Editor:

```text
http://127.0.0.1:8131/manage.html
```

Seed the local archive database:

```bash
python3 scripts/seed_local_archive_db.py
```

This creates `data/archive.db` with local sample image metadata, asset rows, grouped tags, taggings, and an `archive-featured` collection. Local `.db` files are ignored by Git.

When `data/archive.db` exists, `server.py` exposes the published archive rows at:

```text
http://127.0.0.1:8131/api/archive/images
```

`works.html` reads this endpoint first and falls back to the local sample data if the database or API is unavailable.

The internal editor can also sync existing seeded works back into the local SQLite database:

```text
PATCH http://127.0.0.1:8131/api/archive/images/{id}
```

This metadata write path updates existing `images`, `image_tags`, and `image_taggings` rows only. Uploaded image files still stay in the browser IndexedDB transition layer.

Validate the local archive database workflow:

```bash
python3 scripts/validate_local_archive_db.py
```

This creates a temporary SQLite database, runs the seed process, and checks table/view presence, foreign keys, counts, multi-version assets, tag JSON, ratio categories, and local asset paths.

Contact page:

```text
http://127.0.0.1:8131/contact.html
```

The contact form opens the visitor's email app with a prepared draft. There is no local message inbox or message database.

## Project Files

- `index.html`: homepage; reads editable hero and Statement content from local homepage settings when available.
- `works.html`: public Works Archive page.
- `manage.html`: internal Works import, Works Viewer metadata, and homepage content editor.
- `styles.css`: site styling and responsive layout.
- `script.js`: homepage navigation scroll state, editable homepage settings hydration, and Statement section activation.
- `archive-data.js`: shared Works Archive base sample data used by public Works and the internal editor.
- `archive-upload.js`: shared browser-side work import pipeline for dimensions, EXIF, checksum, display/thumbnail, and square slice records.
- `archive.js`: public Works Archive API loading, local sample fallback, filters, work viewer, Arrange mode, published-record reading, saved metadata merge, and IndexedDB logic.
- `manage.js`: internal import flow, metadata editor, local SQLite metadata sync for existing seeded works, homepage settings editor, dirty tracking, grouped tag editing, and IndexedDB save/revert fallback.
- `contact.html`: Contact Artist page and inquiry form.
- `contact.js`: Contact Artist form validation, mail draft generation, and toast feedback.
- `server.py`: local static server, `GET /api/archive/images`, and `PATCH /api/archive/images/{id}` metadata endpoint backed by `data/archive.db`.
- `database/local_archive_schema.sql`: SQLite schema for local Works Archive database verification.
- `scripts/seed_local_archive_db.py`: seeds `data/archive.db` from `archive-data.js`.
- `scripts/validate_local_archive_db.py`: validates the local SQLite archive workflow in a temporary database.
- `.github/workflows/database.yml`: GitHub Actions workflow that runs the database validation command.
- `assets/`: local visual assets used by the site.
- `DATABASE_DESIGN.md`: deferred database design notes.
- `database/schema.sql`: deferred PostgreSQL/Supabase schema.
- `PROJECT_MAP.md`: maintained feature and file responsibility map.

## Notes

The current images are design-stage placeholders. They should be replaced with final MT works or properly licensed production assets before a formal public launch.
