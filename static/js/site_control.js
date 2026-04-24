/* ═══════════════════════════════════════════════════════════════
   SITE CONTROL — bot reply parses <site-action> tags and mutates
   the fake AngryLynx landing page behind the widget.
   ═══════════════════════════════════════════════════════════════ */

const SITE_ACTION_RE = /<site-action>\s*(\{[\s\S]*?\})\s*<\/site-action>/g;

const SITE_THEMES = {
  dark:   { bg: "#0b0b12", fg: "#f5f5ff", accent: "#7c5cff", card: "#17172a" },
  light:  { bg: "#f6f6fb", fg: "#111",    accent: "#5a3dff", card: "#ffffff" },
  purple: { bg: "#1a0f2e", fg: "#ffeaff", accent: "#c46bff", card: "#2a1a4a" },
  green:  { bg: "#0d1a14", fg: "#e8fff2", accent: "#38d48b", card: "#15291f" },
  red:    { bg: "#1a0d0d", fg: "#ffeaea", accent: "#ff5a5a", card: "#2a1515" },
};

function $site(sel) {
  const root = document.getElementById("fakeSite");
  return root ? root.querySelector(sel) : null;
}

const SITE_ACTIONS = {
  setHeroTitle(v)    { const el = $site(".fake-hero h1");      if (el) el.textContent = String(v); },
  setHeroSubtitle(v) { const el = $site(".fake-hero p");       if (el) el.textContent = String(v); },
  setHeroButton(v)   { const el = $site(".fake-hero-btn");     if (el) el.textContent = String(v); },
  setNavBrand(v)     { const el = $site(".fake-nav-brand");    if (el) el.textContent = String(v); },
  setNavCta(v)       { const el = $site(".fake-nav-cta");      if (el) el.textContent = String(v); },
  setCtaTitle(v)     { const el = $site(".fake-cta h2");       if (el) el.textContent = String(v); },
  setCtaText(v)      { const el = $site(".fake-cta p");        if (el) el.textContent = String(v); },
  setFooter(v)       { const el = $site(".fake-footer p");     if (el) el.textContent = String(v); },

  setTheme(name) {
    const t = SITE_THEMES[String(name).toLowerCase()];
    if (!t) return;
    const root = document.getElementById("fakeSite");
    if (!root) return;
    root.style.setProperty("background", t.bg);
    root.style.setProperty("color", t.fg);
    root.style.setProperty("--site-accent", t.accent);
    root.style.setProperty("--site-card", t.card);
    root.querySelectorAll(".fake-hero-btn, .fake-nav-cta").forEach(b => {
      b.style.background = t.accent; b.style.color = "#fff";
    });
    root.querySelectorAll(".fake-feature").forEach(f => { f.style.background = t.card; });
  },

  hideSection(name) {
    const map = { features: ".fake-features", social: ".fake-social", cta: ".fake-cta", hero: ".fake-hero", footer: ".fake-footer", nav: ".fake-nav" };
    const el = $site(map[name]); if (el) el.style.display = "none";
  },
  showSection(name) {
    const map = { features: ".fake-features", social: ".fake-social", cta: ".fake-cta", hero: ".fake-hero", footer: ".fake-footer", nav: ".fake-nav" };
    const el = $site(map[name]); if (el) el.style.display = "";
  },

  clearFeatures() {
    const c = $site(".fake-features"); if (c) c.innerHTML = "";
  },
  removeLastFeature() {
    const c = $site(".fake-features"); if (!c) return;
    const last = c.querySelector(".fake-feature:last-child");
    if (last) last.remove();
  },
  removeFeatureAt(index) {
    const c = $site(".fake-features"); if (!c) return;
    const items = c.querySelectorAll(".fake-feature");
    const i = parseInt(index, 10) - 1; // 1-based
    if (items[i]) items[i].remove();
  },
  replaceFeatureAt(obj) {
    const c = $site(".fake-features"); if (!c || !obj) return;
    const items = c.querySelectorAll(".fake-feature");
    const i = parseInt(obj.index, 10) - 1; // 1-based
    const target = items[i]; if (!target) return;
    const { icon = "✨", title = "Feature", desc = "" } = obj;
    target.innerHTML = `<span class="fake-feature-icon">${icon}</span><h3></h3><p></p>`;
    target.querySelector("h3").textContent = title;
    target.querySelector("p").textContent = desc;
  },
  addFeature(obj) {
    const c = $site(".fake-features"); if (!c) return;
    const { icon = "✨", title = "Feature", desc = "" } = obj || {};
    const div = document.createElement("div");
    div.className = "fake-feature";
    div.innerHTML = `<span class="fake-feature-icon">${icon}</span><h3></h3><p></p>`;
    div.querySelector("h3").textContent = title;
    div.querySelector("p").textContent = desc;
    c.appendChild(div);
  },

  setLogos(list) {
    const c = $site(".fake-social-logos"); if (!c || !Array.isArray(list)) return;
    c.innerHTML = "";
    list.forEach(name => {
      const s = document.createElement("span");
      s.textContent = String(name);
      c.appendChild(s);
    });
  },

  resetSite() { location.reload(); },
};

function tryRunAction(jsonBlob) {
  try {
    const data = JSON.parse(jsonBlob);
    const fn = SITE_ACTIONS[data.action];
    if (typeof fn === "function") {
      fn(data.value !== undefined ? data.value : data);
      return true;
    }
  } catch (_) {}
  return false;
}

function applySiteActions(text) {
  if (!text || typeof text !== "string") return text;
  let cleaned = text.replace(SITE_ACTION_RE, function(_, jsonBlob) {
    tryRunAction(jsonBlob);
    return "";
  });
  // Fallback: bare JSON objects with an "action" field from whitelist
  const names = Object.keys(SITE_ACTIONS).join("|");
  const bareRe = new RegExp(
    '`{0,3}(?:json)?\\s*(\\{[^{}]*"action"\\s*:\\s*"(?:' + names + ')"[\\s\\S]*?\\})\\s*`{0,3}',
    "g"
  );
  cleaned = cleaned.replace(bareRe, function(_, jsonBlob) {
    return tryRunAction(jsonBlob) ? "" : _;
  });
  return cleaned.trim();
}
