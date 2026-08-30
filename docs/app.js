const DONE_KEY = "kuchenplan-done-2026";

const fmt = (n) => {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
  return Number(n).toLocaleString("de-AT", { maximumFractionDigits: 4 });
};

const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

function loadDone() {
  try {
    return new Set(JSON.parse(localStorage.getItem(DONE_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveDone(set) {
  localStorage.setItem(DONE_KEY, JSON.stringify([...set]));
}

let DATA = null;
let done = loadDone();

async function boot(data) {
  DATA = data;
  document.title = `Kuchenplan · ${DATA.camp.name} ${DATA.camp.year}`;
  const foot = document.getElementById("data-foot");
  if (foot) {
    const stamp = DATA.exported_at
      ? new Date(DATA.exported_at).toLocaleString("de-AT", {
          dateStyle: "short",
          timeStyle: "short",
        })
      : document.documentElement.dataset.version || "unbekannt";
    foot.textContent = `Datenstand ${stamp} · Jungscharlager 2026 · Quelle: Küchenplan-Workbook`;
  }
  renderCalc();
  renderMenu();
  fillFilters();
  renderRecipes();
  renderShopping();
  wireTabs();
  wireDrawer();
  document.getElementById("recipe-search").addEventListener("input", renderRecipes);
  document.getElementById("recipe-scale").addEventListener("change", renderRecipes);
  document.getElementById("shop-search").addEventListener("input", renderShopping);
  document.getElementById("shop-filter").addEventListener("change", renderShopping);
  document.getElementById("aisle-filter").addEventListener("change", renderShopping);
  document.getElementById("hide-done").addEventListener("change", renderShopping);
}

function wireTabs() {
  const tabs = [...document.querySelectorAll(".tab")];
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const id = tab.dataset.panel;
      tabs.forEach((t) => {
        const on = t === tab;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      document.querySelectorAll(".panel").forEach((p) => {
        const on = p.id === `panel-${id}`;
        p.classList.toggle("is-active", on);
        p.hidden = !on;
      });
    });
  });
}

function renderCalc() {
  const c = DATA.calculation;
  document.getElementById("calc-lead").textContent =
    `Gewichtete Essen-Äquivalente aus Leiter/Kinder × Faktoren, aufgerundet → Basis ${fmt(c.portion_equivalents)}. Veggie-Zeilen nur × ${fmt(c.veggie_headcount)}.`;

  const grid = document.getElementById("calc-grid");
  grid.innerHTML = `
    <div class="stat"><span class="label">Gewichtete Summe</span><span class="value">${fmt(c.weighted_raw)}</span><span class="hint">vor Aufrundung</span></div>
    <div class="stat"><span class="label">Portionen (M4)</span><span class="value">${fmt(c.portion_equivalents)}</span><span class="hint">ceil</span></div>
    <div class="stat"><span class="label">Veggie</span><span class="value">${fmt(c.veggie_headcount)}</span><span class="hint">Kopfzahl</span></div>
    <div class="stat"><span class="label">Mi–Sa</span><span class="value">47</span><span class="hint">42 + 5 Extra</span></div>
  `;

  const rows = DATA.attendance
    .map(
      (a) => `<tr>
      <td>${esc(a.label)}</td>
      <td>${esc(a.eater_type)}</td>
      <td class="num">${fmt(a.count)}</td>
      <td class="num">× ${fmt(a.factor)}</td>
      <td class="num">${fmt(a.weighted)}</td>
    </tr>`
    )
    .join("");

  document.getElementById("formula-box").innerHTML = `
    <p><strong>Formel:</strong> <code>${esc(c.formula)}</code></p>
    <p>${esc(c.rounding)}</p>
    <table class="people-table" style="margin-top:1rem">
      <thead><tr><th>Gruppe</th><th>Typ</th><th class="num">Anzahl</th><th class="num">Faktor</th><th class="num">Gewichtet</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function dayHeading(meals) {
  const m = meals[0];
  if (m.date_label) return `${m.day} · ${m.date_label}`;
  return m.day;
}

function renderMenu() {
  const byDay = new Map();
  for (const m of DATA.menu) {
    const key = m.day_index ?? m.day;
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(m);
  }
  const board = document.getElementById("menu-board");
  board.innerHTML = [...byDay.entries()]
    .map(([, meals]) => {
      const body = meals
        .map((m) => {
          const chips = m.recipes
            .map(
              (r) =>
                `<button type="button" class="recipe-chip" data-recipe="${esc(r)}">${esc(r)}</button>`
            )
            .join("") || `<span class="muted">—</span>`;
          const note = [m.notes, m.veggie_option && `Veggie: ${m.veggie_option}`, m.gluten_notes]
            .filter(Boolean)
            .map((t) => `<p class="meal-note">${esc(t)}</p>`)
            .join("");
          const scaleHint = m.headcount_note
            ? `${esc(m.headcount_note)} → Skala ${fmt(m.scale)}`
            : `Skala ${fmt(m.scale)}`;
          return `<div class="meal-row">
            <div class="meal-meta">${esc(m.meal)}<small>${scaleHint}</small></div>
            <div>${chips}${note}</div>
          </div>`;
        })
        .join("");
      return `<article class="day-block"><h3>${esc(dayHeading(meals))}</h3>${body}</article>`;
    })
    .join("");

  board.querySelectorAll("[data-recipe]").forEach((btn) => {
    btn.addEventListener("click", () => openRecipe(btn.dataset.recipe));
  });
}

function fillFilters() {
  const shop = document.getElementById("shop-filter");
  const aisle = document.getElementById("aisle-filter");
  for (const s of DATA.shops) {
    shop.insertAdjacentHTML("beforeend", `<option value="${esc(s)}">${esc(s)}</option>`);
  }
  for (const a of DATA.aisles) {
    aisle.insertAdjacentHTML("beforeend", `<option value="${esc(a)}">${esc(a)}</option>`);
  }
}

function renderRecipes() {
  const q = document.getElementById("recipe-search").value.trim().toLowerCase();
  const scale = Number(document.getElementById("recipe-scale").value) || 1;
  const list = document.getElementById("recipe-list");
  const items = DATA.recipes.filter(
    (r) => !q || r.name.toLowerCase().includes(q) || (r.meals || []).join(" ").toLowerCase().includes(q)
  );

  list.innerHTML = items
    .map((r) => {
      const lines = r.lines
        .map((ln) => {
          // Veggie lines always use veggie headcount unless user picks ×2 explicitly.
          const show =
            ln.audience === "veggie"
              ? ln.amount_per_person * (scale === 2 ? 2 : DATA.calculation.veggie_headcount)
              : ln.amount_per_person * scale;
          const badge =
            ln.audience === "veggie" ? ` <span class="badge veggie">veggie</span>` : "";
          return `<tr>
            <td>${esc(ln.ingredient)}${badge}</td>
            <td class="num">${fmt(show)}</td>
            <td>${esc(ln.unit)}</td>
            <td class="muted">${esc(ln.aisle)}</td>
          </tr>`;
        })
        .join("");
      const meals =
        r.meals?.length
          ? `<p class="muted">Am Plan: ${esc(r.meals.join(" · "))}</p>`
          : `<p class="muted">Nicht am Speiseplan (Rezept bleibt in der DB)</p>`;
      const src = r.source
        ? `<p class="muted">Quelle: ${
            String(r.source).startsWith("http")
              ? `<a href="${esc(r.source)}" target="_blank" rel="noopener">${esc(r.source)}</a>`
              : esc(r.source)
          }</p>`
        : "";
      return `<details class="recipe-card">
        <summary><span>${esc(r.name)}</span><span class="muted">${r.on_menu}×</span></summary>
        <div class="body">
          ${meals}${src}
          <table class="recipe-lines">
            <thead><tr><th>Zutat</th><th class="num">Menge</th><th>Einh.</th><th>Gang</th></tr></thead>
            <tbody>${lines}</tbody>
          </table>
        </div>
      </details>`;
    })
    .join("");
}

function openRecipe(name) {
  document.querySelector('.tab[data-panel="recipes"]').click();
  const search = document.getElementById("recipe-search");
  search.value = name;
  renderRecipes();
  const card = [...document.querySelectorAll(".recipe-card")].find((d) =>
    d.querySelector("summary span")?.textContent === name
  );
  if (card) {
    card.open = true;
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function renderShopping() {
  const q = document.getElementById("shop-search").value.trim().toLowerCase();
  const shopF = document.getElementById("shop-filter").value;
  const aisleF = document.getElementById("aisle-filter").value;
  const hideDone = document.getElementById("hide-done").checked;

  let items = DATA.shopping.filter((s) => {
    if (shopF && s.shop !== shopF) return false;
    if (aisleF && s.aisle !== aisleF) return false;
    if (hideDone && done.has(s.ingredient)) return false;
    if (!q) return true;
    const hay = `${s.ingredient} ${s.recipes.join(" ")} ${s.shop} ${s.aisle}`.toLowerCase();
    return hay.includes(q);
  });

  const byShop = new Map();
  for (const s of items) {
    if (!byShop.has(s.shop)) byShop.set(s.shop, new Map());
    const aisles = byShop.get(s.shop);
    if (!aisles.has(s.aisle)) aisles.set(s.aisle, []);
    aisles.get(s.aisle).push(s);
  }

  const root = document.getElementById("shop-list");
  if (!items.length) {
    root.innerHTML = `<p class="muted">Keine Treffer.</p>`;
    return;
  }

  root.innerHTML = [...byShop.entries()]
    .map(([shop, aisles]) => {
      const blocks = [...aisles.entries()]
        .map(([aisle, rows]) => {
          const tr = rows
            .map((s) => {
              const key = s.ingredient;
              const label =
                s.ingredient + (s.audience === "veggie" ? " (veggie)" : "");
              const isDone = done.has(key);
              return `<tr class="shop-row${isDone ? " is-done" : ""}" data-item="${esc(key)}">
                <td class="check-cell"><input type="checkbox" data-done="${esc(key)}" ${isDone ? "checked" : ""} aria-label="Erledigt" /></td>
                <td class="num"><strong>${fmt(s.quantity)}</strong></td>
                <td>${esc(s.unit)}</td>
                <td><button type="button" class="item-link" data-explain="${esc(key)}">${esc(label)}</button>
                  <div class="muted">${esc(s.recipes.join(", "))}</div>
                </td>
              </tr>`;
            })
            .join("");
          return `<h4>${esc(aisle)}</h4>
            <table class="shop-table">
              <thead><tr><th></th><th class="num">Menge</th><th>Einh.</th><th>Zutat / Rezepte</th></tr></thead>
              <tbody>${tr}</tbody>
            </table>`;
        })
        .join("");
      return `<section class="shop-group"><h3>${esc(shop)}</h3>${blocks}</section>`;
    })
    .join("");

  root.querySelectorAll("[data-done]").forEach((cb) => {
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
      const key = cb.dataset.done;
      if (cb.checked) done.add(key);
      else done.delete(key);
      saveDone(done);
      renderShopping();
    });
  });

  root.querySelectorAll("[data-explain]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openExplain(btn.dataset.explain);
    });
  });
}

function openExplain(name) {
  const item = DATA.shopping.find((s) => s.ingredient === name);
  if (!item) return;
  const title = document.getElementById("drawer-title");
  const body = document.getElementById("drawer-body");
  title.textContent = item.ingredient + (item.audience === "veggie" ? " (veggie)" : "");

  const rows = (item.breakdown || [])
    .map((b) => {
      const meals = (b.meals || []).map((m) => `<li>${esc(m)}</li>`).join("");
      return `<tr>
        <td><strong>${esc(b.recipe)}</strong>
          <ul class="muted" style="margin:0.25rem 0 0;padding-left:1.1rem">${meals}</ul>
        </td>
        <td class="num">${fmt(b.amount_per_person)} ${esc(b.unit)} × Σ${fmt(b.portion_servings)}</td>
        <td class="num"><strong>${fmt(b.qty_total)}</strong> ${esc(b.unit)}</td>
      </tr>`;
    })
    .join("");

  body.innerHTML = `
    <p class="qty-big">${fmt(item.quantity)} ${esc(item.unit)}</p>
    <p class="muted">Roh: ${fmt(item.quantity_raw)} ${esc(item.unit)} → auf Packung gerundet · ${esc(item.shop)} · ${esc(item.aisle)}</p>
    <table class="breakdown-table">
      <thead><tr><th>Rezept / Mahlzeiten</th><th class="num">pro Pers. × Skala</th><th class="num">Summe</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="3" class="muted">Keine Aufschlüsselung</td></tr>`}</tbody>
    </table>
  `;
  document.getElementById("drawer").hidden = false;
  document.body.style.overflow = "hidden";
}

function wireDrawer() {
  const drawer = document.getElementById("drawer");
  drawer.querySelectorAll("[data-close]").forEach((el) => {
    el.addEventListener("click", () => {
      drawer.hidden = true;
      document.body.style.overflow = "";
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !drawer.hidden) {
      drawer.hidden = true;
      document.body.style.overflow = "";
    }
  });
}

export { boot, esc };
