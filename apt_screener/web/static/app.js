/* global L */

const BREAKDOWN_LABELS = {
  walk_to_subway: "지하철 도보",
  gangnam_commute: "강남 통근",
  hynix_shuttle_commute: "하이닉스 셔틀",
  price_value: "가격 상대가치",
  complex_quality: "단지 품질",
};

const state = {
  payload: null,
  selectedId: null,
  markers: {},
  map: null,
  layers: {
    apts: null,
    shuttles: null,
    anchors: null,
  },
};

function $(id) {
  return document.getElementById(id);
}

function formatPrice(manwon) {
  if (manwon == null) return "-";
  const eok = Math.floor(manwon / 10000);
  const rest = manwon % 10000;
  if (rest === 0) return `${eok}억`;
  return `${eok}억 ${rest.toLocaleString("ko-KR")}`;
}

function initMap() {
  state.map = L.map("map", {
    zoomControl: true,
    scrollWheelZoom: true,
  }).setView([37.35, 127.12], 10);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(state.map);

  state.layers.apts = L.layerGroup().addTo(state.map);
  state.layers.shuttles = L.layerGroup().addTo(state.map);
  state.layers.anchors = L.layerGroup().addTo(state.map);
}

function iconHtml(kind, label) {
  return `<div class="marker-${kind}"><span>${label}</span></div>`;
}

function makeIcon(kind, label) {
  const size = kind === "shuttle" ? 18 : 28;
  return L.divIcon({
    className: "",
    html: iconHtml(kind, label),
    iconSize: [size, size],
    iconAnchor: [size / 2, size],
    popupAnchor: [0, -size + 4],
  });
}

function clearLayers() {
  Object.values(state.layers).forEach((layer) => layer.clearLayers());
  state.markers = {};
}

function renderMap(payload) {
  clearLayers();
  const bounds = [];

  (payload.shuttle_stops || []).forEach((s) => {
    const m = L.marker([s.lat, s.lon], { icon: makeIcon("shuttle", "S") })
      .bindPopup(`<strong>${s.stop_name}</strong><br/>${s.route_name}<br/>셔틀 ${s.ride_minutes_to_hynix}분`);
    state.layers.shuttles.addLayer(m);
    bounds.push([s.lat, s.lon]);
  });

  const anchors = payload.anchors || {};
  if (anchors.gangnam) {
    const g = anchors.gangnam;
    const m = L.marker([g.lat, g.lon], { icon: makeIcon("anchor", "강") })
      .bindPopup(`<strong>${g.name || "강남역"}</strong><br/>지하철 출근 기준점`);
    state.layers.anchors.addLayer(m);
    bounds.push([g.lat, g.lon]);
  }
  if (anchors.hynix) {
    const h = anchors.hynix;
    const m = L.marker([h.lat, h.lon], { icon: makeIcon("anchor", "하") })
      .bindPopup(`<strong>${h.name || "하이닉스 이천"}</strong><br/>셔틀 도착 기준점`);
    state.layers.anchors.addLayer(m);
    bounds.push([h.lat, h.lon]);
  }

  filteredResults().forEach((r, idx) => {
    const rank = r.rank || idx + 1;
    const m = L.marker([r.lat, r.lon], { icon: makeIcon("apt", String(rank)) })
      .bindPopup(`<strong>${r.complex_name}</strong><br/>점수 ${r.rank_score}`);
    m.on("click", () => selectComplex(r.complex_no));
    state.layers.apts.addLayer(m);
    state.markers[r.complex_no] = m;
    bounds.push([r.lat, r.lon]);
  });

  if (bounds.length) {
    state.map.fitBounds(bounds, { padding: [36, 36], maxZoom: 12 });
  }
}

function filteredResults() {
  if (!state.payload) return [];
  const gMax = Number($("gangnamMax").value);
  const hMax = Number($("hynixMax").value);
  return (state.payload.results || []).filter(
    (r) => r.gangnam_total_min <= gMax && r.hynix_total_min <= hMax
  );
}

function renderList() {
  const list = $("rankList");
  list.innerHTML = "";
  const rows = filteredResults();
  if (!rows.length) {
    list.innerHTML = `<li class="rank-meta" style="padding:0.8rem">필터 조건에 맞는 단지가 없습니다.</li>`;
    return;
  }
  rows.forEach((r, i) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rank-item" + (state.selectedId === r.complex_no ? " is-active" : "");
    btn.innerHTML = `
      <span class="rank-no">${i + 1}</span>
      <span>
        <div class="rank-name">${r.complex_name}</div>
        <div class="rank-meta">강남 ${r.gangnam_total_min}분 · 하이닉스 ${r.hynix_total_min}분 · ${formatPrice(r.min_price_manwon)}</div>
      </span>
      <span class="rank-score">${r.rank_score}</span>
    `;
    btn.addEventListener("click", () => selectComplex(r.complex_no));
    li.appendChild(btn);
    list.appendChild(li);
  });
}

function selectComplex(id) {
  state.selectedId = id;
  const item = (state.payload?.results || []).find((r) => r.complex_no === id);
  if (!item) return;
  renderList();
  renderDetail(item);
  const marker = state.markers[id];
  if (marker) {
    state.map.panTo(marker.getLatLng(), { animate: true });
    marker.openPopup();
  }
}

function renderDetail(r) {
  const el = $("detail");
  el.classList.remove("is-empty");
  const bars = Object.entries(r.score_breakdown || {})
    .map(([k, v]) => {
      const pct = Math.round(Number(v) * 100);
      return `
        <div class="bar-row">
          <span>${BREAKDOWN_LABELS[k] || k}</span>
          <div class="bar-track"><div class="bar-fill" data-width="${pct}"></div></div>
          <span>${pct}</span>
        </div>`;
    })
    .join("");

  const notes = (r.investment_notes || [])
    .map((n) => `<li>${n}</li>`)
    .join("");

  const articles = (r.articles || [])
    .slice(0, 4)
    .map(
      (a) =>
        `${a.price_text || formatPrice(a.price_manwon)} · ${a.exclusive_area_m2}㎡ · ${a.floor_info || "-"}`
    )
    .join("<br/>");

  el.innerHTML = `
    <h2 class="detail-title">${r.complex_name}</h2>
    <p class="detail-addr">${r.address || ""} · 점수 ${r.rank_score}</p>
    <div class="metrics">
      <div class="metric"><span>최저 호가</span><b>${formatPrice(r.min_price_manwon)}</b></div>
      <div class="metric"><span>지하철 도보</span><b>${r.subway_walk_min}<small>분</small></b></div>
      <div class="metric"><span>강남 총통근</span><b>${r.gangnam_total_min}<small>분</small></b></div>
      <div class="metric"><span>하이닉스 총통근</span><b>${r.hynix_total_min}<small>분</small></b></div>
      <div class="metric"><span>가까운 역</span><b style="font-size:0.95rem">${r.nearest_subway}</b></div>
      <div class="metric"><span>가까운 셔틀</span><b style="font-size:0.95rem">${r.nearest_shuttle}</b></div>
    </div>
    <div class="bars">${bars}</div>
    <ul class="notes">${notes}</ul>
    <div class="articles">${articles || "매물 상세 없음"}</div>
  `;

  requestAnimationFrame(() => {
    el.querySelectorAll(".bar-fill").forEach((node) => {
      node.style.width = `${node.dataset.width}%`;
    });
  });
}

async function loadData() {
  const demo = $("demoToggle").checked;
  const btn = $("refreshBtn");
  btn.disabled = true;
  $("statusLine").textContent = "분석 중…";
  try {
    const url = `/api/screen?demo=${demo}&offline=true&refresh=true`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.payload = await res.json();
    const n = state.payload.results?.length || 0;
    const mode = state.payload.mode === "demo" ? "데모" : "라이브";
    $("statusLine").textContent = `${mode} · ${n}개 단지 · 셔틀 ${(state.payload.shuttle_stops || []).length}개 정류장`;
    if (state.payload.errors?.length) {
      $("statusLine").textContent += ` · 경고 ${state.payload.errors.length}`;
    }
    renderMap(state.payload);
    renderList();
    if (!state.selectedId && state.payload.results?.[0]) {
      selectComplex(state.payload.results[0].complex_no);
    } else if (state.selectedId) {
      const still = state.payload.results.find((r) => r.complex_no === state.selectedId);
      if (still) selectComplex(still.complex_no);
      else if (state.payload.results?.[0]) selectComplex(state.payload.results[0].complex_no);
    }
  } catch (err) {
    console.error(err);
    $("statusLine").textContent = `불러오기 실패: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

function bindControls() {
  $("refreshBtn").addEventListener("click", loadData);
  $("demoToggle").addEventListener("change", loadData);
  ["gangnamMax", "hynixMax"].forEach((id) => {
    $(id).addEventListener("input", () => {
      $(`${id}Label`).textContent = $(id).value;
      renderMap(state.payload || { results: [], shuttle_stops: [], anchors: {} });
      renderList();
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  bindControls();
  loadData();
});
