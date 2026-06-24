-- MT Presence photography archive database schema.
-- Target: PostgreSQL 14+ / Supabase-compatible SQL.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  CREATE TYPE public.image_content_type AS ENUM ('abstract', 'concrete');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE TYPE public.image_display_mode AS ENUM ('black_white', 'color');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE TYPE public.image_source_type AS ENUM ('upload', 'local_sample', 'generated', 'external');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE TYPE public.image_visibility AS ENUM ('draft', 'private', 'published', 'archived');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE TYPE public.image_asset_kind AS ENUM ('original', 'display', 'thumbnail', 'square_slice');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS public.ratio_categories (
  code text PRIMARY KEY,
  label text NOT NULL UNIQUE,
  numerator integer NOT NULL CHECK (numerator > 0),
  denominator integer NOT NULL CHECK (denominator > 0),
  target_aspect_ratio numeric(12, 8)
    GENERATED ALWAYS AS (numerator::numeric / denominator::numeric) STORED,
  sort_order integer NOT NULL UNIQUE
);

INSERT INTO public.ratio_categories (code, label, numerator, denominator, sort_order)
VALUES
  ('one_to_one', '1:1', 1, 1, 10),
  ('four_to_three', '4:3', 4, 3, 5),
  ('four_to_five', '4:5', 4, 5, 20),
  ('two_to_three', '2:3', 2, 3, 30),
  ('three_to_two', '3:2', 3, 2, 40),
  ('sixteen_to_nine', '16:9', 16, 9, 50),
  ('panorama', 'Panorama', 2, 1, 60)
ON CONFLICT (code) DO UPDATE
SET
  label = EXCLUDED.label,
  numerator = EXCLUDED.numerator,
  denominator = EXCLUDED.denominator,
  sort_order = EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS public.artists (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_user_id uuid UNIQUE,
  display_name text NOT NULL,
  slug text NOT NULL UNIQUE,
  email text UNIQUE,
  bio text,
  website_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  artist_id uuid REFERENCES public.artists(id) ON DELETE SET NULL,
  title text NOT NULL,
  slug text UNIQUE,
  description text,
  curatorial_note text,
  artist_statement text,
  series text,
  source_type public.image_source_type NOT NULL DEFAULT 'upload',
  visibility public.image_visibility NOT NULL DEFAULT 'draft',
  original_filename text,
  original_width integer NOT NULL CHECK (original_width > 0),
  original_height integer NOT NULL CHECK (original_height > 0),
  original_aspect_ratio numeric(12, 8)
    GENERATED ALWAYS AS (original_width::numeric / original_height::numeric) STORED,
  ratio_category_code text NOT NULL REFERENCES public.ratio_categories(code),
  display_ratio_override numeric(12, 8) CHECK (display_ratio_override IS NULL OR display_ratio_override > 0),
  content_type public.image_content_type NOT NULL,
  display_mode public.image_display_mode NOT NULL,
  ai_model text,
  ai_confidence numeric(5, 4) CHECK (ai_confidence IS NULL OR ai_confidence BETWEEN 0 AND 1),
  ai_analysis jsonb NOT NULL DEFAULT '{}'::jsonb,
  exif jsonb NOT NULL DEFAULT '{}'::jsonb,
  sort_order integer NOT NULL DEFAULT 0,
  captured_at timestamptz,
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT images_content_display_mode_check CHECK (
    (content_type = 'abstract' AND display_mode = 'black_white')
    OR
    (content_type = 'concrete' AND display_mode = 'color')
  )
);

CREATE TABLE IF NOT EXISTS public.image_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  image_id uuid NOT NULL REFERENCES public.images(id) ON DELETE CASCADE,
  kind public.image_asset_kind NOT NULL,
  storage_bucket text NOT NULL,
  storage_path text NOT NULL,
  public_url text,
  url_expires_at timestamptz,
  mime_type text NOT NULL,
  byte_size bigint CHECK (byte_size IS NULL OR byte_size > 0),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  checksum_sha256 char(64),
  source_asset_id uuid REFERENCES public.image_assets(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (storage_bucket, storage_path),
  UNIQUE (image_id, kind, storage_path)
);

CREATE TABLE IF NOT EXISTS public.image_square_slices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  image_id uuid NOT NULL REFERENCES public.images(id) ON DELETE CASCADE,
  asset_id uuid NOT NULL UNIQUE REFERENCES public.image_assets(id) ON DELETE CASCADE,
  slice_index integer NOT NULL CHECK (slice_index >= 0),
  source_x integer NOT NULL DEFAULT 0 CHECK (source_x >= 0),
  source_y integer NOT NULL DEFAULT 0 CHECK (source_y >= 0),
  source_size integer NOT NULL CHECK (source_size > 0),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (image_id, slice_index),
  CONSTRAINT image_square_slices_square_check CHECK (width = height)
);

CREATE TABLE IF NOT EXISTS public.image_analysis_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  image_id uuid NOT NULL REFERENCES public.images(id) ON DELETE CASCADE,
  input_asset_id uuid REFERENCES public.image_assets(id) ON DELETE SET NULL,
  provider text NOT NULL,
  model_name text NOT NULL,
  content_type public.image_content_type NOT NULL,
  confidence numeric(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.image_tags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text NOT NULL,
  group_name text NOT NULL DEFAULT 'subject',
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (group_name, slug),
  UNIQUE (group_name, name)
);

CREATE TABLE IF NOT EXISTS public.image_taggings (
  image_id uuid NOT NULL REFERENCES public.images(id) ON DELETE CASCADE,
  tag_id uuid NOT NULL REFERENCES public.image_tags(id) ON DELETE CASCADE,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (image_id, tag_id)
);

ALTER TABLE public.image_tags
  ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0;

ALTER TABLE public.image_taggings
  ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0;

DO $$
BEGIN
  ALTER TABLE public.image_tags DROP CONSTRAINT IF EXISTS image_tags_name_key;
  ALTER TABLE public.image_tags DROP CONSTRAINT IF EXISTS image_tags_slug_key;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'image_tags_group_name_slug_key'
      AND conrelid = 'public.image_tags'::regclass
  ) THEN
    ALTER TABLE public.image_tags
      ADD CONSTRAINT image_tags_group_name_slug_key UNIQUE (group_name, slug);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'image_tags_group_name_name_key'
      AND conrelid = 'public.image_tags'::regclass
  ) THEN
    ALTER TABLE public.image_tags
      ADD CONSTRAINT image_tags_group_name_name_key UNIQUE (group_name, name);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.collections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  artist_id uuid REFERENCES public.artists(id) ON DELETE SET NULL,
  slug text NOT NULL UNIQUE,
  title text NOT NULL,
  description text,
  is_featured boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.collection_images (
  collection_id uuid NOT NULL REFERENCES public.collections(id) ON DELETE CASCADE,
  image_id uuid NOT NULL REFERENCES public.images(id) ON DELETE CASCADE,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (collection_id, image_id)
);

CREATE INDEX IF NOT EXISTS images_artist_id_idx
  ON public.images (artist_id);

CREATE INDEX IF NOT EXISTS images_archive_filter_idx
  ON public.images (visibility, content_type, ratio_category_code, uploaded_at DESC);

CREATE INDEX IF NOT EXISTS images_ratio_category_code_idx
  ON public.images (ratio_category_code);

CREATE INDEX IF NOT EXISTS images_uploaded_at_idx
  ON public.images (uploaded_at DESC);

CREATE INDEX IF NOT EXISTS image_assets_image_kind_idx
  ON public.image_assets (image_id, kind);

CREATE INDEX IF NOT EXISTS image_assets_source_asset_idx
  ON public.image_assets (source_asset_id);

CREATE INDEX IF NOT EXISTS image_square_slices_image_idx
  ON public.image_square_slices (image_id, slice_index);

CREATE INDEX IF NOT EXISTS image_analysis_events_image_idx
  ON public.image_analysis_events (image_id, created_at DESC);

CREATE INDEX IF NOT EXISTS image_tags_group_name_idx
  ON public.image_tags (group_name, sort_order, name);

CREATE INDEX IF NOT EXISTS image_taggings_tag_idx
  ON public.image_taggings (tag_id);

CREATE INDEX IF NOT EXISTS image_taggings_image_sort_idx
  ON public.image_taggings (image_id, sort_order, created_at);

CREATE INDEX IF NOT EXISTS collection_images_collection_sort_idx
  ON public.collection_images (collection_id, sort_order, created_at);

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.validate_square_slice_asset()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  asset_image_id uuid;
  asset_kind public.image_asset_kind;
  asset_width integer;
  asset_height integer;
BEGIN
  SELECT image_id, kind, width, height
  INTO asset_image_id, asset_kind, asset_width, asset_height
  FROM public.image_assets
  WHERE id = NEW.asset_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'square slice asset % does not exist', NEW.asset_id;
  END IF;

  IF asset_image_id IS DISTINCT FROM NEW.image_id THEN
    RAISE EXCEPTION 'square slice asset % belongs to image %, not image %',
      NEW.asset_id, asset_image_id, NEW.image_id;
  END IF;

  IF asset_kind <> 'square_slice' THEN
    RAISE EXCEPTION 'square slice asset % must have kind square_slice, got %',
      NEW.asset_id, asset_kind;
  END IF;

  IF asset_width <> NEW.width OR asset_height <> NEW.height THEN
    RAISE EXCEPTION 'square slice dimensions must match linked asset dimensions';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS artists_set_updated_at ON public.artists;
CREATE TRIGGER artists_set_updated_at
BEFORE UPDATE ON public.artists
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS images_set_updated_at ON public.images;
CREATE TRIGGER images_set_updated_at
BEFORE UPDATE ON public.images
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS collections_set_updated_at ON public.collections;
CREATE TRIGGER collections_set_updated_at
BEFORE UPDATE ON public.collections
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS image_square_slices_validate_asset ON public.image_square_slices;
CREATE TRIGGER image_square_slices_validate_asset
BEFORE INSERT OR UPDATE ON public.image_square_slices
FOR EACH ROW
EXECUTE FUNCTION public.validate_square_slice_asset();

CREATE OR REPLACE FUNCTION public.closest_ratio_category(_width integer, _height integer)
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT code
  FROM public.ratio_categories
  WHERE _width > 0 AND _height > 0
  ORDER BY abs((_width::numeric / _height::numeric) - target_aspect_ratio) ASC, sort_order ASC
  LIMIT 1;
$$;

CREATE OR REPLACE VIEW public.archive_image_view AS
SELECT
  i.id,
  i.artist_id,
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
  rc.target_aspect_ratio AS classified_aspect_ratio,
  COALESCE(i.display_ratio_override, rc.target_aspect_ratio) AS display_aspect_ratio,
  i.content_type,
  i.display_mode,
  i.ai_model,
  i.ai_confidence,
  i.ai_analysis,
  i.exif,
  i.sort_order,
  i.captured_at,
  i.uploaded_at,
  i.created_at,
  i.updated_at,
  original_asset.public_url AS original_url,
  original_asset.url_expires_at AS original_url_expires_at,
  original_asset.storage_bucket AS original_storage_bucket,
  original_asset.storage_path AS original_storage_path,
  display_asset.public_url AS display_url,
  display_asset.url_expires_at AS display_url_expires_at,
  display_asset.storage_bucket AS display_storage_bucket,
  display_asset.storage_path AS display_storage_path,
  thumbnail_asset.public_url AS thumbnail_url,
  thumbnail_asset.url_expires_at AS thumbnail_url_expires_at,
  COALESCE(display_asset.public_url, original_asset.public_url) AS image_url,
  COALESCE(display_asset.url_expires_at, original_asset.url_expires_at) AS image_url_expires_at,
  COALESCE(tag_list.tags, ARRAY[]::text[]) AS tags,
  COALESCE(tag_groups.tag_groups, '[]'::jsonb) AS tag_groups,
  (
    SELECT count(*)::integer
    FROM public.image_square_slices s
    WHERE s.image_id = i.id
  ) AS square_slice_count
FROM public.images i
JOIN public.ratio_categories rc
  ON rc.code = i.ratio_category_code
LEFT JOIN LATERAL (
  SELECT a.public_url, a.url_expires_at, a.storage_bucket, a.storage_path
  FROM public.image_assets a
  WHERE a.image_id = i.id AND a.kind = 'original'
  ORDER BY a.created_at DESC
  LIMIT 1
) original_asset ON true
LEFT JOIN LATERAL (
  SELECT a.public_url, a.url_expires_at, a.storage_bucket, a.storage_path
  FROM public.image_assets a
  WHERE a.image_id = i.id AND a.kind = 'display'
  ORDER BY a.created_at DESC
  LIMIT 1
) display_asset ON true
LEFT JOIN LATERAL (
  SELECT a.public_url, a.url_expires_at
  FROM public.image_assets a
  WHERE a.image_id = i.id AND a.kind = 'thumbnail'
  ORDER BY a.created_at DESC
  LIMIT 1
) thumbnail_asset ON true
LEFT JOIN LATERAL (
  SELECT array_agg(t.name ORDER BY t.group_name, it.sort_order, t.sort_order, t.name) AS tags
  FROM public.image_taggings it
  JOIN public.image_tags t
    ON t.id = it.tag_id
  WHERE it.image_id = i.id
) tag_list ON true
LEFT JOIN LATERAL (
  SELECT jsonb_agg(
    jsonb_build_object('label', grouped.group_name, 'tags', grouped.tags)
    ORDER BY grouped.group_sort_order, grouped.group_name
  ) AS tag_groups
  FROM (
    SELECT
      t.group_name,
      min(t.sort_order) AS group_sort_order,
      jsonb_agg(t.name ORDER BY it.sort_order, t.sort_order, t.name) AS tags
    FROM public.image_taggings it
    JOIN public.image_tags t
      ON t.id = it.tag_id
    WHERE it.image_id = i.id
    GROUP BY t.group_name
  ) grouped
) tag_groups ON true;
