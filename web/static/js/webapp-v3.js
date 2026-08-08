(() => {
  'use strict';

  const tg = window.Telegram?.WebApp;
  const initData = tg?.initData || '';
  const devTgId = new URLSearchParams(location.search).get('dev_tg_id');
  const state = {
    categories: [],
    category: 'all',
    query: '',
    ads: [],
    skip: 0,
    hasMore: false,
    currentView: 'discover',
    display: 'list',
    places: [],
    me: null,
    map: null,
    markerCluster: null,
    mapRequest: null,
    mapTimer: null,
    pickerMap: null,
    pickerTarget: null,
    pickerCenter: null,
    userLocation: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function iconRefresh() {
    window.lucide?.createIcons({ attrs: { 'aria-hidden': 'true' } });
  }

  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
  }

  function safeUrl(value) {
    if (!value) return '';
    try {
      const url = new URL(value, location.origin);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch { return ''; }
  }

  function phoneUrl(value) {
    return `tel:${String(value || '').replace(/[^+\d]/g, '')}`;
  }

  function authUrl(path) {
    if (!devTgId) return path;
    const url = new URL(path, location.origin);
    url.searchParams.set('dev_tg_id', devTgId);
    return url.pathname + url.search;
  }

  async function request(path, options = {}, auth = false) {
    const headers = new Headers(options.headers || {});
    if (auth && initData) headers.set('X-Telegram-Init-Data', initData);
    const response = await fetch(auth ? authUrl(path) : path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
  }

  function toast(message, error = false) {
    const element = $('#toast');
    element.textContent = message;
    element.className = `toast show${error ? ' error' : ''}`;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { element.className = 'toast'; }, 2800);
    if (error) tg?.HapticFeedback?.notificationOccurred('error');
  }

  function emptyState(icon, text) {
    return `<div class="empty-state"><div><i data-lucide="${icon}"></i><p>${escapeHTML(text)}</p></div></div>`;
  }

  function mediaHTML(url, type = 'image', alt = '') {
    const source = safeUrl(url);
    if (!source) return `<div class="media-placeholder"><i data-lucide="image"></i></div>`;
    if (type === 'video') {
      return `<video src="${source}" preload="metadata" muted playsinline></video><span class="video-badge"><i data-lucide="play"></i></span>`;
    }
    return `<img src="${source}" alt="${escapeHTML(alt)}" loading="lazy">`;
  }

  function displayPrice(price) {
    if (!price) return 'Kelishiladi';
    if (price.formatted) return price.formatted;
    const value = Number(price.value ?? price);
    return Number.isFinite(value) ? value.toLocaleString('uz-UZ') : 'Kelishiladi';
  }

  function markerPrice(price) {
    if (!price) return 'Kelishiladi';
    const value = Number(price.value);
    if (!Number.isFinite(value)) return 'Kelishiladi';
    if (price.currency === 'USD') return `$${value >= 1000 ? `${(value / 1000).toFixed(value % 1000 ? 1 : 0)}k` : value.toFixed(0)}`;
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value % 1_000_000 ? 1 : 0)} mln`;
    if (value >= 1000) return `${Math.round(value / 1000)} ming`;
    return `${Math.round(value)} so'm`;
  }

  function adCard(ad) {
    return `<button class="ad-card" type="button" data-ad-id="${escapeHTML(ad.id)}">
      <div class="ad-media">${mediaHTML(ad.thumbnail, ad.media_type, ad.title)}</div>
      <div class="ad-body">
        <div class="ad-category" style="--cat-color:${escapeHTML(ad.category_color)}">${escapeHTML(ad.category_name)}</div>
        <h3>${escapeHTML(ad.title)}</h3>
        <div class="ad-price">${escapeHTML(displayPrice(ad.price))}</div>
        <div class="ad-address"><i data-lucide="map-pin"></i><span>${escapeHTML(ad.address || 'Manzil ko\'rsatilmagan')}</span></div>
      </div>
    </button>`;
  }

  function placeRow(place) {
    return `<button class="place-row" type="button" data-place-id="${escapeHTML(place.id)}">
      <div class="place-avatar">${mediaHTML(place.thumbnail, 'image', place.name)}</div>
      <div class="place-info">
        <h3>${escapeHTML(place.name)} ${place.is_verified ? '<span class="verified"><i data-lucide="badge-check"></i></span>' : ''}</h3>
        <p>${escapeHTML(place.category_name)}</p>
        <div class="place-meta"><i data-lucide="map-pin"></i><span>${escapeHTML(place.address || 'Manzil ko\'rsatilmagan')}</span></div>
      </div>
      <span class="row-chevron"><i data-lucide="chevron-right"></i></span>
    </button>`;
  }

  async function loadCategories() {
    state.categories = await request('/api/ads/meta/categories');
    const all = [{ id: 'all', name: 'Barchasi', color: '#172026' }, ...state.categories];
    $('#category-rail').innerHTML = all.map(category => `
      <button class="category-chip${category.id === state.category ? ' active' : ''}" type="button" data-category="${category.id}" style="--chip-color:${category.color}">
        <span class="chip-dot"></span>${escapeHTML(category.name)}
      </button>`).join('');
    $$('.category-select').forEach(select => {
      select.innerHTML = state.categories.map(category => `<option value="${category.id}">${escapeHTML(category.name)}</option>`).join('');
    });
    iconRefresh();
  }

  async function loadAds(reset = true) {
    const grid = $('#ad-grid');
    if (reset) {
      state.skip = 0;
      state.ads = [];
      grid.innerHTML = '<div class="ad-card skeleton" style="height:230px"></div><div class="ad-card skeleton" style="height:230px"></div>';
    }
    const params = new URLSearchParams({ category: state.category, skip: state.skip, limit: '20' });
    if (state.query) params.set('q', state.query);
    try {
      const data = await request(`/api/ads/list?${params}`);
      state.ads = reset ? data.ads : [...state.ads, ...data.ads];
      state.skip = state.ads.length;
      state.hasMore = data.has_more;
      grid.innerHTML = state.ads.length ? state.ads.map(adCard).join('') : emptyState('search-x', 'E\'lon topilmadi');
      $('#result-count').textContent = `${data.total} ta`;
      $('#load-more').hidden = !state.hasMore;
      iconRefresh();
    } catch (error) {
      grid.innerHTML = emptyState('circle-alert', error.message);
      iconRefresh();
    }
  }

  async function loadPlaces() {
    const list = $('#place-list');
    list.innerHTML = '<div class="place-row skeleton"></div><div class="place-row skeleton"></div>';
    try {
      const data = await request(`/api/ads/places?category=${encodeURIComponent(state.category)}`);
      state.places = data.places;
      list.innerHTML = state.places.length ? state.places.map(placeRow).join('') : emptyState('store', 'Hozircha joy profillari yo\'q');
      iconRefresh();
    } catch (error) {
      list.innerHTML = emptyState('circle-alert', error.message);
      iconRefresh();
    }
  }

  function showView(view) {
    state.currentView = view;
    $$('.view').forEach(element => element.classList.toggle('active', element.id === `${view}-view`));
    $$('.bottom-nav [data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
    $('#search-wrap').hidden = view !== 'discover';
    if (view === 'places' && !state.places.length) loadPlaces();
    if (view === 'profile') loadProfile();
    if (view === 'discover' && state.display === 'map') setTimeout(() => state.map?.invalidateSize(), 80);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    tg?.HapticFeedback?.selectionChanged();
  }

  function setDisplay(display) {
    state.display = display;
    $('#list-pane').hidden = display !== 'list';
    $('#map-pane').hidden = display !== 'map';
    $('#show-list').classList.toggle('active', display === 'list');
    $('#show-map').classList.toggle('active', display === 'map');
    if (display === 'map') {
      initMap();
      setTimeout(() => { state.map.invalidateSize(); loadMapItems(); }, 80);
    }
  }

  function initMap() {
    if (state.map) return;
    state.map = L.map('map', { zoomControl: false, minZoom: 5, maxZoom: 19 }).setView([41.3111, 69.2797], 12);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    }).addTo(state.map);
    L.control.zoom({ position: 'topleft' }).addTo(state.map);
    state.markerCluster = L.markerClusterGroup({
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      removeOutsideVisibleBounds: true,
      disableClusteringAtZoom: 17,
      maxClusterRadius: 46,
    });
    state.map.addLayer(state.markerCluster);
    state.map.on('moveend', () => {
      clearTimeout(state.mapTimer);
      state.mapTimer = setTimeout(loadMapItems, 280);
    });
  }

  function validCoordinates(item) {
    const lat = Number(item.lat);
    const lng = Number(item.lng);
    return Number.isFinite(lat) && Number.isFinite(lng) && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
  }

  function mapIcon(item) {
    const color = escapeHTML(item.category_color || '#172026');
    if (item.kind === 'place') {
      return L.divIcon({
        className: 'custom-map-icon',
        html: `<div class="place-marker" style="--marker-color:${color}"><span>${escapeHTML(item.category_icon || '•')}</span></div>`,
        iconSize: [42, 48], iconAnchor: [21, 45], popupAnchor: [0, -43],
      });
    }
    return L.divIcon({
      className: 'custom-map-icon',
      html: `<div class="price-marker" style="--marker-color:${color}">${escapeHTML(markerPrice(item.price))}</div>`,
      iconSize: [92, 40], iconAnchor: [46, 37], popupAnchor: [0, -36],
    });
  }

  async function loadMapItems() {
    if (!state.map || !state.markerCluster) return;
    state.mapRequest?.abort();
    state.mapRequest = new AbortController();
    const bounds = state.map.getBounds();
    const params = new URLSearchParams({
      category: state.category,
      north: bounds.getNorth().toFixed(6), south: bounds.getSouth().toFixed(6),
      east: bounds.getEast().toFixed(6), west: bounds.getWest().toFixed(6),
    });
    try {
      const response = await fetch(`/api/ads/map?${params}`, { signal: state.mapRequest.signal });
      if (!response.ok) throw new Error('Xarita ma\'lumotlari yuklanmadi');
      const data = await response.json();
      state.markerCluster.clearLayers();
      data.items.filter(validCoordinates).forEach(item => {
        const marker = L.marker([Number(item.lat), Number(item.lng)], { icon: mapIcon(item), keyboard: true, title: item.title });
        marker.on('click', () => showMapPreview(item));
        state.markerCluster.addLayer(marker);
      });
    } catch (error) {
      if (error.name !== 'AbortError') toast(error.message, true);
    }
  }

  function showMapPreview(item) {
    const preview = $('#map-preview');
    preview.hidden = false;
    preview.innerHTML = `<div class="map-preview-inner">
      <div class="map-preview-media">${mediaHTML(item.thumbnail, item.media_type, item.title)}</div>
      <div><h3>${escapeHTML(item.title)}</h3><p>${escapeHTML(item.address || item.category_name)}</p>${item.kind === 'ad' ? `<strong>${escapeHTML(displayPrice(item.price))}</strong>` : ''}</div>
      <button class="map-preview-open" type="button" aria-label="Batafsil"><i data-lucide="chevron-right"></i></button>
    </div>`;
    $('.map-preview-open', preview).onclick = () => item.kind === 'ad' ? openAd(item.id) : openPlace(item.id);
    iconRefresh();
  }

  function locate(map = state.map) {
    if (!navigator.geolocation) return toast('Joylashuv xizmati mavjud emas', true);
    navigator.geolocation.getCurrentPosition(position => {
      const latlng = [position.coords.latitude, position.coords.longitude];
      state.userLocation = latlng;
      map?.flyTo(latlng, 16, { duration: .7 });
      $('#location-label').textContent = 'Joylashuvingiz bo\'yicha';
    }, () => toast('Joylashuvga ruxsat berilmadi', true), { enableHighAccuracy: true, timeout: 10000 });
  }

  function openSheet(content) {
    $('#detail-content').innerHTML = content;
    $('#sheet-backdrop').hidden = false;
    $('#detail-sheet').classList.add('open');
    $('#detail-sheet').setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    iconRefresh();
  }

  function closeSheet() {
    $('#detail-sheet').classList.remove('open');
    $('#detail-sheet').setAttribute('aria-hidden', 'true');
    $('#sheet-backdrop').hidden = true;
    document.body.style.overflow = '';
  }

  async function openAd(id) {
    openSheet('<div class="empty-state"><div class="skeleton" style="width:44px;height:44px;border-radius:50%"></div></div>');
    try {
      const ad = await request(`/api/ads/${encodeURIComponent(id)}`);
      const media = ad.media?.length ? ad.media.map(item => item.type === 'video'
        ? `<video src="${safeUrl(item.url)}" controls playsinline preload="metadata"></video>`
        : `<img src="${safeUrl(item.url)}" alt="${escapeHTML(ad.title)}">`).join('')
        : `<div class="media-placeholder"><i data-lucide="image"></i></div>`;
      const actions = [
        ad.phone ? `<a class="primary-button" href="${phoneUrl(ad.phone)}"><i data-lucide="phone"></i>Qo'ng'iroq</a>` : '',
        ad.lat != null && ad.lng != null ? `<button class="secondary-button detail-map-button" type="button"><i data-lucide="map"></i>Xaritada</button>` : '',
      ].join('');
      openSheet(`<div class="detail-gallery">${media}</div><div class="detail-body">
        <span class="detail-kicker">${escapeHTML(ad.category_name)}</span>
        <h2 class="detail-title">${escapeHTML(ad.title)}</h2>
        <div class="detail-price">${escapeHTML(displayPrice(ad.price))}</div>
        <p class="detail-description">${escapeHTML(ad.description || '')}</p>
        <div class="detail-facts">
          ${ad.address ? `<div class="detail-fact"><i data-lucide="map-pin"></i>${escapeHTML(ad.address)}</div>` : ''}
          ${ad.seller?.name ? `<div class="detail-fact"><i data-lucide="user-round"></i>${escapeHTML(ad.seller.name)}</div>` : ''}
          <div class="detail-fact"><i data-lucide="eye"></i>${Number(ad.view_count || 0).toLocaleString('uz-UZ')} ko'rish</div>
        </div><div class="detail-actions">${actions}</div>
      </div>`);
      $('.detail-map-button')?.addEventListener('click', () => {
        closeSheet(); showView('discover'); setDisplay('map');
        setTimeout(() => state.map.flyTo([ad.lat, ad.lng], 17, { duration: .7 }), 120);
      });
    } catch (error) { openSheet(emptyState('circle-alert', error.message)); }
  }

  async function openPlace(id) {
    openSheet('<div class="empty-state"><div class="skeleton" style="width:44px;height:44px;border-radius:50%"></div></div>');
    try {
      const place = await request(`/api/ads/place/${encodeURIComponent(id)}`);
      const hero = safeUrl(place.cover || place.thumbnail);
      const products = (place.photos || []).map(item => `<div class="product-item">
        ${item.type === 'video' ? `<video src="${safeUrl(item.url)}" controls playsinline preload="metadata"></video>` : `<img src="${safeUrl(item.url)}" alt="${escapeHTML(item.caption || place.name)}" loading="lazy">`}
        <div class="product-caption">${escapeHTML(item.caption || '')}${item.price ? `<strong>${escapeHTML(displayPrice(item.price))}</strong>` : ''}</div>
      </div>`).join('');
      openSheet(`${hero ? `<div class="detail-gallery"><img src="${hero}" alt="${escapeHTML(place.name)}"></div>` : ''}<div class="detail-body">
        <span class="detail-kicker">${escapeHTML(place.category_name)}</span>
        <h2 class="detail-title">${escapeHTML(place.name)} ${place.is_verified ? '<span class="verified"><i data-lucide="badge-check"></i></span>' : ''}</h2>
        <p class="detail-description">${escapeHTML(place.description || '')}</p>
        <div class="detail-facts">
          ${place.address ? `<div class="detail-fact"><i data-lucide="map-pin"></i>${escapeHTML(place.address)}</div>` : ''}
          ${place.working_hours ? `<div class="detail-fact"><i data-lucide="clock-3"></i>${escapeHTML(place.working_hours)}</div>` : ''}
        </div>
        <div class="detail-actions">${place.phone ? `<a class="primary-button" href="${phoneUrl(place.phone)}"><i data-lucide="phone"></i>Qo'ng'iroq</a>` : ''}${place.telegram ? `<a class="secondary-button" href="https://t.me/${encodeURIComponent(place.telegram)}" target="_blank"><i data-lucide="send"></i>Telegram</a>` : ''}</div>
        ${products ? `<div class="product-grid">${products}</div>` : ''}
      </div>`);
    } catch (error) { openSheet(emptyState('circle-alert', error.message)); }
  }

  async function loadProfile() {
    const hero = $('#profile-hero');
    hero.innerHTML = '<div class="skeleton" style="height:110px"></div>';
    try {
      state.me = await request('/api/webapp/me', {}, true);
      const user = state.me.user;
      hero.innerHTML = `<div class="profile-main"><div class="profile-avatar">${escapeHTML((user.full_name || 'S')[0].toUpperCase())}</div><div><h1>${escapeHTML(user.full_name || 'Foydalanuvchi')}</h1><p>${escapeHTML(user.phone || user.username || '')}</p></div></div>
        <div class="profile-stats"><div class="profile-stat"><strong>${state.me.ads.length}</strong><span>E'lon</span></div><div class="profile-stat"><strong>${user.remaining_ads}</strong><span>Qolgan limit</span></div><div class="profile-stat"><strong>${user.referral_count}</strong><span>Taklif</span></div></div>`;
      $('#profile-actions').innerHTML = `${state.me.place ? `<button class="secondary-button" type="button" data-place-id="${state.me.place.id}"><i data-lucide="store"></i>${escapeHTML(state.me.place.name)}</button><button class="secondary-button" id="add-product" type="button"><i data-lucide="image-plus"></i>Mahsulot qo'shish</button>` : `<button class="secondary-button" id="create-place-profile" type="button"><i data-lucide="store"></i>Joy profili ochish</button>`}`;
      $('#my-ads').innerHTML = state.me.ads.length ? state.me.ads.map(ad => `<div class="my-ad"><div>${mediaHTML(ad.thumbnail, 'image', ad.title)}</div><div><h3>${escapeHTML(ad.title)}</h3><span class="status ${escapeHTML(ad.status)}">${statusLabel(ad.status)}</span></div><button class="delete-button" type="button" data-delete-ad="${ad.id}" aria-label="O'chirish"><i data-lucide="trash-2"></i></button></div>`).join('') : emptyState('file-text', 'Sizda hali e\'lon yo\'q');
      iconRefresh();
    } catch (error) {
      state.me = null;
      hero.innerHTML = emptyState('log-in', error.message);
      $('#profile-actions').innerHTML = '';
      $('#my-ads').innerHTML = '';
      iconRefresh();
    }
  }

  function statusLabel(status) {
    return ({ active: 'Faol', pending: 'Tekshiruvda', rejected: 'Rad etilgan', expired: 'Muddati tugagan' })[status] || status;
  }

  function openModal(modal) {
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeModal(modal) {
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  function showComposeForm(name) {
    $$('.compose-tabs button').forEach(button => button.classList.toggle('active', button.dataset.form === name));
    $$('.compose-form').forEach(form => form.classList.toggle('active', form.id === `${name}-form`));
  }

  function openCompose(form = 'ad') {
    if (form === 'product' && !state.me?.place) {
      toast('Avval joy profilini yarating', true);
      form = 'place';
    }
    showComposeForm(form);
    openModal($('#compose-modal'));
  }

  function previewFiles(input) {
    const preview = input.closest('form').querySelector('.media-preview');
    const files = [...input.files].slice(0, 5);
    if (input.files.length > 5) toast('Ko\'pi bilan 5 ta media tanlang', true);
    preview.innerHTML = files.map(file => {
      const url = URL.createObjectURL(file);
      return `<div class="media-preview-item">${file.type.startsWith('video/') ? `<video src="${url}" muted></video>` : `<img src="${url}" alt="">`}</div>`;
    }).join('');
  }

  function openPicker(formName) {
    state.pickerTarget = formName;
    openModal($('#map-picker'));
    if (!state.pickerMap) {
      state.pickerMap = L.map('picker-map', { zoomControl: true, maxZoom: 19 }).setView(state.userLocation || [41.3111, 69.2797], state.userLocation ? 16 : 12);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', { maxZoom: 20, attribution: '&copy; OpenStreetMap &copy; CARTO' }).addTo(state.pickerMap);
      state.pickerMap.on('move', updatePickerCenter);
      state.pickerMap.on('moveend', updatePickerCenter);
    }
    const form = $(`#${formName}-form`);
    const lat = Number(form.elements.lat.value);
    const lng = Number(form.elements.lng.value);
    if (Number.isFinite(lat) && Number.isFinite(lng) && form.elements.lat.value) state.pickerMap.setView([lat, lng], 16);
    setTimeout(() => { state.pickerMap.invalidateSize(); updatePickerCenter(); }, 100);
  }

  function updatePickerCenter() {
    if (!state.pickerMap) return;
    const center = state.pickerMap.getCenter();
    state.pickerCenter = { lat: center.lat, lng: center.lng };
    $('#coordinate-bar').textContent = `${center.lat.toFixed(6)}, ${center.lng.toFixed(6)}`;
  }

  function confirmPicker() {
    if (!state.pickerTarget || !state.pickerCenter) return;
    const form = $(`#${state.pickerTarget}-form`);
    form.elements.lat.value = state.pickerCenter.lat.toFixed(7);
    form.elements.lng.value = state.pickerCenter.lng.toFixed(7);
    const button = $(`[data-location-form="${state.pickerTarget}"]`);
    button.classList.add('selected');
    $('span', button).textContent = `${state.pickerCenter.lat.toFixed(5)}, ${state.pickerCenter.lng.toFixed(5)}`;
    closeModal($('#map-picker'));
    openModal($('#compose-modal'));
    tg?.HapticFeedback?.notificationOccurred('success');
  }

  async function submitForm(form, endpoint) {
    const button = $('.submit-button', form);
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Yuborilmoqda...';
    try {
      const data = await request(endpoint, { method: 'POST', body: new FormData(form) }, true);
      toast(data.message || 'Saqlandi');
      form.reset();
      $('.media-preview', form).innerHTML = '';
      closeModal($('#compose-modal'));
      await Promise.all([loadAds(true), loadProfile()]);
      if (state.map) loadMapItems();
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; button.textContent = original; }
  }

  async function deleteAd(id) {
    if (!confirm('E\'lonni o\'chirasizmi?')) return;
    try {
      await request(`/api/webapp/ads/${encodeURIComponent(id)}`, { method: 'DELETE' }, true);
      toast('E\'lon o\'chirildi');
      await Promise.all([loadProfile(), loadAds(true)]);
      if (state.map) loadMapItems();
    } catch (error) { toast(error.message, true); }
  }

  function bindEvents() {
    $('#category-rail').addEventListener('click', event => {
      const button = event.target.closest('[data-category]');
      if (!button) return;
      state.category = button.dataset.category;
      $$('.category-chip').forEach(item => item.classList.toggle('active', item === button));
      loadAds(true);
      if (state.map) loadMapItems();
      if (state.currentView === 'places') loadPlaces();
    });
    $('#ad-grid').addEventListener('click', event => { const card = event.target.closest('[data-ad-id]'); if (card) openAd(card.dataset.adId); });
    $('#place-list').addEventListener('click', event => { const row = event.target.closest('[data-place-id]'); if (row) openPlace(row.dataset.placeId); });
    $('#profile-actions').addEventListener('click', event => {
      const place = event.target.closest('[data-place-id]');
      if (place) openPlace(place.dataset.placeId);
      if (event.target.closest('#add-product')) openCompose('product');
      if (event.target.closest('#create-place-profile')) openCompose('place');
    });
    $('#my-ads').addEventListener('click', event => { const button = event.target.closest('[data-delete-ad]'); if (button) deleteAd(button.dataset.deleteAd); });
    $$('.bottom-nav [data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
    $('#open-compose').addEventListener('click', () => openCompose('ad'));
    $('#show-list').addEventListener('click', () => setDisplay('list'));
    $('#show-map').addEventListener('click', () => setDisplay('map'));
    $('#load-more').addEventListener('click', () => loadAds(false));
    $('#locate-button').addEventListener('click', () => { showView('discover'); setDisplay('map'); locate(); });
    $('#map-locate').addEventListener('click', () => locate());
    $('#picker-locate').addEventListener('click', () => locate(state.pickerMap));
    $('#search-input').addEventListener('input', event => {
      $('#clear-search').classList.toggle('visible', Boolean(event.target.value));
      clearTimeout(bindEvents.searchTimer);
      bindEvents.searchTimer = setTimeout(() => { state.query = event.target.value.trim(); loadAds(true); }, 350);
    });
    $('#clear-search').addEventListener('click', () => { $('#search-input').value = ''; state.query = ''; $('#clear-search').classList.remove('visible'); loadAds(true); });
    $('#sheet-backdrop').addEventListener('click', closeSheet);
    $('.sheet-close').addEventListener('click', closeSheet);
    $$('.modal-close').forEach(button => button.addEventListener('click', () => closeModal(button.closest('.modal'))));
    $('.picker-close').addEventListener('click', () => { closeModal($('#map-picker')); openModal($('#compose-modal')); });
    $('#confirm-location').addEventListener('click', confirmPicker);
    $$('.compose-tabs button').forEach(button => button.addEventListener('click', () => {
      if (button.dataset.form === 'product' && !state.me?.place) return toast('Avval joy profilini yarating', true);
      showComposeForm(button.dataset.form);
    }));
    $$('.location-field').forEach(button => button.addEventListener('click', () => { closeModal($('#compose-modal')); openPicker(button.dataset.locationForm); }));
    $$('input[type="file"]').forEach(input => input.addEventListener('change', () => previewFiles(input)));
    $('#ad-form').addEventListener('submit', event => { event.preventDefault(); submitForm(event.currentTarget, '/api/webapp/ads'); });
    $('#place-form').addEventListener('submit', event => { event.preventDefault(); submitForm(event.currentTarget, '/api/webapp/places'); });
    $('#product-form').addEventListener('submit', event => { event.preventDefault(); submitForm(event.currentTarget, '/api/webapp/places/products'); });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') { closeSheet(); $$('.modal.open').forEach(closeModal); } });
  }

  async function boot() {
    tg?.ready();
    tg?.expand();
    tg?.disableVerticalSwipes?.();
    document.documentElement.style.setProperty('--tg-height', `${tg?.viewportStableHeight || innerHeight}px`);
    bindEvents();
    iconRefresh();
    try {
      await loadCategories();
      await loadAds(true);
    } catch (error) { toast(error.message, true); }
  }

  boot();
})();
