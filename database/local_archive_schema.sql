-- MT Presence local archive database schema.
-- Target: SQLite 3 for local development and seed verification.
--
-- This mirrors the deferred PostgreSQL/Supabase archive model closely enough
-- to validate image metadata, assets, tags, taggings, and collections locally.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ratio_categories (
  code TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  numerator INTEGER NOT NULL CHECK (numerator > 0),
  denominator INTEGER NOT NULL CHECK (denominator > 0),
  target_aspect_ratio REAL NOT NULL,
  sort_order INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS artists (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  email TEXT UNIQUE,
  bio TEXT,
  website_url TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
  id TEXT PRIMARY KEY,
  artist_id TEXT REFERENCES artists(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  slug TEXT UNIQUE,
  description TEXT,
  curatorial_note TEXT,
  artist_statement TEXT,
  series TEXT,
  source_type TEXT NOT NULL DEFAULT 'upload'
    CHECK (source_type IN ('upload', 'local_sample', 'generated', 'external')),
  visibility TEXT NOT NULL DEFAULT 'draft'
    CHECK (visibility IN ('draft', 'private', 'published', 'archived')),
  original_filename TEXT,
  original_width INTEGER NOT NULL CHECK (original_width > 0),
  original_height INTEGER NOT NULL CHECK (original_height > 0),
  original_aspect_ratio REAL NOT NULL,
  ratio_category_code TEXT NOT NULL REFERENCES ratio_categories(code),
  display_ratio_override REAL CHECK (display_ratio_override IS NULL OR display_ratio_override > 0),
  content_type TEXT NOT NULL CHECK (content_type IN ('abstract', 'concrete')),
  display_mode TEXT NOT NULL CHECK (display_mode IN ('black_white', 'color')),
  ai_model TEXT,
  ai_confidence REAL CHECK (ai_confidence IS NULL OR ai_confidence BETWEEN 0 AND 1),
  ai_analysis TEXT NOT NULL DEFAULT '{}',
  exif TEXT NOT NULL DEFAULT '{}',
  sort_order INTEGER NOT NULL DEFAULT 0,
  captured_at TEXT,
  uploaded_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (
    (content_type = 'abstract' AND display_mode = 'black_white')
    OR
    (content_type = 'concrete' AND display_mode = 'color')
  )
);

CREATE TABLE IF NOT EXISTS image_assets (
  id TEXT PRIMARY KEY,
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('original', 'display', 'thumbnail', 'square_slice')),
  storage_bucket TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  public_url TEXT,
  url_expires_at TEXT,
  mime_type TEXT NOT NULL,
  byte_size INTEGER CHECK (byte_size IS NULL OR byte_size > 0),
  width INTEGER NOT NULL CHECK (width > 0),
  height INTEGER NOT NULL CHECK (height > 0),
  checksum_sha256 TEXT CHECK (checksum_sha256 IS NULL OR length(checksum_sha256) = 64),
  source_asset_id TEXT REFERENCES image_assets(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  UNIQUE (storage_bucket, storage_path),
  UNIQUE (image_id, kind, storage_path)
);

CREATE TABLE IF NOT EXISTS image_square_slices (
  id TEXT PRIMARY KEY,
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL UNIQUE REFERENCES image_assets(id) ON DELETE CASCADE,
  slice_index INTEGER NOT NULL CHECK (slice_index >= 0),
  source_x INTEGER NOT NULL DEFAULT 0 CHECK (source_x >= 0),
  source_y INTEGER NOT NULL DEFAULT 0 CHECK (source_y >= 0),
  source_size INTEGER NOT NULL CHECK (source_size > 0),
  width INTEGER NOT NULL CHECK (width > 0),
  height INTEGER NOT NULL CHECK (height > 0),
  created_at TEXT NOT NULL,
  UNIQUE (image_id, slice_index),
  CHECK (width = height)
);

CREATE TABLE IF NOT EXISTS image_analysis_events (
  id TEXT PRIMARY KEY,
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  input_asset_id TEXT REFERENCES image_assets(id) ON DELETE SET NULL,
  provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK (content_type IN ('abstract', 'concrete')),
  confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  result TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_tags (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  group_name TEXT NOT NULL DEFAULT 'Subject',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE (group_name, slug),
  UNIQUE (group_name, name)
);

CREATE TABLE IF NOT EXISTS image_taggings (
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  tag_id TEXT NOT NULL REFERENCES image_tags(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  PRIMARY KEY (image_id, tag_id)
);

CREATE TABLE IF NOT EXISTS collections (
  id TEXT PRIMARY KEY,
  artist_id TEXT REFERENCES artists(id) ON DELETE SET NULL,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  description TEXT,
  is_featured INTEGER NOT NULL DEFAULT 0 CHECK (is_featured IN (0, 1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_images (
  collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  PRIMARY KEY (collection_id, image_id)
);

CREATE INDEX IF NOT EXISTS images_artist_id_idx
  ON images (artist_id);

CREATE INDEX IF NOT EXISTS images_archive_filter_idx
  ON images (visibility, content_type, ratio_category_code, uploaded_at DESC);

CREATE INDEX IF NOT EXISTS images_ratio_category_code_idx
  ON images (ratio_category_code);

CREATE INDEX IF NOT EXISTS images_uploaded_at_idx
  ON images (uploaded_at DESC);

CREATE INDEX IF NOT EXISTS image_assets_image_kind_idx
  ON image_assets (image_id, kind);

CREATE INDEX IF NOT EXISTS image_assets_source_asset_idx
  ON image_assets (source_asset_id);

CREATE INDEX IF NOT EXISTS image_square_slices_image_idx
  ON image_square_slices (image_id, slice_index);

CREATE INDEX IF NOT EXISTS image_analysis_events_image_idx
  ON image_analysis_events (image_id, created_at DESC);

CREATE INDEX IF NOT EXISTS image_tags_group_name_idx
  ON image_tags (group_name, sort_order, name);

CREATE INDEX IF NOT EXISTS image_taggings_tag_idx
  ON image_taggings (tag_id);

CREATE INDEX IF NOT EXISTS collection_images_collection_sort_idx
  ON collection_images (collection_id, sort_order, created_at);

DROP VIEW IF EXISTS archive_image_view;

CREATE VIEW archive_image_view AS
SELECT
  i.id,
  i.title,
  i.slug,
  i.description,
  i.curatorial_note,
  i.artist_statement,
  i.series,
  i.source_type,
  i.visibility,
  i.original_filename,
  i.original_width,
  i.original_height,
  i.original_aspect_ratio,
  i.ratio_category_code,
  rc.label AS ratio_label,
  COALESCE(i.display_ratio_override, rc.target_aspect_ratio) AS display_aspect_ratio,
  i.content_type,
  i.display_mode,
  i.sort_order,
  i.captured_at,
  i.uploaded_at,
  i.created_at,
  i.updated_at,
  COALESCE(display_asset.public_url, original_asset.public_url) AS image_url,
  thumbnail_asset.public_url AS thumbnail_url,
  original_asset.public_url AS original_url,
  COALESCE(
    (
      SELECT json_group_array(name)
      FROM (
        SELECT t.name
        FROM image_taggings it
        JOIN image_tags t ON t.id = it.tag_id
        WHERE it.image_id = i.id
        ORDER BY t.sort_order, it.sort_order, t.name
      )
    ),
    '[]'
  ) AS tags,
  COALESCE(
    (
      SELECT json_group_array(json_object('label', group_name, 'tags', json(tags_json)))
      FROM (
        SELECT
          grouped.group_name,
          json_group_array(grouped.name) AS tags_json,
          MIN(grouped.group_order) AS group_order
        FROM (
          SELECT t.group_name, t.name, t.sort_order AS group_order, it.sort_order
          FROM image_taggings it
          JOIN image_tags t ON t.id = it.tag_id
          WHERE it.image_id = i.id
          ORDER BY t.sort_order, it.sort_order, t.name
        ) grouped
        GROUP BY grouped.group_name
        ORDER BY group_order, group_name
      )
    ),
    '[]'
  ) AS tag_groups
FROM images i
JOIN ratio_categories rc ON rc.code = i.ratio_category_code
LEFT JOIN image_assets original_asset
  ON original_asset.image_id = i.id
  AND original_asset.kind = 'original'
LEFT JOIN image_assets display_asset
  ON display_asset.image_id = i.id
  AND display_asset.kind = 'display'
LEFT JOIN image_assets thumbnail_asset
  ON thumbnail_asset.image_id = i.id
  AND thumbnail_asset.kind = 'thumbnail';
