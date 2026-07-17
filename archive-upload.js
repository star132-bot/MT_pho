window.MTArchiveUpload = (() => {
  const archiveSeedData = window.MTPresenceArchiveData || {};
  const ratioProfiles = archiveSeedData.ratioProfiles || [
    { label: "1:1", ratio: 1 / 1 },
    { label: "4:3", ratio: 4 / 3 },
    { label: "4:5", ratio: 4 / 5 },
    { label: "2:3", ratio: 2 / 3 },
    { label: "3:2", ratio: 3 / 2 },
    { label: "16:9", ratio: 16 / 9 },
    { label: "Panorama", ratio: 2 / 1 },
  ];

  const abstractKeywords = [
    "abstract",
    "texture",
    "shadow",
    "light",
    "pattern",
    "geometry",
    "minimal",
    "detail",
    "surface",
    "reflection",
  ];
  const concreteKeywords = [
    "people",
    "person",
    "portrait",
    "architecture",
    "building",
    "landscape",
    "mountain",
    "object",
    "forest",
    "river",
    "street",
  ];

  const LOCAL_STORAGE_BUCKET = "indexeddb-local";
  const DISPLAY_MAX_LONG_EDGE = 2300;
  const DISPLAY_FORCE_RESIZE_RATIO = 1.12;
  const DISPLAY_QUALITY = 0.86;
  const THUMBNAIL_MAX_LONG_EDGE = 640;
  const THUMBNAIL_QUALITY = 0.78;
  const SQUARE_SLICE_MAX_EDGE = 1400;
  const SQUARE_SLICE_QUALITY = 0.84;
  const DERIVATIVE_MIME_TYPE = "image/jpeg";

  function cleanText(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function classifyRatio(width, height) {
    const imageRatio = width / height;
    const closest = ratioProfiles.reduce(
      (best, item) => {
        const distance = Math.abs(imageRatio - item.ratio);
        return distance < best.distance ? { ...item, distance } : best;
      },
      { label: "1:1", distance: Number.POSITIVE_INFINITY },
    );
    return closest.label;
  }

  function ratioCategoryCode(label) {
    const codes = {
      "1:1": "one_to_one",
      "4:3": "four_to_three",
      "4:5": "four_to_five",
      "2:3": "two_to_three",
      "3:2": "three_to_two",
      "16:9": "sixteen_to_nine",
      Panorama: "panorama",
    };
    return codes[label] || "one_to_one";
  }

  function contentTypeCode(type) {
    const value = cleanText(type).toLowerCase();
    return value === "abstract" ? "abstract" : "concrete";
  }

  function displayModeForType(type) {
    return contentTypeCode(type) === "abstract" ? "black_white" : "color";
  }

  function contentTypeLabel(type) {
    return contentTypeCode(type) === "abstract" ? "Abstract" : "Concrete";
  }

  function yieldToMain() {
    return new Promise((resolve) => {
      window.setTimeout(resolve, 0);
    });
  }

  function isSquareRatio(width, height) {
    return Math.abs(width - height) <= Math.max(width, height) * 0.01;
  }

  function classifyContent(fileName = "") {
    const name = fileName.toLowerCase();
    if (abstractKeywords.some((keyword) => name.includes(keyword))) {
      return "abstract";
    }
    if (concreteKeywords.some((keyword) => name.includes(keyword))) {
      return "concrete";
    }
    return "concrete";
  }

  function normalizeCapturedDate(value) {
    const text = cleanText(value);
    if (!text) {
      return "";
    }
    const exifMatch = text.match(/^(\d{4}):(\d{2}):(\d{2})(?:\s+(.+))?$/);
    if (exifMatch) {
      return `${exifMatch[1]}-${exifMatch[2]}-${exifMatch[3]}`;
    }
    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) {
      return date.toISOString().slice(0, 10);
    }
    return text;
  }

  function hasCanvasExportSupport() {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext && canvas.toBlob);
  }

  function imageExtension(mimeType, fallback = "jpg") {
    if (mimeType === "image/png") {
      return "png";
    }
    if (mimeType === "image/webp") {
      return "webp";
    }
    if (mimeType === "image/gif") {
      return "gif";
    }
    return fallback;
  }

  function sanitizePathPart(value) {
    return (
      String(value || "image")
        .toLowerCase()
        .replace(/\.[^.]+$/, "")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 72) || "image"
    );
  }

  function buildStoragePath(imageId, kind, fileName, extension = "jpg", index = null) {
    const stem = sanitizePathPart(fileName);
    const suffix = index === null ? "" : `-${String(index + 1).padStart(2, "0")}`;
    return `draft/${imageId}/${kind}${suffix}-${stem}.${extension}`;
  }

  async function sha256HexFromBuffer(buffer) {
    if (!crypto?.subtle) {
      return null;
    }
    const digest = await crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  }

  async function sha256HexFromBlob(blob) {
    return sha256HexFromBuffer(await blob.arrayBuffer());
  }

  function readAscii(view, offset, length) {
    let value = "";
    for (let index = 0; index < length; index += 1) {
      const code = view.getUint8(offset + index);
      if (code === 0) {
        break;
      }
      value += String.fromCharCode(code);
    }
    return value.trim();
  }

  function parseExifValue(view, tiffStart, valueOffset, type, count, littleEndian) {
    const typeSize = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1 }[type] || 1;
    const byteLength = typeSize * count;
    const dataOffset = byteLength <= 4 ? valueOffset : tiffStart + view.getUint32(valueOffset, littleEndian);

    if (type === 2) {
      return readAscii(view, dataOffset, count);
    }
    if (type === 3) {
      return count === 1
        ? view.getUint16(dataOffset, littleEndian)
        : Array.from({ length: count }, (_, index) => view.getUint16(dataOffset + index * 2, littleEndian));
    }
    if (type === 4) {
      return count === 1
        ? view.getUint32(dataOffset, littleEndian)
        : Array.from({ length: count }, (_, index) => view.getUint32(dataOffset + index * 4, littleEndian));
    }
    if (type === 5) {
      const readRational = (offset) => {
        const numerator = view.getUint32(offset, littleEndian);
        const denominator = view.getUint32(offset + 4, littleEndian);
        return denominator ? numerator / denominator : null;
      };
      return count === 1
        ? readRational(dataOffset)
        : Array.from({ length: count }, (_, index) => readRational(dataOffset + index * 8));
    }
    return null;
  }

  function readExifIfd(view, tiffStart, ifdOffset, littleEndian, tagMap) {
    const values = {};
    const absoluteOffset = tiffStart + ifdOffset;
    if (absoluteOffset <= 0 || absoluteOffset + 2 > view.byteLength) {
      return values;
    }
    const entryCount = view.getUint16(absoluteOffset, littleEndian);
    for (let index = 0; index < entryCount; index += 1) {
      const entryOffset = absoluteOffset + 2 + index * 12;
      if (entryOffset + 12 > view.byteLength) {
        break;
      }
      const tag = view.getUint16(entryOffset, littleEndian);
      const key = tagMap[tag];
      if (!key) {
        continue;
      }
      const type = view.getUint16(entryOffset + 2, littleEndian);
      const count = view.getUint32(entryOffset + 4, littleEndian);
      values[key] = parseExifValue(view, tiffStart, entryOffset + 8, type, count, littleEndian);
    }
    return values;
  }

  function extractExif(buffer, mimeType) {
    if (mimeType !== "image/jpeg") {
      return { status: "unsupported_mime" };
    }
    const view = new DataView(buffer);
    let offset = 2;
    while (offset + 4 < view.byteLength) {
      if (view.getUint8(offset) !== 0xff) {
        break;
      }
      const marker = view.getUint8(offset + 1);
      const segmentLength = view.getUint16(offset + 2, false);
      if (marker === 0xe1 && readAscii(view, offset + 4, 6) === "Exif") {
        const tiffStart = offset + 10;
        const endian = readAscii(view, tiffStart, 2);
        const littleEndian = endian === "II";
        if (!littleEndian && endian !== "MM") {
          return { status: "invalid_endian" };
        }
        const firstIfdOffset = view.getUint32(tiffStart + 4, littleEndian);
        const ifd0 = readExifIfd(view, tiffStart, firstIfdOffset, littleEndian, {
          0x010f: "camera_make",
          0x0110: "camera_model",
          0x0112: "orientation",
          0x0131: "software",
          0x0132: "datetime",
          0x013b: "artist",
          0x8298: "copyright",
          0x8769: "exif_ifd_offset",
        });
        const exif =
          Number.isFinite(ifd0.exif_ifd_offset) && ifd0.exif_ifd_offset > 0
            ? readExifIfd(view, tiffStart, ifd0.exif_ifd_offset, littleEndian, {
                0x829a: "exposure_time",
                0x829d: "f_number",
                0x8827: "iso",
                0x9003: "datetime_original",
                0x9004: "datetime_digitized",
                0x920a: "focal_length",
                0xa434: "lens_model",
              })
            : {};
        delete ifd0.exif_ifd_offset;
        return { status: "parsed", ...ifd0, ...exif };
      }
      offset += 2 + segmentLength;
    }
    return { status: "not_found" };
  }

  async function createImageSource(blob) {
    if ("createImageBitmap" in window) {
      const bitmap = await createImageBitmap(blob);
      return {
        source: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        close: () => bitmap.close(),
      };
    }
    const url = URL.createObjectURL(blob);
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        URL.revokeObjectURL(url);
        resolve({
          source: image,
          width: image.naturalWidth,
          height: image.naturalHeight,
          close: () => {},
        });
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("Could not read image dimensions."));
      };
      image.src = url;
    });
  }

  function targetDimensions(width, height, maxLongEdge) {
    const longest = Math.max(width, height);
    const scale = longest > maxLongEdge ? maxLongEdge / longest : 1;
    return {
      width: Math.max(1, Math.round(width * scale)),
      height: Math.max(1, Math.round(height * scale)),
    };
  }

  function canvasToBlob(canvas, type = DERIVATIVE_MIME_TYPE, quality = DISPLAY_QUALITY) {
    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => {
          if (blob) {
            resolve(blob);
          } else {
            reject(new Error("Could not create image version."));
          }
        },
        type,
        quality,
      );
    });
  }

  async function drawImageVersion(source, sourceRect, outputSize, type, quality) {
    const canvas = document.createElement("canvas");
    canvas.width = outputSize.width;
    canvas.height = outputSize.height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
      throw new Error("Canvas is not available for image processing.");
    }
    context.drawImage(
      source,
      sourceRect.x,
      sourceRect.y,
      sourceRect.width,
      sourceRect.height,
      0,
      0,
      outputSize.width,
      outputSize.height,
    );
    return canvasToBlob(canvas, type, quality);
  }

  function createAsset({ imageId, kind, fileName, blob, width, height, checksum, index = null, sourceAssetId = null }) {
    const extension = kind === "original" ? imageExtension(blob.type) : "jpg";
    return {
      id: `${imageId}-${kind}${index === null ? "" : `-${index}`}`,
      image_id: imageId,
      kind,
      storage_bucket: LOCAL_STORAGE_BUCKET,
      storage_path: buildStoragePath(imageId, kind, fileName, extension, index),
      public_url: null,
      mime_type: blob.type || DERIVATIVE_MIME_TYPE,
      byte_size: blob.size,
      width,
      height,
      checksum_sha256: checksum,
      source_asset_id: sourceAssetId,
      blob,
    };
  }

  async function createDerivativeAsset({ imageId, kind, fileName, imageSource, maxLongEdge, quality, sourceAssetId }) {
    const size = targetDimensions(imageSource.width, imageSource.height, maxLongEdge);
    const blob = await drawImageVersion(
      imageSource.source,
      { x: 0, y: 0, width: imageSource.width, height: imageSource.height },
      size,
      DERIVATIVE_MIME_TYPE,
      quality,
    );
    return createAsset({
      imageId,
      kind,
      fileName,
      blob,
      width: size.width,
      height: size.height,
      checksum: await sha256HexFromBlob(blob),
      sourceAssetId,
    });
  }

  async function createSquareSlices(imageId, imageSource, fileName, sourceAssetId) {
    const { width, height } = imageSource;
    if (isSquareRatio(width, height)) {
      return { assets: [], squareSlices: [] };
    }
    const tileSize = Math.min(width, height);
    const longSide = Math.max(width, height);
    const tileCount = Math.ceil(longSide / tileSize);
    const assets = [];
    const squareSlices = [];
    const outputSize = Math.min(tileSize, SQUARE_SLICE_MAX_EDGE);

    for (let index = 0; index < tileCount; index += 1) {
      await yieldToMain();
      const offset = tileCount === 1 ? 0 : Math.round((longSide - tileSize) * (index / (tileCount - 1)));
      const sourceX = width >= height ? offset : 0;
      const sourceY = height > width ? offset : 0;
      const blob = await drawImageVersion(
        imageSource.source,
        { x: sourceX, y: sourceY, width: tileSize, height: tileSize },
        { width: outputSize, height: outputSize },
        DERIVATIVE_MIME_TYPE,
        SQUARE_SLICE_QUALITY,
      );
      const asset = createAsset({
        imageId,
        kind: "square_slice",
        fileName,
        blob,
        width: outputSize,
        height: outputSize,
        checksum: await sha256HexFromBlob(blob),
        index,
        sourceAssetId,
      });
      assets.push(asset);
      squareSlices.push({
        id: `${imageId}-slice-${index}`,
        image_id: imageId,
        asset_id: asset.id,
        slice_index: index,
        source_x: sourceX,
        source_y: sourceY,
        source_size: tileSize,
        width: outputSize,
        height: outputSize,
      });
    }
    return { assets, squareSlices };
  }

  function assetObjectUrl(asset) {
    if (!asset?.blob) {
      return null;
    }
    if (!asset.objectUrl) {
      asset.objectUrl = URL.createObjectURL(asset.blob);
    }
    return asset.objectUrl;
  }

  function preferredDisplayAsset(assets = []) {
    return assets.find((asset) => asset.kind === "display") || assets.find((asset) => asset.kind === "original") || null;
  }

  async function buildUploadedItem(file, task, index = 0) {
    const imageId = `upload-${Date.now()}-${index}`;
    task?.update?.("reading", 10, "Reading original file, dimensions, checksum, and metadata.");
    const originalBuffer = await file.arrayBuffer();
    const originalChecksum = await sha256HexFromBuffer(originalBuffer);
    const exif = extractExif(originalBuffer, file.type);
    const imageSource = await createImageSource(file);
    await yieldToMain();

    const ratio = classifyRatio(imageSource.width, imageSource.height);
    const contentType = classifyContent(file.name);
    const type = contentTypeLabel(contentType);
    const title = file.name.replace(/\.[^.]+$/, "") || "Uploaded Image";
    const originalAsset = createAsset({
      imageId,
      kind: "original",
      fileName: file.name,
      blob: file,
      width: imageSource.width,
      height: imageSource.height,
      checksum: originalChecksum,
    });
    const assets = [originalAsset];
    let squareSlices = [];
    let fallbackMessage = "";
    let displayAsset = originalAsset;

    if (hasCanvasExportSupport()) {
      task?.update?.("compressing", 32, "Creating display version for the archive.");
      const candidateDisplayAsset = await createDerivativeAsset({
        imageId,
        kind: "display",
        fileName: file.name,
        imageSource,
        maxLongEdge: DISPLAY_MAX_LONG_EDGE,
        quality: DISPLAY_QUALITY,
        sourceAssetId: originalAsset.id,
      });
      if (candidateDisplayAsset.byte_size < originalAsset.byte_size) {
        displayAsset = candidateDisplayAsset;
        assets.push(candidateDisplayAsset);
      } else if (Math.max(imageSource.width, imageSource.height) > DISPLAY_MAX_LONG_EDGE * DISPLAY_FORCE_RESIZE_RATIO) {
        displayAsset = candidateDisplayAsset;
        assets.push(candidateDisplayAsset);
        fallbackMessage = "Display version is dimension-optimized but not smaller than the original file.";
      } else {
        fallbackMessage = "Original is already smaller than the display version. Using original as display fallback.";
      }
      await yieldToMain();

      task?.update?.("compressing", 50, "Creating thumbnail for fast lists.");
      assets.push(
        await createDerivativeAsset({
          imageId,
          kind: "thumbnail",
          fileName: file.name,
          imageSource,
          maxLongEdge: THUMBNAIL_MAX_LONG_EDGE,
          quality: THUMBNAIL_QUALITY,
          sourceAssetId: originalAsset.id,
        }),
      );
      await yieldToMain();

      task?.update?.("slicing", 68, "Preparing square archive slices when needed.");
      const sliceResult = await createSquareSlices(imageId, imageSource, file.name, originalAsset.id);
      assets.push(...sliceResult.assets);
      squareSlices = sliceResult.squareSlices;
    } else {
      fallbackMessage = "Browser image compression is unavailable. Original saved and used as fallback.";
    }

    task?.update?.("analyzing", 78, "Applying local type and ratio classification.");
    await yieldToMain();

    const imageRecord = {
      id: imageId,
      title,
      description: "",
      curatorial_note: "",
      artist_statement: "",
      series: "",
      source_type: "upload",
      original_filename: file.name,
      original_width: imageSource.width,
      original_height: imageSource.height,
      ratio_category_code: ratioCategoryCode(ratio),
      content_type: contentType,
      display_mode: displayModeForType(contentType),
      exif,
      visibility: "draft",
      visibility_manually_set: false,
      sort_order: 0,
      captured_at: normalizeCapturedDate(exif.datetime_original || exif.datetime),
      tags: [],
      tag_groups: [],
    };

    const item = {
      id: imageId,
      title,
      src: assetObjectUrl(preferredDisplayAsset([displayAsset])),
      width: imageSource.width,
      height: imageSource.height,
      type,
      ratio,
      source: "Uploaded",
      createdAt: Date.now() + index,
      imageRecord,
      assets,
      squareSliceCount: squareSlices.length,
      squareSlices,
    };
    imageSource.close();
    return { item, fallbackMessage };
  }

  function prepareStoredItem(item) {
    return {
      id: item.id,
      title: item.title,
      width: item.width,
      height: item.height,
      type: item.type,
      ratio: item.ratio,
      source: item.source,
      createdAt: item.createdAt,
      sortOrder: item.sortOrder,
      description: item.description || item.imageRecord?.description || "",
      curatorial_note: item.curatorial_note || item.imageRecord?.curatorial_note || "",
      artist_statement: item.artist_statement || item.imageRecord?.artist_statement || "",
      captured_at: item.captured_at || item.imageRecord?.captured_at || "",
      series: item.series || item.imageRecord?.series || "",
      tags: item.tags || item.imageRecord?.tags || [],
      tag_groups: item.tag_groups || item.imageRecord?.tag_groups || [],
      imageTags: item.imageTags || [],
      imageTaggings: item.imageTaggings || [],
      image_url: item.image_url || "",
      thumbnail_url: item.thumbnail_url || "",
      display_mode: item.display_mode || item.imageRecord?.display_mode || "",
      imageRecord: item.imageRecord || null,
      assets: (item.assets || []).map(({ objectUrl, ...asset }) => asset),
      squareSliceCount: item.squareSliceCount || 0,
      squareSlices: item.squareSlices || [],
    };
  }

  return {
    buildUploadedItem,
    prepareStoredItem,
  };
})();
