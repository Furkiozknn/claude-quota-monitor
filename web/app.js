/* Claude Kota Panosu — arayuz mantigi. Bagimlilik yok. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// Kart etiketleri belgelenmemis bir uctan geliyor ve innerHTML'e basiliyor.
// Ucun bugun markup dondurmemesi yarin dondurmeyecegi anlamina gelmez.
const esc = (v) => String(v ?? "")
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

// Sunucudan gelen son durum. Geri sayimlar bunun uzerinden yerel olarak isler,
// yani her saniye sunucuya gitmeyiz.
let state = null;
let historyData = {};

const SERIES_COLORS = ["#c96442", "#3b82f6", "#2e9e5b", "#a855f7", "#d98324", "#0891b2"];

/* ---------------- tema ---------------- */

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch { /* gizli sekme */ }
  if (saved) document.documentElement.setAttribute("data-theme", saved);

  $("#theme-btn").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const isDark = cur
      ? cur === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch { /* yoksay */ }
    if (!$("#panel-history").hidden) drawChart();
  });
}

/* ---------------- sekmeler ---------------- */

function initTabs() {
  const tabs = $$(".tab");

  function select(tab, focus = false) {
    tabs.forEach((t) => {
      const on = t === tab;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", String(on));
      // Roving tabindex: sekme serisi tek Tab duragi olur, iceride ok tuslari gezer.
      t.tabIndex = on ? 0 : -1;
    });
    const name = tab.dataset.tab;
    $$(".panel").forEach((p) => { p.hidden = p.id !== `panel-${name}`; });
    if (name === "history") loadHistory();
    if (focus) tab.focus();
  }

  tabs.forEach((tab, i) => {
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", `panel-${tab.dataset.tab}`);
    tab.setAttribute("aria-selected", String(tab.classList.contains("active")));
    tab.tabIndex = tab.classList.contains("active") ? 0 : -1;

    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (e) => {
      const map = { ArrowRight: 1, ArrowLeft: -1, Home: "first", End: "last" };
      const move = map[e.key];
      if (move === undefined) return;
      e.preventDefault();
      let next;
      if (move === "first") next = tabs[0];
      else if (move === "last") next = tabs[tabs.length - 1];
      else next = tabs[(i + move + tabs.length) % tabs.length];
      select(next, true);
    });
  });
}

/* ---------------- bicimlendirme ---------------- */

function fmtCountdown(epochSec) {
  if (!epochSec) return null;
  let secs = Math.round(epochSec - Date.now() / 1000);
  if (secs <= 0) return "sıfırlanıyor…";
  const d = Math.floor(secs / 86400); secs -= d * 86400;
  const h = Math.floor(secs / 3600); secs -= h * 3600;
  const m = Math.floor(secs / 60);
  if (d > 0) return `${d}g ${h}s`;
  if (h > 0) return `${h}s ${m}dk`;
  return `${m}dk`;
}

function fmtClock(epochSec) {
  if (!epochSec) return "—";
  const d = new Date(epochSec * 1000);
  return d.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "medium" });
}

function fmtAgo(epochSec) {
  if (!epochSec) return "hiç";
  const secs = Math.round(Date.now() / 1000 - epochSec);
  if (secs < 60) return `${secs} sn önce`;
  if (secs < 3600) return `${Math.floor(secs / 60)} dk önce`;
  return `${Math.floor(secs / 3600)} sa önce`;
}

// Uc kendi severity'sini veriyor (normal / warning / critical).
// Ona guveniriz; yoksa yuzdeye gore tahmin ederiz.
function levelOf(card) {
  const sev = String(card.severity || "").toLowerCase();
  if (sev === "critical") return "danger";
  if (sev === "warning") return "warn";
  if (sev === "normal") return "ok";

  const pct = card.percent;
  if (pct == null) return "";
  if (pct >= 90) return "danger";
  if (pct >= 70) return "warn";
  return "ok";
}

function colorFor(card) {
  const css = getComputedStyle(document.documentElement);
  const level = levelOf(card);
  if (level === "danger") return css.getPropertyValue("--danger").trim();
  if (level === "warn") return css.getPropertyValue("--warn").trim();
  return css.getPropertyValue("--accent").trim();
}

/* ---------------- kartlar ---------------- */

function ringSvg(card) {
  const r = 32, c = 2 * Math.PI * r;
  const pct = card.percent;
  const filled = pct == null ? 0 : (Math.max(0, Math.min(100, pct)) / 100) * c;
  const track = getComputedStyle(document.documentElement).getPropertyValue("--track").trim();
  return `
    <svg width="76" height="76" viewBox="0 0 76 76">
      <circle cx="38" cy="38" r="${r}" fill="none" stroke="${track}" stroke-width="7"/>
      <circle cx="38" cy="38" r="${r}" fill="none" stroke="${colorFor(card)}" stroke-width="7"
              stroke-linecap="round" stroke-dasharray="${filled} ${c - filled}"/>
    </svg>`;
}

function renderCards() {
  const wrap = $("#cards");
  const cards = (state && state.cards) || [];

  $("#empty-hint").hidden = cards.length > 0;
  if (!cards.length) { wrap.innerHTML = ""; return; }

  wrap.innerHTML = cards.map((card) => {
    const pct = card.percent;
    const pctText = pct == null ? "—" : `${pct.toFixed(0)}%`;
    const cd = fmtCountdown(card.resets_at);
    const level = levelOf(card);

    // WCAG: durum yalnizca renkle anlatilmaz — simge + metin de var.
    const sevInfo = {
      ok:     { icon: "●", text: "normal" },
      warn:   { icon: "▲", text: "dikkat" },
      danger: { icon: "■", text: "kritik" },
    }[level] || { icon: "○", text: "bilinmiyor" };

    const sevTag =
      `<span class="tag tag-${level}"><span aria-hidden="true">${sevInfo.icon}</span> ${sevInfo.text}</span>`;

    // is_active = su an seni fiilen daraltan limit bu
    const activeTag = card.is_active
      ? `<span class="tag tag-active"><span aria-hidden="true">▶</span> şu an bu sınırlıyor</span>`
      : "";

    // Yanma hizi: asil soru "pencere sifirlanmadan once dolar miyim?"
    let burnLine = "";
    const burn = card.burn;
    if (burn && burn.percent_per_hour > 0) {
      const rate = `%${burn.percent_per_hour.toFixed(1)}/sa`;
      if (card.will_exhaust === true) {
        burnLine = `<div class="burn bad">${rate} · bu hızda <b>${fmtCountdown(burn.eta)}</b> sonra dolar</div>`;
      } else if (card.will_exhaust === false) {
        burnLine = `<div class="burn">${rate} · bu hızda pencere önce sıfırlanır</div>`;
      } else {
        burnLine = `<div class="burn">${rate}</div>`;
      }
    }

    const pctAria = pct == null ? "bilinmiyor" : pct.toFixed(0);
    const aria = `${esc(card.label)}: yüzde ${pctAria}, durum ${sevInfo.text}`;

    return `
      <div class="card ${card.is_active ? "is-active" : ""}" role="group" aria-label="${aria}">
        <div class="ring" aria-hidden="true">
          ${ringSvg(card)}
          <div class="val">${pctText}</div>
        </div>
        <div class="card-body">
          <div class="card-label" title="${esc(card.key)}">${esc(card.label)}</div>
          <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"
               aria-valuenow="${pct == null ? 0 : pct.toFixed(0)}"
               aria-label="${esc(card.label)} doluluk">
            <span class="bar-fill lvl-${level}" style="width:${Math.max(0, Math.min(100, pct || 0))}%"></span>
          </div>
          <div class="card-reset">
            ${cd ? `sıfırlanmasına <b class="cd">${cd}</b>` : "sıfırlanma bilgisi yok"}
          </div>
          ${burnLine}
          <div class="tags">${sevTag}${activeTag}</div>
        </div>
      </div>`;
  }).join("");

  renderMeta();
}

// Kota penceresi olmayan yan bilgiler: ek kullanim kredisi ve harcama
function renderMeta() {
  const meta = state && state.meta;
  const host = $("#meta");
  if (!host) return;
  if (!meta || (!meta.extra_usage && !meta.spend)) { host.hidden = true; return; }

  const bits = [];
  const eu = meta.extra_usage;
  if (eu) {
    bits.push(eu.enabled
      ? `Ek kullanım <b>açık</b>${eu.utilization != null ? ` · %${eu.utilization.toFixed(0)}` : ""}`
      : `Ek kullanım <b>kapalı</b>${eu.user_disabled ? " (senin tercihin)" : ""}`);
  }
  const sp = meta.spend;
  if (sp && sp.used != null) {
    bits.push(`Kredi harcaması <b>${sp.used.toFixed(2)} ${sp.currency || ""}</b>`);
  }

  host.hidden = bits.length === 0;
  host.innerHTML = bits.join(" &nbsp;·&nbsp; ");
}

// Geri sayimlari saniyede bir yerel olarak tazele (sunucuya gitmeden)
function tickCountdowns() {
  if (!state || !state.cards) return;
  $$("#cards .card").forEach((el, i) => {
    const card = state.cards[i];
    if (!card) return;
    const b = el.querySelector(".cd");
    if (b) b.textContent = fmtCountdown(card.resets_at) || "—";
  });
}

/* ---------------- uyari seridi ---------------- */

function renderNotice() {
  const el = $("#notice");
  const note = state && (state.note || state.error);
  if (!note) { el.hidden = true; return; }
  el.hidden = false;
  el.textContent = note;
  el.classList.toggle("bad", !!(state.error && !state.last_ok));
}

/* ---------------- ust bar + alt bar ---------------- */

function renderChrome() {
  const dot = $("#health-dot");
  dot.className = "dot";
  if (!state) return;

  if (state.last_ok && !state.error) dot.classList.add("ok");
  else if (state.last_ok) dot.classList.add("warn");
  else dot.classList.add("bad");

  $("#last-updated").textContent = state.last_ok
    ? `güncellendi ${fmtAgo(state.last_ok)}`
    : "henüz veri yok";

  const plan = state.subscription;
  const badge = $("#plan-badge");
  badge.hidden = !plan;
  if (plan) badge.textContent = plan;

  const next = state.next_try ? fmtCountdown(state.next_try) : null;
  const backoffNote = state.consecutive_errors > 0
    ? ` · ${state.consecutive_errors} hata sonrası bekleme modunda`
    : "";
  $("#foot-status").textContent =
    `sorgu aralığı ${state.poll_interval}sn` +
    (next ? ` · sonraki ~${next}` : "") +
    backoffNote +
    ` · token rotasyonu yapılmaz · v${state.version || "?"}`;
}

/* ---------------- tanilama ---------------- */

function renderDiag() {
  if (!state) return;
  const rows = [
    ["HTTP durumu", state.http_status ?? "—"],
    ["Son başarılı sorgu", state.last_ok ? fmtClock(state.last_ok) : "hiç"],
    ["Son deneme", state.last_try ? fmtClock(state.last_try) : "hiç"],
    ["Sonraki deneme", state.next_try ? fmtClock(state.next_try) : "—"],
    ["Üst üste hata", state.consecutive_errors ?? 0],
    ["Abonelik", state.subscription || "bilinmiyor"],
    ["Sorgu aralığı", `${state.poll_interval} sn`],
    ["Bulunan kota kartı", (state.cards || []).length],
    ["Not", state.note || "—"],
    ["Hata", state.error || "—"],
  ];
  $("#diag-table").innerHTML = rows
    .map(([k, v]) => `<tr><td>${k}</td><td>${String(v)}</td></tr>`)
    .join("");
}

/* ---------------- gecmis grafigi ---------------- */

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    historyData = await res.json();
    drawChart();
  } catch { /* sunucu kapanmis olabilir */ }
}

function drawChart() {
  const canvas = $("#chart");
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 800;
  const cssH = 320;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const css = getComputedStyle(document.documentElement);
  const border = css.getPropertyValue("--border").trim();
  const muted = css.getPropertyValue("--fg-muted").trim();

  const keys = Object.keys(historyData).filter((k) => historyData[k].length > 1);
  const pad = { l: 42, r: 14, t: 14, b: 26 };
  const w = cssW - pad.l - pad.r;
  const h = cssH - pad.t - pad.b;

  // izgara + y ekseni
  ctx.strokeStyle = border;
  ctx.fillStyle = muted;
  ctx.lineWidth = 1;
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let p = 0; p <= 100; p += 25) {
    const y = pad.t + h - (p / 100) * h;
    ctx.beginPath();
    ctx.moveTo(pad.l, y + 0.5);
    ctx.lineTo(pad.l + w, y + 0.5);
    ctx.stroke();
    ctx.fillText(`${p}%`, pad.l - 8, y);
  }

  if (!keys.length) {
    ctx.textAlign = "center";
    ctx.fillText("Henüz yeterli geçmiş yok — birkaç sorgu sonra dolar.",
                 pad.l + w / 2, pad.t + h / 2);
    $("#legend").innerHTML = "";
    return;
  }

  // ortak zaman ekseni
  let tMin = Infinity, tMax = -Infinity;
  keys.forEach((k) => historyData[k].forEach(([t]) => {
    if (t < tMin) tMin = t;
    if (t > tMax) tMax = t;
  }));
  const span = Math.max(tMax - tMin, 1);

  keys.forEach((key, i) => {
    const color = SERIES_COLORS[i % SERIES_COLORS.length];
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.beginPath();
    historyData[key].forEach(([t, pct], idx) => {
      const x = pad.l + ((t - tMin) / span) * w;
      const y = pad.t + h - (Math.max(0, Math.min(100, pct)) / 100) * h;
      idx === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  // zaman etiketleri
  ctx.fillStyle = muted;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  [0, 0.5, 1].forEach((f) => {
    const t = tMin + f * span;
    const label = new Date(t * 1000).toLocaleTimeString("tr-TR",
      { hour: "2-digit", minute: "2-digit" });
    ctx.fillText(label, pad.l + f * w, pad.t + h + 8);
  });

  $("#legend").innerHTML = keys.map((k, i) => {
    const label = (state?.cards || []).find((c) => c.key === k)?.label || k;
    return `<span><i style="background:${SERIES_COLORS[i % SERIES_COLORS.length]}"></i>${esc(label)}</span>`;
  }).join("");
}

/* ---------------- ham veri ---------------- */

function renderRaw() {
  const raw = state ? state.raw : null;
  $("#raw").textContent = raw
    ? JSON.stringify(raw, null, 2)
    : "Henüz cevap alınmadı.";
}

/* ---------------- dongu ---------------- */

async function refresh() {
  try {
    const res = await fetch("/api/status");
    state = await res.json();
  } catch {
    state = state || null;
    $("#health-dot").className = "dot bad";
    $("#foot-status").textContent = "sunucuya ulaşılamıyor — pencereyi kapatıp yeniden başlat";
    return;
  }
  renderChrome();
  renderNotice();
  renderCards();
  renderRaw();
  renderDiag();
  if (!$("#panel-history").hidden) loadHistory();
}

function init() {
  initTheme();
  initTabs();

  $("#refresh-btn").addEventListener("click", async () => {
    const btn = $("#refresh-btn");
    btn.disabled = true;
    btn.textContent = "…";
    try { await fetch("/api/refresh"); } catch { /* yoksay */ }
    setTimeout(async () => {
      await refresh();
      btn.disabled = false;
      btn.textContent = "Yenile";
    }, 1200);
  });

  $("#copy-raw").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#raw").textContent);
      $("#copy-raw").textContent = "Kopyalandı";
      setTimeout(() => { $("#copy-raw").textContent = "Kopyala"; }, 1500);
    } catch {
      $("#copy-raw").textContent = "Kopyalanamadı";
      setTimeout(() => { $("#copy-raw").textContent = "Kopyala"; }, 1500);
    }
  });

  addEventListener("resize", () => {
    if (!$("#panel-history").hidden) drawChart();
  });

  refresh();
  setInterval(refresh, 5000);   // yerel sunucu — Anthropic'e gitmez
  setInterval(tickCountdowns, 1000);
}

init();
