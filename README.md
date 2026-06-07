# MT CIJIAN

MT CIJIAN is a static fine art photography portfolio prototype. Version `v1.0.0` focuses on the public homepage, selected works presentation, and a local Works Archive experience.

## Current Version

- Version: `1.0.0`
- Release label: `v1.0.0`
- Status: static frontend first version
- Database: deferred until the project is complete

## Features

- Sticky homepage hero transition from abstract black-and-white scenery to concrete color scenery.
- Infinite horizontal selected works gallery.
- Works Archive page with local photography samples.
- Upload flow that reads original image dimensions in the browser.
- Automatic ratio classification: `1:1`, `4:5`, `2:3`, `3:2`, `16:9`, `Panorama`.
- Abstract and Concrete filters.
- IndexedDB local persistence for uploaded images.
- Deferred PostgreSQL/Supabase schema and database design documentation for future backend work.

## Run Locally

This project has no package install step.

```bash
python3 -m http.server 8131
```

Then open:

```text
http://127.0.0.1:8131/
```

Works Archive:

```text
http://127.0.0.1:8131/works.html
```

## Project Files

- `index.html`: homepage.
- `works.html`: Works Archive page.
- `styles.css`: site styling and responsive layout.
- `script.js`: homepage scroll transition.
- `archive.js`: Works Archive data, upload, filters, ratio classification, and IndexedDB logic.
- `assets/`: local visual assets used by the site.
- `DATABASE_DESIGN.md`: deferred database design notes.
- `database/schema.sql`: deferred PostgreSQL/Supabase schema.
- `PROJECT_MAP.md`: maintained feature and file responsibility map.

## Notes

The current images are design-stage placeholders. They should be replaced with final MT works or properly licensed production assets before a formal public launch.
