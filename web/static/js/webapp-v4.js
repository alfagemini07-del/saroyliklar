(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const DEFAULT_CENTER = [40.167796262859696, 67.80262130723996];
  const DEFAULT_ZOOM = 16;
  const SATELLITE_TILES = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const TRANSPORT_TILES = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}";
  const LABEL_TILES = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
  const STREET_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const params = new URLSearchParams(window.location.search);
  const devTelegramId = params.get("dev_tg_id");

  const state = {
    view: "home",
    category: "all",
    mapCategory: "all",
    query: "",
    categories: [],
    products: [],
    stores: [],
    profile: null,
    skip: 0,
    pageSize: 20,
    hasMore: false,
    map: null,
    mapCluster: null,
    mapRequest: null,
    mapTimer: null,
    mapLayers: null,
    userLocationLayer: null,
    pickerMap: null,
    pickerTarget: null,
  };

  const elements = {
    appShell: qs("#app-shell"),
    accessGate: qs("#access-gate"),
    accessGateTitle: qs("#access-gate-title"),
    accessGateText: qs("#access-gate-text"),
    searchWrap: qs("#search-wrap"),
    searchInput: qs("#search-input"),
    clearSearch: qs("#clear-search"),
    categoryRail: qs("#category-rail"),
    productGrid: qs("#product-grid"),
    productCount: qs("#product-count"),
    loadMore: qs("#load-more"),
    storeList: qs("#store-list"),
    mapFilter: qs("#map-filter"),
    mapPreview: qs("#map-preview"),
    mapStatus: qs("#map-status"),
    profileContent: qs("#profile-content"),
    detailSheet: qs("#detail-sheet"),
    detailContent: qs("#detail-content"),
    sheetBackdrop: qs("#sheet-backdrop"),
    composeModal: qs("#compose-modal"),
    composeTitle: qs("#compose-title"),
    storeForm: qs("#store-form"),
    productForm: qs("#product-form"),
    mapPicker: qs("#map-picker"),
    coordinateBar: qs("#coordinate-bar"),
    toast: qs("#toast"),
    mediaViewer: qs("#media-viewer"),
    mediaViewerTitle: qs("#media-viewer-title"),
    mediaViewerStage: qs("#media-viewer-stage"),
    mediaViewerContent: qs("#media-viewer-content"),
    mediaViewerTools: qs("#media-viewer-tools"),
  };

  const viewer = { scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0 };

  function escapeHtml(value = "") {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function refreshIcons(root = document) {
    window.lucide?.createIcons({ root });
  }

  let toastTimer;
  function toast(message, error = false) {
    clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.toggle("error", error);
    elements.toast.classList.add("show");
    toastTimer = setTimeout(() => elements.toast.classList.remove("show"), 2800);
  }

  function apiUrl(path) {
    if (!path.startsWith("/api/webapp") && !path.startsWith("/api/market")) return path;
    const url = new URL(path, window.location.origin);
    if (devTelegramId) url.searchParams.set("dev_tg_id", devTelegramId);
    return `${url.pathname}${url.search}`;
  }

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (tg?.initData) {
      headers.set("X-Telegram-Init-Data", tg.initData);
      headers.set("Authorization", `tma ${tg.initData}`);
    }
    const fetchOptions = { ...options };
    const timeoutMs = Number(fetchOptions.timeoutMs) || 15000;
    delete fetchOptions.timeoutMs;
    const timeoutController = fetchOptions.signal ? null : new AbortController();
    const timeoutId = timeoutController ? setTimeout(() => timeoutController.abort(), timeoutMs) : null;
    try {
      const response = await fetch(apiUrl(path), { ...fetchOptions, headers, signal: fetchOptions.signal || timeoutController.signal });
      const contentType = response.headers.get("content-type") || "";
      const data = contentType.includes("application/json") ? await response.json() : null;
      if (!response.ok) {
        const detail = data?.detail;
        const message = Array.isArray(detail)
          ? detail.map((item) => item.msg).join("; ")
          : detail || "So'rov bajarilmadi";
        throw new Error(message);
      }
      return data;
    } catch (error) {
      if (timeoutController?.signal.aborted) throw new Error("Server javobi kechikdi. Qayta urinib ko'ring");
      throw error;
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }
  }

  function initials(name) {
    return String(name || "S").trim().charAt(0).toUpperCase() || "S";
  }

  function avatarHtml(url, name, className = "store-avatar") {
    const content = url
      ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(name)}" loading="lazy">`
      : escapeHtml(initials(name));
    return `<span class="${className}">${content}</span>`;
  }

  function mediaHtml(item, className = "product-media", controls = false) {
    const url = escapeHtml(item.media || "");
    const title = escapeHtml(item.title || "Mahsulot");
    if (!url) return `<div class="${className}"></div>`;
    if (item.media_type === "video") {
      return `<div class="${className}"><video src="${url}" ${controls ? "controls" : "preload=\"metadata\""} playsinline></video>${controls ? "" : '<span class="video-badge"><i data-lucide="play"></i></span>'}</div>`;
    }
    const expand = controls ? ` data-expand-media="${url}" data-media-title="${title}" role="button" tabindex="0"` : "";
    const hint = controls ? '<span class="media-zoom-hint"><i data-lucide="zoom-in"></i></span>' : "";
    return `<div class="${className}"${expand}><img src="${url}" alt="${title}" loading="lazy">${hint}</div>`;
  }

  function applyViewerTransform() {
    const image = qs("img", elements.mediaViewerContent);
    if (!image) return;
    image.style.transform = `translate3d(${viewer.x}px, ${viewer.y}px, 0) scale(${viewer.scale})`;
  }

  function setViewerZoom(nextScale) {
    viewer.scale = Math.max(1, Math.min(4, nextScale));
    if (viewer.scale === 1) viewer.x = viewer.y = 0;
    applyViewerTransform();
  }

  function openMediaViewer(url, title, mediaType = "image") {
    viewer.scale = 1; viewer.x = 0; viewer.y = 0;
    elements.mediaViewerTitle.textContent = title || "Mahsulot rasmi";
    elements.mediaViewer.classList.toggle("video-mode", mediaType === "video");
    elements.mediaViewerContent.innerHTML = mediaType === "video"
      ? `<video src="${escapeHtml(url)}" controls autoplay playsinline></video>`
      : `<img src="${escapeHtml(url)}" alt="${escapeHtml(title || "Mahsulot rasmi")}">`;
    elements.mediaViewer.hidden = false;
    elements.mediaViewer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeMediaViewer() {
    const video = qs("video", elements.mediaViewerContent);
    video?.pause();
    elements.mediaViewer.hidden = true;
    elements.mediaViewer.setAttribute("aria-hidden", "true");
    elements.mediaViewerContent.innerHTML = "";
    document.body.style.overflow = "";
  }

  function priceText(product) {
    return product.price?.formatted || "Narxi kelishiladi";
  }

  function verifiedHtml(store) {
    return store.is_verified
      ? '<span class="verified" title="Tasdiqlangan"><i data-lucide="badge-check"></i></span>'
      : "";
  }

  function emptyState(icon, title, text) {
    return `<div class="empty-state"><div><span class="empty-icon"><i data-lucide="${icon}"></i></span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></div></div>`;
  }

  function productCard(product) {
    return `<button class="product-card" type="button" data-product-id="${escapeHtml(product.id)}">
      ${mediaHtml(product)}
      <div class="product-body">
        <h3>${escapeHtml(product.title)}</h3>
        <div class="product-price">${escapeHtml(priceText(product))}</div>
        <div class="product-store">
          ${avatarHtml(product.store?.avatar, product.store?.name, "mini-avatar")}
          <span>${escapeHtml(product.store?.name || "Do'kon")}</span>
        </div>
      </div>
    </button>`;
  }

  function storeRow(store) {
    return `<button class="store-row" type="button" data-store-id="${escapeHtml(store.id)}">
      ${avatarHtml(store.avatar, store.name)}
      <span class="store-info">
        <h3>${escapeHtml(store.name)} ${verifiedHtml(store)}</h3>
        <p>${escapeHtml(store.category_name || "Do'kon")}</p>
        <span class="store-address"><i data-lucide="map-pin"></i><span>${escapeHtml(store.address || "Manzil ko'rsatilmagan")}</span></span>
      </span>
      <span class="row-chevron"><i data-lucide="chevron-right"></i></span>
    </button>`;
  }

  async function loadCategories() {
    state.categories = await request("/api/market/categories");
    const chips = [
      '<button class="category-chip active" type="button" data-category="all">Barchasi</button>',
      ...state.categories.map((category) => `<button class="category-chip" type="button" data-category="${escapeHtml(category.id)}"><span class="category-icon">${escapeHtml(category.icon)}</span>${escapeHtml(category.name)}</button>`),
    ];
    elements.categoryRail.innerHTML = chips.join("");

    const options = state.categories
      .map((category) => `<option value="${escapeHtml(category.id)}">${escapeHtml(category.icon)} ${escapeHtml(category.name)}</option>`)
      .join("");
    qsa(".category-select").forEach((select) => { select.innerHTML = options; });
    elements.mapFilter.innerHTML = `<select aria-label="Do'kon turi"><option value="all">Barcha do'konlar</option>${options}</select>`;
  }

  async function loadProducts({ append = false } = {}) {
    if (!append) {
      state.skip = 0;
      elements.productGrid.innerHTML = Array.from({ length: 6 }, () => '<div class="product-card"><div class="product-media skeleton"></div><div class="product-body"><div class="skeleton" style="height:34px"></div></div></div>').join("");
    }
    elements.loadMore.disabled = true;
    try {
      const query = new URLSearchParams({
        category: state.category,
        q: state.query,
        skip: String(append ? state.skip : 0),
        limit: String(state.pageSize),
      });
      const data = await request(`/api/market/products?${query}`);
      state.products = append ? [...state.products, ...data.products] : data.products;
      state.skip = state.products.length;
      state.hasMore = data.has_more;
      elements.productCount.textContent = `${data.total} ta`;
      elements.productGrid.innerHTML = state.products.length
        ? state.products.map(productCard).join("")
        : emptyState("package-search", "Mahsulot topilmadi", "Qidiruv yoki tur filtrini o'zgartirib ko'ring.");
      elements.loadMore.hidden = !state.hasMore;
      refreshIcons(elements.productGrid);
    } catch (error) {
      elements.productGrid.innerHTML = emptyState("wifi-off", "Ma'lumot yuklanmadi", error.message);
      elements.loadMore.hidden = true;
      refreshIcons(elements.productGrid);
    } finally {
      elements.loadMore.disabled = false;
    }
  }

  async function loadStores() {
    elements.storeList.innerHTML = Array.from({ length: 4 }, () => '<div class="store-row"><span class="store-avatar skeleton"></span><span class="skeleton" style="height:60px"></span></div>').join("");
    try {
      const query = new URLSearchParams({ category: "all", q: state.query });
      const data = await request(`/api/market/stores?${query}`);
      state.stores = data.stores;
      elements.storeList.innerHTML = state.stores.length
        ? state.stores.map(storeRow).join("")
        : emptyState("store", "Do'kon topilmadi", "Qidiruvni o'zgartirib ko'ring.");
      refreshIcons(elements.storeList);
    } catch (error) {
      elements.storeList.innerHTML = emptyState("wifi-off", "Ma'lumot yuklanmadi", error.message);
      refreshIcons(elements.storeList);
    }
  }

  function configureHeader() {
    const searchable = state.view === "home" || state.view === "stores";
    elements.searchWrap.hidden = !searchable;
    qs("#header-locate").hidden = state.view !== "map";
    elements.searchInput.placeholder = state.view === "stores"
      ? "Do'kon nomi yoki manzilini qidiring"
      : "Mahsulot yoki do'kon qidiring";
  }

  async function showView(view) {
    state.view = view;
    qsa(".view").forEach((section) => section.classList.toggle("active", section.id === `${view}-view`));
    qsa(".bottom-nav [data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
    configureHeader();
    if (view === "stores") await loadStores();
    if (view === "profile") await loadProfile();
    if (view === "map") {
      initMap();
      setTimeout(() => {
        if (state.map) {
          state.map.invalidateSize();
          loadMapStores();
        } else {
          elements.mapStatus.textContent = "Xarita yuklanmadi. Internetni tekshiring";
          elements.mapStatus.classList.add("empty");
        }
      }, 80);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function initMap() {
    if (state.map || !window.L) return;
    state.map = L.map("market-map", { zoomControl: true, minZoom: 5, maxZoom: 20 }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    const satellite = L.tileLayer(SATELLITE_TILES, {
      minZoom: 5,
      maxZoom: 20,
      maxNativeZoom: 18,
      keepBuffer: 3,
      updateWhenZooming: false,
      attribution: "Imagery &copy; Esri",
    });
    const streets = L.tileLayer(STREET_TILES, {
      minZoom: 5,
      maxZoom: 20,
      maxNativeZoom: 19,
      keepBuffer: 3,
      updateWhenZooming: false,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    });
    const transport = L.tileLayer(TRANSPORT_TILES, {
      minZoom: 5,
      maxZoom: 20,
      maxNativeZoom: 18,
      pane: "overlayPane",
      attribution: "Roads &copy; Esri, HERE, Garmin, OpenStreetMap contributors",
    });
    const labels = L.tileLayer(LABEL_TILES, {
      minZoom: 5,
      maxZoom: 20,
      maxNativeZoom: 18,
      pane: "overlayPane",
      attribution: "Labels &copy; Esri",
    });
    satellite.addTo(state.map);
    transport.addTo(state.map);
    labels.addTo(state.map);
    state.mapLayers = { satellite, streets, transport, labels };
    L.control.layers(
      { "Sun'iy yo'ldosh": satellite, "Ko'chalar": streets },
      { "Yo'llar": transport, "Joy nomlari": labels },
      { position: "topright", collapsed: true },
    ).addTo(state.map);
    state.map.on("baselayerchange", ({ layer }) => {
      if (layer === streets) {
        state.map.removeLayer(transport);
        state.map.removeLayer(labels);
      } else {
        if (!state.map.hasLayer(transport)) transport.addTo(state.map);
        if (!state.map.hasLayer(labels)) labels.addTo(state.map);
      }
    });
    state.mapCluster = typeof L.markerClusterGroup === "function"
      ? L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 44 })
      : L.layerGroup();
    state.map.addLayer(state.mapCluster);
    state.map.on("moveend", () => {
      clearTimeout(state.mapTimer);
      state.mapTimer = setTimeout(loadMapStores, 220);
    });
  }

  function markerIcon(store) {
    const color = store.category_color || "#07865f";
    const icon = store.category_icon || "📦";
    return L.divIcon({
      className: "custom-map-icon",
      html: `<div class="store-marker" style="--marker-color:${escapeHtml(color)}"><span aria-hidden="true">${escapeHtml(icon)}</span></div>`,
      iconSize: [42, 48],
      iconAnchor: [21, 45],
      tooltipAnchor: [0, -42],
    });
  }

  async function loadMapStores() {
    if (!state.map || state.view !== "map") return;
    state.mapRequest?.abort();
    state.mapRequest = new AbortController();
    const bounds = state.map.getBounds();
    const query = new URLSearchParams({
      category: state.mapCategory,
      north: String(bounds.getNorth()),
      south: String(bounds.getSouth()),
      east: String(bounds.getEast()),
      west: String(bounds.getWest()),
    });
    try {
      const data = await request(`/api/market/map?${query}`, { signal: state.mapRequest.signal });
      state.mapCluster.clearLayers();
      elements.mapPreview.hidden = true;
      const validStores = data.stores.filter((store) => Number.isFinite(Number(store.lat)) && Number.isFinite(Number(store.lng)));
      validStores.forEach((store) => {
        const coordinates = [Number(store.lat), Number(store.lng)];
        const marker = L.marker(coordinates, { icon: markerIcon(store), title: store.name, riseOnHover: true });
        marker.bindTooltip(`<strong>${escapeHtml(store.name)}</strong><br>${escapeHtml(store.category_name || "Do'kon")}`, {
          className: "store-map-tooltip",
          direction: "top",
          opacity: 0.96,
        });
        marker.on("click", () => showMapPreview(store));
        state.mapCluster.addLayer(marker);
      });
      elements.mapStatus.textContent = validStores.length ? `${validStores.length} ta do'kon` : "Faol do'kon topilmadi";
      elements.mapStatus.classList.toggle("empty", !validStores.length);
    } catch (error) {
      if (error.name !== "AbortError") toast(error.message, true);
    }
  }

  function showMapPreview(store) {
    elements.mapPreview.hidden = false;
    const destination = `${Number(store.lat)},${Number(store.lng)}`;
    elements.mapPreview.innerHTML = `<div class="map-preview-inner">
      <button class="map-preview-store" type="button" data-store-id="${escapeHtml(store.id)}">
        ${avatarHtml(store.avatar, store.name)}
        <span><h3>${escapeHtml(store.name)}</h3><p>${escapeHtml(store.category_icon || "📦")} ${escapeHtml(store.address || store.category_name || "Do'kon")}</p></span>
      </button>
      <a class="map-route-button" href="https://www.google.com/maps/dir/?api=1&amp;destination=${escapeHtml(destination)}" target="_blank" rel="noopener" aria-label="Yo'nalish" title="Yo'nalish"><i data-lucide="route"></i></a>
    </div>`;
    refreshIcons(elements.mapPreview);
  }

  function locate(map = state.map) {
    if (!navigator.geolocation || !map) {
      toast("Joylashuvni aniqlab bo'lmadi", true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const point = [coords.latitude, coords.longitude];
        map.setView(point, 17, { animate: true });
        if (map === state.map) {
          state.userLocationLayer?.remove();
          const accuracy = L.circle(point, {
            radius: Math.min(coords.accuracy || 20, 200),
            color: "#1684d6",
            weight: 1,
            fillColor: "#1684d6",
            fillOpacity: 0.1,
            interactive: false,
          });
          const dot = L.circleMarker(point, {
            radius: 7,
            color: "#ffffff",
            weight: 3,
            fillColor: "#1684d6",
            fillOpacity: 1,
          }).bindTooltip("Sizning joylashuvingiz", { direction: "top" });
          state.userLocationLayer = L.layerGroup([accuracy, dot]).addTo(map);
        }
      },
      () => toast("Joylashuvga ruxsat berilmadi", true),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  async function openProduct(productId) {
    try {
      const product = await request(`/api/market/products/${encodeURIComponent(productId)}`);
      elements.detailContent.innerHTML = `${mediaHtml(product, "detail-media", true)}
        <div class="detail-body">
          <h1>${escapeHtml(product.title)}</h1>
          <div class="detail-price">${escapeHtml(priceText(product))}</div>
          <p class="detail-description">${escapeHtml(product.description || "Mahsulot haqida qo'shimcha ma'lumot berilmagan.")}</p>
          <button class="store-link" type="button" data-store-id="${escapeHtml(product.store.id)}">
            ${avatarHtml(product.store.avatar, product.store.name)}
            <span><strong>${escapeHtml(product.store.name)}</strong><span>${escapeHtml(product.store.address || "Do'kon profiliga o'tish")}</span></span>
            <i data-lucide="chevron-right"></i>
          </button>
          <div class="detail-actions"><button class="secondary-button" type="button" data-store-id="${escapeHtml(product.store.id)}"><i data-lucide="store"></i>Do'kon</button><a class="primary-button" href="${escapeHtml(contactHref(product.store))}" target="_blank" rel="noopener"><i data-lucide="phone"></i>Bog'lanish</a></div>
        </div>`;
      refreshIcons(elements.detailContent);
      openSheet();
    } catch (error) {
      toast(error.message, true);
    }
  }

  function contactHref(store) {
    if (store.telegram) return `https://t.me/${String(store.telegram).replace(/[^A-Za-z0-9_]/g, "")}`;
    return `tel:${String(store.phone || "").replace(/[^+\d]/g, "")}`;
  }

  async function openStore(storeId) {
    try {
      const store = await request(`/api/market/stores/${encodeURIComponent(storeId)}`);
      const cover = store.cover ? `<img src="${escapeHtml(store.cover)}" alt="${escapeHtml(store.name)}">` : "";
      elements.detailContent.innerHTML = `<div class="store-hero-cover">${cover}${avatarHtml(store.avatar, store.name, "store-hero-logo")}</div>
        <div class="detail-body">
          <h1>${escapeHtml(store.name)} ${verifiedHtml(store)}</h1>
          <p class="detail-description">${escapeHtml(store.description || "Do'kon haqida ma'lumot berilmagan.")}</p>
          <div class="store-meta-list">
            <div><i data-lucide="map-pin"></i><span>${escapeHtml(store.address || "Manzil ko'rsatilmagan")}</span></div>
            ${store.working_hours ? `<div><i data-lucide="clock-3"></i><span>${escapeHtml(store.working_hours)}</span></div>` : ""}
            ${store.phone ? `<div><i data-lucide="phone"></i><span>${escapeHtml(store.phone)}</span></div>` : ""}
          </div>
          <div class="detail-actions"><a class="primary-button" href="${escapeHtml(contactHref(store))}" target="_blank" rel="noopener"><i data-lucide="phone"></i>Bog'lanish</a><button class="secondary-button" type="button" data-show-store-map="${escapeHtml(store.id)}"><i data-lucide="map"></i>Xaritada</button></div>
          <div class="profile-section-title"><h2>Mahsulotlar</h2><span>${store.products.length} ta</span></div>
          <div class="detail-products">${store.products.length ? store.products.map(productCard).join("") : emptyState("package", "Mahsulot yo'q", "Do'kon hali katalog qo'shmagan.")}</div>
        </div>`;
      refreshIcons(elements.detailContent);
      openSheet();
    } catch (error) {
      toast(error.message, true);
    }
  }

  function openSheet() {
    elements.sheetBackdrop.hidden = false;
    elements.detailSheet.classList.add("open");
    elements.detailSheet.setAttribute("aria-hidden", "false");
  }

  function closeSheet() {
    elements.detailSheet.classList.remove("open");
    elements.detailSheet.setAttribute("aria-hidden", "true");
    setTimeout(() => { elements.sheetBackdrop.hidden = true; }, 250);
  }

  function statusName(status) {
    return { active: "Faol", pending: "Tekshiruvda", rejected: "Rad etilgan", inactive: "Yopiq" }[status] || status;
  }

  function ownProductRow(product) {
    return `<article class="own-product">
      ${mediaHtml(product, "own-product-media")}
      <div><h3>${escapeHtml(product.title)}</h3><p>${escapeHtml(product.price == null ? "Narxi kelishiladi" : `${Number(product.price).toLocaleString("uz-UZ")} ${product.currency}`)}</p></div>
      <div class="own-product-actions"><button type="button" data-edit-product="${escapeHtml(product.id)}" aria-label="Tahrirlash"><i data-lucide="pencil"></i></button><button class="danger" type="button" data-delete-product="${escapeHtml(product.id)}" aria-label="O'chirish"><i data-lucide="trash-2"></i></button></div>
    </article>`;
  }

  async function loadProfile() {
    elements.profileContent.innerHTML = emptyState("loader-circle", "Yuklanmoqda", "Profil ma'lumotlari olinmoqda.");
    refreshIcons(elements.profileContent);
    try {
      state.profile = await request("/api/webapp/me");
      renderProfile();
    } catch (error) {
      state.profile = null;
      const telegramHint = !tg?.initData && !devTelegramId ? " Web ilovani Telegram bot ichidan oching." : "";
      elements.profileContent.innerHTML = emptyState("shield-alert", "Profil ochilmadi", `${error.message}.${telegramHint}`);
      refreshIcons(elements.profileContent);
    }
  }

  function renderProfile() {
    const { user, store, products } = state.profile;
    const userHeader = `<div class="user-strip"><span class="user-avatar">${escapeHtml(initials(user.full_name))}</span><div><h1>${escapeHtml(user.full_name || "Foydalanuvchi")}</h1><p>${escapeHtml(user.phone || "Telefon ko'rsatilmagan")}</p></div></div>`;
    if (!store) {
      elements.profileContent.innerHTML = `${userHeader}<div class="open-store-empty"><span class="empty-icon"><i data-lucide="store"></i></span><h2>Do'koningizni oching</h2><p>Manzilni xaritada belgilang va mahsulotlaringizni mahallaga ko'rsating.</p><button class="primary-button" type="button" data-open-store-form><i data-lucide="plus"></i>Do'kon ochish</button></div>`;
      refreshIcons(elements.profileContent);
      return;
    }
    const cover = store.cover ? `<img src="${escapeHtml(store.cover)}" alt="${escapeHtml(store.name)}">` : "";
    elements.profileContent.innerHTML = `${userHeader}
      <section class="profile-store">
        <div class="profile-cover">${cover}${avatarHtml(store.avatar, store.name, "profile-logo")}</div>
        <div class="profile-store-body">
          <div class="profile-title-row"><h2>${escapeHtml(store.name)}</h2><span class="status-chip ${escapeHtml(store.status)}">${escapeHtml(statusName(store.status))}</span></div>
          <p>${escapeHtml(store.address || store.description || "Do'kon manzili kiritilmagan")}</p>
          <div class="profile-buttons"><button class="secondary-button" type="button" data-edit-store><i data-lucide="settings-2"></i>Tahrirlash</button><button class="primary-button" type="button" data-add-product><i data-lucide="plus"></i>Mahsulot</button></div>
        </div>
      </section>
      <div class="profile-section-title"><h2>Mahsulotlarim</h2><span>${products.length} ta</span></div>
      <div class="own-products">${products.length ? products.map(ownProductRow).join("") : emptyState("package-plus", "Katalog bo'sh", "Birinchi mahsulotingizni qo'shing.")}</div>`;
    refreshIcons(elements.profileContent);
  }

  function setFormMediaPreview(form) {
    const preview = qs(".media-preview", form);
    const files = qsa('input[type="file"]', form).flatMap((input) => [...input.files]);
    preview.innerHTML = files.map((file) => {
      const url = URL.createObjectURL(file);
      return file.type.startsWith("video/")
        ? `<span class="preview-item"><video src="${url}" muted></video></span>`
        : `<span class="preview-item"><img src="${url}" alt="Tanlangan rasm"></span>`;
    }).join("");
  }

  function filesWithinLimit(form) {
    const oversized = qsa('input[type="file"]', form)
      .flatMap((input) => [...input.files])
      .find((file) => file.size > 10 * 1024 * 1024);
    if (!oversized) return true;
    toast(`${oversized.name} 10 MB limitdan katta`, true);
    return false;
  }

  function openCompose(type, item = null) {
    elements.storeForm.hidden = type !== "store";
    elements.productForm.hidden = type !== "product";
    if (type === "store") prepareStoreForm(item);
    if (type === "product") prepareProductForm(item);
    elements.composeModal.classList.add("open");
    elements.composeModal.setAttribute("aria-hidden", "false");
    elements.composeModal.scrollTop = 0;
    refreshIcons(elements.composeModal);
  }

  function closeCompose() {
    elements.composeModal.classList.remove("open");
    elements.composeModal.setAttribute("aria-hidden", "true");
  }

  function prepareStoreForm(store = null) {
    elements.storeForm.reset();
    elements.composeTitle.textContent = store ? "Do'konni tahrirlash" : "Do'kon ochish";
    elements.storeForm.elements.mode.value = store ? "edit" : "create";
    qs(".submit-button", elements.storeForm).textContent = store ? "O'zgarishlarni saqlash" : "Do'konni yuborish";
    qs(".media-preview", elements.storeForm).innerHTML = "";
    if (!store) return;
    ["name", "category", "phone", "description", "address", "lat", "lng", "working_hours", "telegram", "instagram", "website"].forEach((name) => {
      if (elements.storeForm.elements[name]) elements.storeForm.elements[name].value = store[name] ?? "";
    });
    const label = qs('[data-location-form="store"] span');
    label.textContent = store.lat && store.lng ? "Joylashuv belgilangan" : "Do'konni xaritada belgilang";
  }

  function prepareProductForm(product = null) {
    elements.productForm.reset();
    elements.composeTitle.textContent = product ? "Mahsulotni tahrirlash" : "Mahsulot qo'shish";
    elements.productForm.elements.product_id.value = product?.id || "";
    qs("#product-media-field").hidden = false;
    qs("#availability-field").hidden = !product;
    qs(".submit-button", elements.productForm).textContent = product ? "O'zgarishlarni saqlash" : "Mahsulotni qo'shish";
    qs(".media-preview", elements.productForm).innerHTML = product?.media
      ? `<span class="preview-item">${product.media_type === "video" ? `<video src="${escapeHtml(product.media)}" muted></video>` : `<img src="${escapeHtml(product.media)}" alt="${escapeHtml(product.title)}">`}</span>`
      : "";
    if (!product) return;
    elements.productForm.elements.title.value = product.title || "";
    elements.productForm.elements.description.value = product.description || "";
    elements.productForm.elements.price.value = product.price ?? "";
    elements.productForm.elements.currency.value = product.currency || "UZS";
    elements.productForm.elements.is_available.checked = product.is_available !== false;
  }

  async function ensureCompose() {
    await loadProfile();
    if (!state.profile) {
      toast("Web ilovani Telegram bot ichidan oching", true);
      return;
    }
    openCompose(state.profile.store ? "product" : "store");
  }

  function openLocationPicker(form) {
    state.pickerTarget = form;
    elements.mapPicker.classList.add("open");
    elements.mapPicker.setAttribute("aria-hidden", "false");
    const lat = Number(form.elements.lat.value) || DEFAULT_CENTER[0];
    const lng = Number(form.elements.lng.value) || DEFAULT_CENTER[1];
    setTimeout(() => {
      if (!state.pickerMap) {
        state.pickerMap = L.map("picker-map", { zoomControl: true, minZoom: 5, maxZoom: 20 }).setView([lat, lng], form.elements.lat.value ? 16 : DEFAULT_ZOOM);
        L.tileLayer(SATELLITE_TILES, {
          minZoom: 5,
          maxZoom: 20,
          maxNativeZoom: 18,
          keepBuffer: 3,
          updateWhenZooming: false,
          attribution: "Imagery &copy; Esri",
        }).addTo(state.pickerMap);
        L.tileLayer(TRANSPORT_TILES, {
          minZoom: 5,
          maxZoom: 20,
          maxNativeZoom: 18,
          pane: "overlayPane",
          attribution: "Roads &copy; Esri, HERE, Garmin, OpenStreetMap contributors",
        }).addTo(state.pickerMap);
        L.tileLayer(LABEL_TILES, {
          minZoom: 5,
          maxZoom: 20,
          maxNativeZoom: 18,
          pane: "overlayPane",
          attribution: "Labels &copy; Esri",
        }).addTo(state.pickerMap);
        state.pickerMap.on("move", updatePickerCoordinates);
      } else {
        state.pickerMap.setView([lat, lng], 16);
        state.pickerMap.invalidateSize();
      }
      updatePickerCoordinates();
    }, 80);
  }

  function updatePickerCoordinates() {
    const center = state.pickerMap?.getCenter();
    if (center) elements.coordinateBar.textContent = `${center.lat.toFixed(6)}, ${center.lng.toFixed(6)}`;
  }

  function closeLocationPicker() {
    elements.mapPicker.classList.remove("open");
    elements.mapPicker.setAttribute("aria-hidden", "true");
  }

  function confirmLocation() {
    const center = state.pickerMap?.getCenter();
    if (!center || !state.pickerTarget) return;
    state.pickerTarget.elements.lat.value = center.lat.toFixed(7);
    state.pickerTarget.elements.lng.value = center.lng.toFixed(7);
    qs('[data-location-form="store"] span').textContent = "Joylashuv belgilandi";
    closeLocationPicker();
  }

  async function submitStore(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = qs(".submit-button", form);
    if (!form.elements.lat.value || !form.elements.lng.value) {
      toast("Do'konni xaritada belgilang", true);
      return;
    }
    if (!filesWithinLimit(form)) return;
    button.disabled = true;
    try {
      const editing = form.elements.mode.value === "edit";
      const data = await request("/api/webapp/store", {
        method: editing ? "PUT" : "POST",
        body: new FormData(form),
        timeoutMs: 90000,
      });
      toast(data.message);
      closeCompose();
      await loadProfile();
      await loadStores();
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  async function submitProduct(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = qs(".submit-button", form);
    const productId = form.elements.product_id.value;
    const formData = new FormData(form);
    if (!filesWithinLimit(form)) return;
    if (productId) {
      if (!form.elements.media.files.length) formData.delete("media");
      formData.delete("is_available");
      formData.set("is_available", form.elements.is_available.checked ? "true" : "false");
    } else if (!form.elements.media.files.length) {
      toast("Mahsulot rasmini yoki videosini tanlang", true);
      return;
    }
    button.disabled = true;
    const buttonLabel = button.textContent;
    button.textContent = "Saqlanmoqda...";
    try {
      const data = await request(productId ? `/api/webapp/products/${encodeURIComponent(productId)}` : "/api/webapp/products", {
        method: productId ? "PUT" : "POST",
        body: formData,
        timeoutMs: 90000,
      });
      toast(data.message);
      closeCompose();
      await Promise.all([loadProfile(), loadProducts()]);
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = buttonLabel;
    }
  }

  async function deleteProduct(productId) {
    if (!window.confirm("Mahsulotni o'chirasizmi?")) return;
    try {
      await request(`/api/webapp/products/${encodeURIComponent(productId)}`, { method: "DELETE" });
      toast("Mahsulot o'chirildi");
      await Promise.all([loadProfile(), loadProducts()]);
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function showStoreOnMap(storeId) {
    try {
      const store = state.stores.find((item) => item.id === storeId)
        || await request(`/api/market/stores/${encodeURIComponent(storeId)}`);
      closeSheet();
      await showView("map");
      if (store?.lat && store?.lng) state.map.setView([store.lat, store.lng], 17);
    } catch (error) {
      toast(error.message, true);
    }
  }

  function bindEvents() {
    qsa(".bottom-nav [data-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
    qs("#open-compose").addEventListener("click", ensureCompose);
    qs("#header-locate").addEventListener("click", () => { showView("map").then(() => locate()); });
    qs("#map-locate").addEventListener("click", () => locate());
    qs("#picker-locate").addEventListener("click", () => locate(state.pickerMap));
    qs("#confirm-location").addEventListener("click", confirmLocation);
    qs(".picker-close").addEventListener("click", closeLocationPicker);
    qsa(".modal-close").forEach((button) => button.addEventListener("click", closeCompose));
    qs(".sheet-close").addEventListener("click", closeSheet);
    qs("#media-viewer-close").addEventListener("click", closeMediaViewer);
    elements.mediaViewerTools.addEventListener("click", (event) => {
      const action = event.target.closest("[data-viewer-zoom]")?.dataset.viewerZoom;
      if (action === "in") setViewerZoom(viewer.scale + 0.5);
      if (action === "out") setViewerZoom(viewer.scale - 0.5);
      if (action === "reset") setViewerZoom(1);
    });
    elements.mediaViewerStage.addEventListener("dblclick", () => setViewerZoom(viewer.scale > 1 ? 1 : 2));
    elements.mediaViewerStage.addEventListener("pointerdown", (event) => {
      if (viewer.scale <= 1 || !qs("img", elements.mediaViewerContent)) return;
      viewer.dragging = true; viewer.startX = event.clientX - viewer.x; viewer.startY = event.clientY - viewer.y;
      event.currentTarget.setPointerCapture(event.pointerId);
      qs("img", elements.mediaViewerContent)?.classList.add("dragging");
    });
    elements.mediaViewerStage.addEventListener("pointermove", (event) => {
      if (!viewer.dragging) return;
      viewer.x = event.clientX - viewer.startX; viewer.y = event.clientY - viewer.startY;
      applyViewerTransform();
    });
    const stopViewerDrag = () => { viewer.dragging = false; qs("img", elements.mediaViewerContent)?.classList.remove("dragging"); };
    elements.mediaViewerStage.addEventListener("pointerup", stopViewerDrag);
    elements.mediaViewerStage.addEventListener("pointercancel", stopViewerDrag);
    elements.sheetBackdrop.addEventListener("click", closeSheet);
    elements.loadMore.addEventListener("click", () => loadProducts({ append: true }));
    elements.storeForm.addEventListener("submit", submitStore);
    elements.productForm.addEventListener("submit", submitProduct);
    qsa('input[type="file"]').forEach((input) => input.addEventListener("change", () => setFormMediaPreview(input.form)));
    qsa("[data-location-form]").forEach((button) => button.addEventListener("click", () => openLocationPicker(button.form)));

    elements.categoryRail.addEventListener("click", (event) => {
      const button = event.target.closest("[data-category]");
      if (!button) return;
      state.category = button.dataset.category;
      qsa("[data-category]", elements.categoryRail).forEach((item) => item.classList.toggle("active", item === button));
      loadProducts();
    });
    elements.mapFilter.addEventListener("change", (event) => {
      state.mapCategory = event.target.value;
      loadMapStores();
    });

    let searchTimer;
    elements.searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      state.query = elements.searchInput.value.trim();
      elements.clearSearch.style.visibility = state.query ? "visible" : "hidden";
      searchTimer = setTimeout(() => state.view === "stores" ? loadStores() : loadProducts(), 280);
    });
    elements.clearSearch.addEventListener("click", () => {
      elements.searchInput.value = "";
      state.query = "";
      elements.clearSearch.style.visibility = "hidden";
      state.view === "stores" ? loadStores() : loadProducts();
    });

    document.addEventListener("click", (event) => {
      const expandedMedia = event.target.closest("[data-expand-media]");
      if (expandedMedia) { openMediaViewer(expandedMedia.dataset.expandMedia, expandedMedia.dataset.mediaTitle, "image"); return; }
      const product = event.target.closest("[data-product-id]");
      if (product) { openProduct(product.dataset.productId); return; }
      const store = event.target.closest("[data-store-id]");
      if (store) { openStore(store.dataset.storeId); return; }
      if (event.target.closest("[data-open-store-form]")) openCompose("store");
      if (event.target.closest("[data-edit-store]")) openCompose("store", state.profile?.store);
      if (event.target.closest("[data-add-product]")) openCompose("product");
      const editProduct = event.target.closest("[data-edit-product]");
      if (editProduct) openCompose("product", state.profile?.products.find((item) => item.id === editProduct.dataset.editProduct));
      const removeProduct = event.target.closest("[data-delete-product]");
      if (removeProduct) deleteProduct(removeProduct.dataset.deleteProduct);
      const showMap = event.target.closest("[data-show-store-map]");
      if (showMap) showStoreOnMap(showMap.dataset.showStoreMap);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !elements.mediaViewer.hidden) closeMediaViewer();
      const expandedMedia = event.target.closest?.("[data-expand-media]");
      if (expandedMedia && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        openMediaViewer(expandedMedia.dataset.expandMedia, expandedMedia.dataset.mediaTitle, "image");
      }
    });
  }

  async function init() {
    tg?.ready();
    tg?.expand();
    tg?.setHeaderColor?.("#ffffff");
    tg?.setBackgroundColor?.("#f6f7f8");
    refreshIcons();
    if (!tg?.initData && !devTelegramId) {
      elements.accessGate.classList.add("denied");
      elements.accessGateTitle.textContent = "Kirish cheklangan";
      elements.accessGateText.textContent = "Marketpleysni Telegram botdagi menu yoki inline tugma orqali oching.";
      return;
    }
    elements.accessGate.hidden = true;
    elements.appShell.hidden = false;
    bindEvents();
    elements.clearSearch.style.visibility = "hidden";
    const startup = await Promise.allSettled([loadProfile(), loadCategories(), loadProducts()]);
    const categoriesError = startup[1].status === "rejected" ? startup[1].reason : null;
    if (categoriesError) toast(categoriesError.message || "Kategoriyalar yuklanmadi", true);
  }

  init();
})();
