const ratioProfiles = [
  { label: "1:1", ratio: 1 / 1 },
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
  "animal",
  "object",
  "forest",
  "river",
  "street",
];

const DB_NAME = "mt-cijian-archive";
const DB_VERSION = 1;
const DB_STORE = "images";

const sampleItems = [
  {
    id: "sample-1",
    title: "Square Shadow Field",
    src: "assets/archive/abstract-square-01.jpg",
    width: 1600,
    height: 1600,
    type: "Abstract",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-2",
    title: "Vertical Light Pattern",
    src: "assets/archive/abstract-4x5-01.jpg",
    width: 1600,
    height: 2000,
    type: "Abstract",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-3",
    title: "Concrete Valley",
    src: "assets/archive/concrete-2x3-01.jpg",
    width: 1600,
    height: 2400,
    type: "Concrete",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-4",
    title: "Architectural Plane",
    src: "assets/archive/concrete-3x2-01.jpg",
    width: 2400,
    height: 1600,
    type: "Concrete",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-5",
    title: "Wide Weather",
    src: "assets/archive/concrete-16x9-01.jpg",
    width: 1920,
    height: 1080,
    type: "Concrete",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-6",
    title: "Panorama Surface",
    src: "assets/archive/abstract-panorama-01.jpg",
    width: 2400,
    height: 1200,
    type: "Abstract",
    ratio: "Panorama",
    source: "Local sample",
  },
  {
    id: "sample-7",
    title: "Minimal Stone Detail",
    src: "assets/archive/abstract-4x5-02.jpg",
    width: 1600,
    height: 2000,
    type: "Abstract",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-8",
    title: "Identifiable Coast",
    src: "assets/archive/concrete-2x3-02.jpg",
    width: 1600,
    height: 2400,
    type: "Concrete",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-9",
    title: "Horizontal Silence",
    src: "assets/archive/abstract-3x2-01.jpg",
    width: 2400,
    height: 1600,
    type: "Abstract",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-10",
    title: "Color Object Study",
    src: "assets/archive/concrete-square-01.jpg",
    width: 1600,
    height: 1600,
    type: "Concrete",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-11",
    title: "Abstract Wide Interval",
    src: "assets/archive/abstract-16x9-01.jpg",
    width: 1920,
    height: 1080,
    type: "Abstract",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-12",
    title: "Concrete Animal Study",
    src: "assets/archive/concrete-4x5-01.jpg",
    width: 1600,
    height: 2000,
    type: "Concrete",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-13",
    title: "Concrete Panorama",
    src: "assets/archive/concrete-panorama-01.jpg",
    width: 2400,
    height: 1200,
    type: "Concrete",
    ratio: "Panorama",
    source: "Local sample",
  },
  {
    id: "sample-14",
    title: "Square Abstract Interval",
    src: "assets/archive/abstract-square-02.jpg",
    width: 1600,
    height: 1600,
    type: "Abstract",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-15",
    title: "Concrete Square Study",
    src: "assets/archive/concrete-square-02.jpg",
    width: 1600,
    height: 1600,
    type: "Concrete",
    ratio: "1:1",
    source: "Local sample",
  },
  {
    id: "sample-16",
    title: "Vertical Abstract Surface",
    src: "assets/archive/abstract-4x5-03.jpg",
    width: 1600,
    height: 2000,
    type: "Abstract",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-17",
    title: "Concrete Vertical Field",
    src: "assets/archive/concrete-4x5-02.jpg",
    width: 1600,
    height: 2000,
    type: "Concrete",
    ratio: "4:5",
    source: "Local sample",
  },
  {
    id: "sample-18",
    title: "Tall Abstract Study",
    src: "assets/archive/abstract-2x3-01.jpg",
    width: 1600,
    height: 2400,
    type: "Abstract",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-19",
    title: "Tall Concrete Study",
    src: "assets/archive/concrete-2x3-03.jpg",
    width: 1600,
    height: 2400,
    type: "Concrete",
    ratio: "2:3",
    source: "Local sample",
  },
  {
    id: "sample-20",
    title: "Abstract Horizontal Plane",
    src: "assets/archive/abstract-3x2-02.jpg",
    width: 2400,
    height: 1600,
    type: "Abstract",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-21",
    title: "Concrete Horizontal Plane",
    src: "assets/archive/concrete-3x2-02.jpg",
    width: 2400,
    height: 1600,
    type: "Concrete",
    ratio: "3:2",
    source: "Local sample",
  },
  {
    id: "sample-22",
    title: "Abstract Wide Field",
    src: "assets/archive/abstract-16x9-02.jpg",
    width: 1920,
    height: 1080,
    type: "Abstract",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-23",
    title: "Concrete Wide Field",
    src: "assets/archive/concrete-16x9-02.jpg",
    width: 1920,
    height: 1080,
    type: "Concrete",
    ratio: "16:9",
    source: "Local sample",
  },
  {
    id: "sample-24",
    title: "Abstract Long Horizon",
    src: "assets/archive/abstract-panorama-02.jpg",
    width: 2400,
    height: 1200,
    type: "Abstract",
    ratio: "Panorama",
    source: "Local sample",
  },
  {
    id: "sample-25",
    title: "Concrete Long Horizon",
    src: "assets/archive/concrete-panorama-02.jpg",
    width: 2400,
    height: 1200,
    type: "Concrete",
    ratio: "Panorama",
    source: "Local sample",
  },
];

const gallery = document.querySelector("[data-archive-gallery]");
const count = document.querySelector("[data-archive-count]");
const uploadInput = document.querySelector("[data-upload-input]");
const typeFilters = document.querySelector("[data-type-filters]");
const ratioFilters = document.querySelector("[data-ratio-filters]");

let activeType = "All";
let activeRatio = "All";
let archiveItems = [...sampleItems];
let archiveDb = null;

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

function ratioCssValue(label) {
  const match = ratioProfiles.find((item) => item.label === label);
  return match ? `${match.ratio}` : "1";
}

function isSquareRatio(width, height) {
  return Math.abs(width - height) <= Math.max(width, height) * 0.01;
}

function classifyContent(fileName = "") {
  // Replace this function with a vision-model call when the archive has a backend.
  const name = fileName.toLowerCase();
  if (abstractKeywords.some((keyword) => name.includes(keyword))) {
    return "Abstract";
  }
  if (concreteKeywords.some((keyword) => name.includes(keyword))) {
    return "Concrete";
  }

  return "Concrete";
}

async function analyzeImageContent(file) {
  return classifyContent(file.name);
}

function openArchiveDatabase() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      reject(new Error("IndexedDB is not available."));
      return;
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(DB_STORE)) {
        database.createObjectStore(DB_STORE, { keyPath: "id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionStore(mode = "readonly") {
  return archiveDb.transaction(DB_STORE, mode).objectStore(DB_STORE);
}

function getStoredItems() {
  return new Promise((resolve, reject) => {
    if (!archiveDb) {
      resolve([]);
      return;
    }

    const request = transactionStore().getAll();
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
}

function saveStoredItem(item, file) {
  return new Promise((resolve, reject) => {
    if (!archiveDb) {
      resolve();
      return;
    }

    const storedItem = {
      id: item.id,
      title: item.title,
      width: item.width,
      height: item.height,
      type: item.type,
      ratio: item.ratio,
      source: item.source,
      createdAt: item.createdAt,
      squareSliceCount: item.squareSliceCount || 0,
      squareSlices: item.squareSlices || [],
      blob: file,
    };

    const request = transactionStore("readwrite").put(storedItem);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

function reviveStoredItem(item) {
  return {
    id: item.id,
    title: item.title,
    src: URL.createObjectURL(item.blob),
    width: item.width,
    height: item.height,
    type: item.type,
    ratio: item.ratio,
    source: item.source || "Uploaded",
    createdAt: item.createdAt || 0,
    squareSliceCount: item.squareSliceCount || 0,
    squareSlices: item.squareSlices || [],
  };
}

function readImageDimensions(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);

    image.onload = () => {
      resolve({
        url,
        width: image.naturalWidth,
        height: image.naturalHeight,
      });
    };

    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`Could not read ${file.name}`));
    };

    image.src = url;
  });
}

function loadImageFromUrl(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not prepare square slices."));
    image.src = url;
  });
}

function canvasToBlob(canvas, type = "image/jpeg", quality = 0.9) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("Could not create square slice."));
        }
      },
      type,
      quality,
    );
  });
}

async function createSquareSlices(imageUrl, width, height) {
  if (isSquareRatio(width, height)) {
    return [];
  }

  const image = await loadImageFromUrl(imageUrl);
  const tileSize = Math.min(width, height);
  const longSide = Math.max(width, height);
  const tileCount = Math.ceil(longSide / tileSize);
  const slices = [];

  for (let index = 0; index < tileCount; index += 1) {
    const offset = tileCount === 1 ? 0 : Math.round((longSide - tileSize) * (index / (tileCount - 1)));
    const sourceX = width >= height ? offset : 0;
    const sourceY = height > width ? offset : 0;
    const canvas = document.createElement("canvas");
    canvas.width = tileSize;
    canvas.height = tileSize;

    const context = canvas.getContext("2d");
    context.drawImage(image, sourceX, sourceY, tileSize, tileSize, 0, 0, tileSize, tileSize);

    const blob = await canvasToBlob(canvas, "image/jpeg", 0.9);
    slices.push({
      index,
      width: tileSize,
      height: tileSize,
      blob,
    });
  }

  return slices;
}

function filteredItems() {
  return archiveItems.filter((item) => {
    const typeMatch = activeType === "All" || item.type === activeType;
    const ratioMatch = activeRatio === "All" || item.ratio === activeRatio;
    return typeMatch && ratioMatch;
  });
}

function renderGallery() {
  const items = filteredItems();
  count.textContent = `${items.length} image${items.length === 1 ? "" : "s"}`;
  gallery.classList.toggle("is-ratio-filtered", activeRatio !== "All");
  gallery.dataset.activeRatio = activeRatio;

  gallery.innerHTML = items
    .map(
      (item) => `
        <article class="archive-item" data-type="${item.type}" data-ratio="${item.ratio}">
          <figure class="archive-image-frame" style="--display-ratio: ${ratioCssValue(item.ratio)};">
            <img src="${item.src}" alt="${item.title}" loading="lazy" />
          </figure>
          <div class="archive-item-meta">
            <h3>${item.title}</h3>
            <dl>
              <div>
                <dt>Type</dt>
                <dd>${item.type}</dd>
              </div>
              <div>
                <dt>Ratio</dt>
                <dd>${item.ratio}</dd>
              </div>
              <div>
                <dt>Size</dt>
                <dd>${item.width}x${item.height}</dd>
              </div>
              <div>
                <dt>1:1 Slices</dt>
                <dd>${item.squareSliceCount || 0}</dd>
              </div>
            </dl>
          </div>
        </article>
      `,
    )
    .join("");
}

function setActiveButton(container, selector, value) {
  container.querySelectorAll("button").forEach((button) => {
    const isActive = button.matches(`[${selector}="${value}"]`);
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

typeFilters.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter-type]");
  if (!button) {
    return;
  }

  activeType = button.dataset.filterType;
  setActiveButton(typeFilters, "data-filter-type", activeType);
  renderGallery();
});

ratioFilters.addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter-ratio]");
  if (!button) {
    return;
  }

  activeRatio = button.dataset.filterRatio;
  setActiveButton(ratioFilters, "data-filter-ratio", activeRatio);
  renderGallery();
});

uploadInput.addEventListener("change", async (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) {
    return;
  }

  const uploaded = await Promise.all(
    files.map(async (file, index) => {
      const image = await readImageDimensions(file);
      const type = await analyzeImageContent(file, image);
      const squareSlices = await createSquareSlices(image.url, image.width, image.height);
      return {
        id: `upload-${Date.now()}-${index}`,
        title: file.name.replace(/\.[^.]+$/, "") || "Uploaded Image",
        src: image.url,
        width: image.width,
        height: image.height,
        type,
        ratio: classifyRatio(image.width, image.height),
        source: "Uploaded",
        createdAt: Date.now() + index,
        squareSliceCount: squareSlices.length,
        squareSlices,
        file,
      };
    }),
  );

  await Promise.all(uploaded.map((item) => saveStoredItem(item, item.file)));
  archiveItems.unshift(...uploaded.map(({ file, squareSlices, ...item }) => item));
  uploadInput.value = "";
  renderGallery();
});

async function initArchive() {
  try {
    archiveDb = await openArchiveDatabase();
    const storedItems = await getStoredItems();
    const uploadedItems = storedItems
      .filter((item) => item.blob)
      .map(reviveStoredItem)
      .sort((a, b) => b.createdAt - a.createdAt);

    archiveItems = [...uploadedItems, ...sampleItems];
  } catch {
    archiveDb = null;
    archiveItems = [...sampleItems];
  }

  renderGallery();
}

initArchive();
