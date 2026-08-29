
/* ═══════════════════════════════════════════════════════
   ADVANCED VISUALIZATION PANELS
   Diverse chart set: radar · bubble/scatter · doughnut ·
   distribution · term-curve · FII/DII flow · confidence gauge ·
   sector heatmap (DOM).  Loaded after app.js, so api()/num/esc/
   cls/regChart/$/$$/chartRegistry/Chart are in global scope.
   ══════════════════════════════════════════════════════ */
(function () {
"use strict";
const LG = { labels: { color: "#7c8aa5", usePointStyle: true, boxWidth: 10 } };
const GRID = "rgba(35,43,64,.5)";
const TICK = "#5b6683";

function kpi(label, value, sub, c) {
  return `<div class="tile"><div class="t-label">${esc(label)}</div>`
     + `<div class="t-value ${c||""}">${value}</div>`
     + (sub ? `<div class="t-sub">${esc(sub)}</div>` : "") + `</div>`;
}
function statCell(label, value, sub, c) {
  return `<div class="statcell"><div class="sc-label">${esc(label)}</div>`
     + `<div class="sc-value ${c||""}">${value}</div>`
     + (sub ? `<div class="sc-sub">${esc(sub)}</div>` : "") + `</div>`;
}
function vcat(v) {
  const s = String(v || "").toUpperCase();
  if (s.startsWith("FAVOR")) return "positive";
  if (s.startsWith("ADVERS")) return "negative";
  return "neutral";
}
function heatColor(v, lo, hi) {
  if (v == null || Number.isNaN(v)) return "rgba(40,48,68,.35)";
  const t = Math.max(-1, Math.min(1, 2 * (v - lo) / ((hi - lo) || 1) - 1));
  const hue = t >= 0 ? 45 + 105 * t : 45 - 45 * (1 + t);
  return `hsl(${hue.toFixed(0)},${(30 + 60 * Math.abs(t)).toFixed(0)}%,${(30 + 38 * Math.abs(t)).toFixed(0)}%)`;
}
function gaugeSVG(pct, col) {
  pct = Math.max(0, Math.min(100, pct || 0));
  const cx = 100, cy = 100, r = 78, a = Math.PI - pct / 100 * Math.PI;
  const nx = cx + r * Math.cos(a), ny = cy - r * Math.sin(a);
  return `<svg viewBox="0 0 200 110" class="gauge" style="width:190px">
    <path d="M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${cx+r} ${cy}" fill="none" stroke="#232b40" stroke-width="14"/>
    <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="${col}" stroke-width="5"/>
    <circle cx="${cx}" cy="${cy}" r="6" fill="${col}"/></svg>
    <div class="big-label" style="color:${col}">${Math.round(pct)}%</div>
    <div class="sub-label">regime confidence</div>`;
}
// map a scalar into 0..100 for a radar axis
function norm(x, lo, hi) {
  return Math.max(0, Math.min(100, Math.round((x - lo) / ((hi - lo) || 1) * 100)));
}
function regimeAxes(ins) {
  const sv = ins.state_vector || {};
  const conf = Math.round((ins.confidence || 0) * 100);
  const fii = (sv.fii_score != null ? sv.fii_score : -0.5) * 100;
  const calm = sv.vix_pctile != null ? 100 - sv.vix_pctile : 50;
  return {
    labels: ["Trend", "Strength", "Fund-flow", "Calm", "Conviction"],
    values: [norm(sv.vs_ema200_pct, -6, 6), norm(sv.adx, 5, 45), norm(fii, -50, 50),
      Math.round(calm), conf].map(v => Math.max(0, Math.min(100, v)))
  };
}
function radarChart(el, key, values, color) {
  const cfg = {
    type: "radar",
    data: { labels: regimeAxes({ state_vector: {} }).labels,
      datasets: [{ label: "regime", data: values, borderColor: color,
        backgroundColor: color.replace("1)", ".18)").replace(")", ",.18)"), borderWidth: 2, pointRadius: 3 }] },
    options: { scales: { r: { min: 0, max: 100, grid: { color: GRID }, angleLines: { color: GRID },
        ticks: { color: TICK, backdropColor: "transparent", stepSize: 25 },
        pointLabels: { color: "#8a97ad", font: { size: 11 } } } }, plugins: { legend: { display: false } } }
  };
  return regChart(key, () => new Chart(el, cfg));
}

/* ── DECISION DASHBOARD ─────────────────────────────── */
window.decidePanel = async function () {
  const body = $("#decBody"), st = $("#decStatus");
  const hor = $("#decHorizon").value, side = Number($("#decSide").value);
  st.textContent = "assembling regime + opportunities…";
  body.innerHTML = '<p class="muted">computing…</p>';
  try {
    const [ins, u, ov] = await Promise.all([
      api(`/insights?horizon=${encodeURIComponent(hor)}&side=${side}&symbol=NIFTY`),
      api(`/universe?top_n=12`),
      api("/market/overview"),
    ]);
    const vc = vcat(ins.verdict), conf = Math.round((ins.confidence || 0) * 100);
    const col = conf >= 66 ? "var(--green)" : conf >= 34 ? "var(--amber)" : "var(--red)";
    const rows = u.rows || [];
    const gate = (r) => side === 0
       ? Math.abs(r.rs_vs_nifty_pct || 0) >= 5
        : side === 1 ? r.rs_vs_nifty_pct > 0
       : r.rs_vs_nifty_pct < 0;
    const gated = rows.filter(gate).slice(0, 6);
    const top = rows.slice().sort((a, b) => (b.rs_vs_nifty_pct || 0) - (a.rs_vs_nifty_pct || 0)).slice(0, 12);

    body.innerHTML =
      `<div class="insight ${vc}"><div class="insp-head">
        <div>
          <div class="insp-regime mono">${esc(ins.regime_label)} <span class="muted small">(${esc(ins.regime)})</span></div>
          <div class="insp-horizon">Horizon: <b>${esc(hor)}</b> · Bias: <b>${esc(ins.side_label || "Long/Short")}</b> · Phase: <b>${esc(ov.phase)}</b></div>
        </div>
        <div class="center-card">${gaugeSVG(conf, col)}<div class="sub-label" style="margin-top:2px">${esc(ins.regime_label)}</div></div>
      </div>
      <div class="insight-verdict ${vc}">${esc(ins.verdict)}
        <div class="muted small mt8" style="font-weight:400">Favours: ${esc(ins.favors || "—")} · Trap: ${esc(ins.trap || "—")}</div>
      </div></div>
      <div class="grid g4 mt">
        ${kpi("Regime", ins.regime_label, `${conf}% confidence`, vc === "positive" ? "pos" : vc === "negative" ? "neg" : "neu")}
        ${kpi("Gate pass", String(gated.length), "of " + rows.length + " scanned", gated.length ? "pos" : "muted")}
        ${kpi("Top RS", top[0] ? num(top[0].rs_vs_nifty_pct, 1) + "%" : "—", top[0] ? top[0].symbol : "—", "pos")}
        ${kpi("Flow", ov.regime.label, "FII vs DII regime", ov.regime.score > 0 ? "pos" : "neg")}
      </div>
      <div class="grid g2-1 mt">
        <div class="card"><h3>Action plan — gated by the regime</h3>
          ${gated.length
            ? `<table class="tbl"><tr><th>Setup</th><th>3m %</th><th>RS %</th><th>Gate</th></tr>`
              + gated.map(r => `<tr><td class="mono"><b>${esc(r.symbol)}</b> <span class="muted small">${esc(r.sector)}</span></td>
                    <td class="num ${cls(r.ret_3m_pct)}">${num(r.ret_3m_pct, 1)}</td>
                    <td class="num ${cls(r.rs_vs_nifty_pct)}">${num(r.rs_vs_nifty_pct, 1)}</td>
                    <td class="pos">✓ agree</td></tr>`).join("") + `</table>`
            : `<p class="neu">No setup currently ${vc === "positive" ? "aligns with this regime" : "passes the gate"}. ${esc(Array.isArray(ins.invalidation) ? ins.invalidation[0] : (ins.invalidation || "Wait."))}.</p>`}
        </div>
        <div class="card"><h3>State vector ${'<i class="fi" data-f="fii_dii_regime_score"></i>'}</h3><div id="decRadar"><canvas height="240"></canvas></div></div>
      </div>
      <div class="card mt"><h3>Full universe ${'<i class="fi" data-f="screener_composite"></i>'}</h3>
        <div class="tbl-wrap"><table class="tbl" id="decTable"></table></div></div>
      <div class="muted small mt">${(ins.data_notes || []).map(esc).join(" · ")}</div>`;

    const ra = regimeAxes(ins);
    await new Promise(r => setTimeout(r, 0));
    radarChart($("#decRadar canvas"), "decRadar", ra.values, "#38bdf8");

    $("#decTable").innerHTML =
        `  <tr><th>#</th><th>Symbol</th><th>Sector</th><th>Close</th><th>3m %</th><th>RS vs Nifty %</th></tr>`
       + top.map((r, i) => `<tr><td class="muted">${i + 1}</td><td class="mono"><b>${esc(r.symbol)}</b></td>
           <td class="small">${esc(r.sector)}</td><td class="num">${num(r.ltp)}</td>
           <td class="num ${cls(r.ret_3m_pct)}">${num(r.ret_3m_pct, 1)}</td>
           <td class="num ${cls(r.rs_vs_nifty_pct)}">${num(r.rs_vs_nifty_pct, 1)}</td></tr>`).join("");
    st.textContent = "done @ " + new Date().toLocaleTimeString("en-IN");
  } catch (e) { st.textContent = ""; body.innerHTML = `<p class="neg">decision unavailable: ${esc(e.message)}</p>`; }
};
$("#btnDecision")?.addEventListener("click", () => { window._decLoaded = false; window.decidePanel(); });
$("#decHorizon")?.addEventListener("change", () => { window._decLoaded = false; window.decidePanel(); });
$("#decSide")?.addEventListener("change", () => { window._decLoaded = false; window.decidePanel(); });

/* ── UNIVERSE & HEATMAP ─────────────────────────────── */
window.heatmapPanel = async function () {
  const st = $("#hmStatus"), grid = $("#heatGrid");
  st.textContent = "loading universe…"; grid.innerHTML = '<p class="muted">downloading…</p>';
  try {
    const d = await api("/universe");
    const rows = d.rows || [];
    const metric = $("#hmMetric").value;
    const min = Number($("#hmTop").value) || 0;
    const show = min > 0 ? rows.slice(0, min) : rows;
    const vals = show.map(r => r[metric]).filter(v => v != null && !Number.isNaN(v));
    const lo = Math.min.apply(null, vals.concat(0)), hi = Math.max.apply(null, vals.concat(0));
    const groups = {};
    show.forEach(r => { (groups[r.sector] = groups[r.sector] || []).push(r); });
    grid.innerHTML = Object.keys(groups).map(sec => {
      const cells = groups[sec].slice().sort((a, b) => (b[metric] || 0) - (a[metric] || 0));
      return `<div class="hm-group"><div class="hm-sec">${esc(sec)} <span class="muted">${cells.length}</span></div>`
        + `<div class="hm-cells">`
        + cells.map(r => { const v = r[metric];
          return `<div class="hm-cell" title="${esc(r.symbol)} · ${metric}=${v == null ? "—" : v}" style="background:${heatColor(v, lo, hi)}">`
            + `<div class="hm-sym">${esc(r.symbol)}</div><div class="hm-val">${v == null ? "—" : num(v, 1)}</div></div>`; }).join("")
        + `</div></div>`;
    }).join("");
    const byMetric = rows.slice().sort((a, b) => (b[metric] || 0) - (a[metric] || 0));
    const tbl = rs => rs.map(r => `<tr><td class="mono">${esc(r.symbol)}</td><td class="small">${esc(r.sector)}</td>`
      + `<td class="num ${cls(r[metric])}">${num(r[metric], 1)}</td></tr>`).join("");
    $("#heatTop").innerHTML = `<table class="tbl"><tr><th>Symbol</th><th>Sector</th><th>${esc(metric)}</th></tr>` + tbl(byMetric.slice(0, 8)) + `</table>`;
    $("#heatBottom").innerHTML = `<table class="tbl"><tr><th>Symbol</th><th>Sector</th><th>${esc(metric)}</th></tr>` + tbl(byMetric.slice(-8).reverse()) + `</table>`;
    const agg = {};
    show.forEach(r => { (agg[r.sector] = agg[r.sector] || []).push(r[metric] || 0); });
    const secMeans = Object.keys(agg).map(k => ({ sec: k, m: agg[k].reduce((a, b) => a + b, 0) / agg[k].length }))
      .sort((a, b) => b.m - a.m);
    await new Promise(r => setTimeout(r, 0));
    const cfg = {
      type: "bar",
      data: { labels: secMeans.map(s => s.sec),
        datasets: [{ label: metric, data: secMeans.map(s => +s.m.toFixed(2)),
          backgroundColor: secMeans.map(s => heatColor(s.m, lo, hi)), borderWidth: 0 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } },
        scales: { x: { grid: { color: GRID }, ticks: { color: TICK } },
          y: { grid: { display: false }, ticks: { color: "#8a97ad" } } } }
    };
    regChart("heatSector", () => new Chart($("#heatSectorChart"), cfg));
    $("#heatNote").textContent = `${show.length} instruments · ${Object.keys(groups).length} sectors · scale ${num(lo, 1)}%…${num(hi, 1)}% · ${d.note || ""}`;
    st.textContent = `${rows.length} instruments @ ${new Date(d.generated_at || Date.now()).toLocaleTimeString("en-IN")}`;
  } catch (e) { st.textContent = ""; grid.innerHTML = `<p class="neg">universe unavailable: ${esc(e.message)}</p>`; }
};
$("#btnHeatmap")?.addEventListener("click", () => { window._hmLoaded = false; window.heatmapPanel(); });
$("#hmMetric")?.addEventListener("change", () => { window._hmLoaded = false; window.heatmapPanel(); });
$("#hmTop")?.addEventListener("change", () => { window._hmLoaded = false; window.heatmapPanel(); });

/* ── DERIVATIVES DEEP-DIVE ──────────────────────────── */
window.derivativesPanel = async function () {
  const st = $("#dvStatus");
  const sym = ($("#dvSymbol").value || "RELIANCE.NS").trim().toUpperCase();
  st.textContent = "analyzing " + sym + "…";
  $("#dvKpis").innerHTML = "";
  try {
    const [an, ta, beta, chain] = await Promise.all([
      api(`/fno/analytics/${sym}`).catch(() => null),
      api(`/fno/futures/term-structure/${sym}`).catch(() => null),
      api(`/fno/alpha-beta/${sym}`).catch(() => null),
      api(`/options/chain?underlying=${encodeURIComponent(sym)}`).catch(() => null),
    ]);
    const structure = ta ? ta.structure : "—";
    const near = ta ? ta.near_term : null, far = ta ? ta.far_term : null, cur = beta ? beta.current : null;

    $("#dvKpis").innerHTML =
      kpi("Structure", structure, ta ? `spot ${num(ta.spot)}` : "off-season", structure === "CONTANGO" ? "pos" : structure === "BACKWARDATION" ? "neg" : "neu")
      + kpi("Near basis", near ? num(near.basis_pct, 2) + "%" : "—", near ? `annual ${num(near.annualized_basis, 1)}%` : "off-season", "neu")
      + kpi("Far basis", far ? num(far.basis_pct, 2) + "%" : "—", far ? `annual ${num(far.annualized_basis, 1)}%` : "off-season", "neu")
      + kpi("Alpha / Beta", cur ? `${num(cur.alpha, 1)} / ${num(cur.beta, 2)}` : "—", cur ? `R² ${num(cur.r_squared, 2)} · IR ${num(cur.information_ratio, 2)}` : "off-season", "neu");

    if (ta) {
      $("#dvTermWrap").innerHTML = "<canvas id='dvTermChart'></canvas>";
      const tCfg = {
        type: "line",
        data: { labels: ta.curve.map(c => String(c.expiry).slice(5)),
          datasets: [
            { label: "Futures", data: ta.curve.map(c => c.futures_price), borderColor: "#38bdf8", borderWidth: 2, pointRadius: 3, tension: .15 },
            { label: "Spot", data: ta.curve.map(() => ta.spot), borderColor: "rgba(167,139,250,.6)", borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0 },
            { label: "Basis %", data: ta.curve.map(c => c.basis_pct), borderColor: "#f59e0b", borderWidth: 1.5, pointRadius: 2, tension: .1, yAxisID: "y1" } ] },
        options: { scales: { x: { grid: { color: GRID }, ticks: { color: TICK } },
          y: { grid: { color: GRID }, ticks: { color: TICK }, position: "left" },
          y1: { grid: { display: false }, ticks: { color: "#b8860b" }, position: "right" } } }
      };
      await new Promise(r => setTimeout(r, 0));
      regChart("dvTerm", () => new Chart($("#dvTermChart"), tCfg));
    } else {
      $("#dvTermWrap").innerHTML = `<p class="muted small">off-season: term structure unavailable for ${esc(sym)}</p>`;
    }
    const roll = beta && beta.rolling ? beta.rolling : null;
    if (roll) {
      $("#dvRollWrap").innerHTML = "<canvas id='dvRollChart'></canvas>";
      const rCfg = {
        type: "line",
        data: { labels: roll.map((_, i) => "t-" + (roll.length - i)),
          datasets: [
            { label: "Rolling α", data: roll.map(r => r.alpha), borderColor: "#22c55e", borderWidth: 2, pointRadius: 2, tension: .2 },
            { label: "Rolling IR", data: roll.map(r => r.info_ratio), borderColor: "#a78bfa", borderWidth: 1.5, pointRadius: 2, tension: .2, yAxisID: "y1" } ] },
        options: { scales: { x: { grid: { color: GRID }, ticks: { color: TICK, maxTicksLimit: 8 } },
          y: { grid: { color: GRID }, ticks: { color: TICK } },
          y1: { grid: { display: false }, ticks: { color: "#b8860b" }, position: "right" } } }
      };
      await new Promise(r => setTimeout(r, 0));
      regChart("dvRoll", () => new Chart($("#dvRollChart"), rCfg));
    } else {
      $("#dvRollWrap").innerHTML = `<p class="muted small">off-season: rolling alpha unavailable</p>`;
    }
     $("#dvAlphaWrap").innerHTML = cur
        ? `<div class="dv-alpha">
             ${statCell("Alpha", num(cur.alpha, 1) + "%/yr", cur.alpha > 0 ? "pos" : "neg")}
             ${statCell("Beta", num(cur.beta, 2), "vs NIFTY50")}
             ${statCell("R²", num(cur.r_squared, 2), "fit quality")}
             ${statCell("Track err", num(cur.tracking_error, 1) + "%", "")}
             ${statCell("Info ratio", num(cur.information_ratio, 2), cur.information_ratio > 0 ? "pos" : "neg")}
             ${statCell("α t-stat", num(cur.alpha_t_stat, 2), Math.abs(cur.alpha_t_stat) > 2 ? "pos" : "neu")}
           </div>`
        : `<p class="muted small">off-season: alpha/beta unavailable</p>`;
    const rows = chain ? chain.chain : null;
    const spot = rows && rows.length ? rows[0].spot : (an ? an.spot : null);
    if (rows && rows.length) {
        const mid = rows.slice(0, 12);
        $("#dvChain").innerHTML = `<table class="tbl"><tr><th>PE strike</th><th>PE IV%</th><th>spot</th><th>CE IV%</th><th>CE strike</th></tr>`
          + mid.map(r => `<tr><td class="num neg">${num(r.strike)}</td>`
            + `<td class="num">${num(r.pe_iv, 1)}</td><td class="mono">${num(spot)}</td>`
            + `<td class="num">${num(r.ce_iv, 1)}</td><td class="num pos">${num(r.strike)}</td></tr>`).join("")
          + `</table>`;
      } else {
        $("#dvChain").innerHTML = `<p class="muted small">off-season: option chain unavailable (NSE). ${an ? "Futures basis & alpha/beta above use cached data." : ""}</p>`;
      }
    st.textContent = "done @ " + new Date().toLocaleTimeString("en-IN");
    toast(`${sym} derivatives ready`);
  } catch (e) { st.textContent = ""; toast("✗ " + e.message); }
};
$("#btnDeriv")?.addEventListener("click", () => { window._dvLoaded = false; window.derivativesPanel(); });

/* ── MARKET REGIME ──────────────────────────────────── */
window.regimePanel = async function () {
  const st = $("#rgStatus"), verdict = $("#rgVerdict"), check = $("#rgCheck");
  st.textContent = "mapping regime mosaic…";
  try {
    const [ov, fd, ins] = await Promise.all([
      api("/market/overview"),
      api("/market/fii-dii"),
      api("/insights?horizon=swing&side=0&symbol=NIFTY"),
    ]);
    const vc = vcat(ins.verdict);
    verdict.innerHTML = `<div class="insight ${vc}" style="margin-top:0">
      <div class="insp-head"><div>
        <div class="insp-regime mono">${esc(ins.regime_label)} <span class="muted small">(${esc(ins.regime)})</span></div>
        <div class="insp-horizon">flow regime: <b>${esc(ov.regime.label)}</b> · phase <b>${esc(ov.phase)}</b></div>
      </div></div><div class="insight-verdict ${vc}">${esc(ins.verdict)}</div></div>`;

    const ra = regimeAxes(ins);
    await new Promise(r => setTimeout(r, 0));
    radarChart($("#rgRadar canvas"), "rgRadar", ra.values, "#a78bfa");

    const nets = {}, datesSet = new Set();
    (fd.table || []).forEach(r => {
      const d = String(r.date), c = r.category.indexOf("FII") >= 0 ? "FII" : "DII";
      nets[c] = nets[c] || {}; nets[c][d] = (nets[c][d] || 0) + r.net_cr; datesSet.add(d);
    });
    const dates = [...datesSet].sort().slice(-8);
    const fCfg = {
      type: "bar",
      data: { labels: dates.map(d => String(d).split("-")[2] || d),
        datasets: ["FII", "DII"].map((c, i) => ({ label: c, data: dates.map(d => (nets[c] && nets[c][d]) || 0),
          backgroundColor: i === 0 ? "rgba(56,189,248,.8)" : "rgba(167,139,250,.8)" })) },
      options: { scales: { x: { grid: { display: false }, ticks: { color: TICK } },
        y: { grid: { color: GRID }, ticks: { color: TICK } } }, plugins: { legend: LG } }
    };
    regChart("rgFlow", () => new Chart($("#rgFlowChart"), fCfg));

    const vwrap = $("#rgVolWrap");
    try {
      const vs = ($("#rgVolSym").value || "NIFTY50").trim().toUpperCase();
      const v = await api(`/volatility/${vs}`);
      const hist = v.history || v.series || [];
      vwrap.innerHTML = "<canvas id='rgVolChart'></canvas>";
      const vCfg = {
        type: "line",
        data: { labels: hist.map(p => Array.isArray(p) ? p[0] : p),
          datasets: [{ label: "realized vol", data: hist.map(p => Array.isArray(p) ? p[1] : (p.v != null ? p.v : p)),
            borderColor: "#22c55e", borderWidth: 1.5, pointRadius: 0, fill: true, backgroundColor: "rgba(34,197,94,.12)" }] },
        options: { scales: { x: { grid: { display: false }, ticks: { color: TICK, maxTicksLimit: 6 } },
          y: { grid: { color: GRID }, ticks: { color: TICK } } } }
      };
      await new Promise(r => setTimeout(r, 0));
      regChart("rgVol", () => new Chart($("#rgVolChart"), vCfg));
    } catch (_) {
      vwrap.innerHTML = `<p class="muted small">volatility series unavailable off-season — use the regime radar + flow instead.</p>`;
    }

    const items = ins.checklist || [];
    check.innerHTML = `<div class="insp-check">${items.map(q => `<label class="insp-gate"><input type="checkbox"/><span>${esc(q)}</span></label>`).join("")}</div>`;
    $$(".insp-gate input", check).forEach(cb => cb.addEventListener("change", () => cb.closest(".insp-gate").classList.toggle("done", cb.checked)));
    st.textContent = "mapped @ " + new Date().toLocaleTimeString("en-IN");
  } catch (e) { st.textContent = ""; verdict.innerHTML = `<p class="neg">regime unavailable: ${esc(e.message)}</p>`; }
};
$("#btnRegime")?.addEventListener("click", () => { window._rgLoaded = false; window.regimePanel(); });

/* ── OPPORTUNITY BOARD ──────────────────────────────── */
async function populateOppStrats() {
  const sel = $("#oppStrat");
  if (!sel || sel.options.length) return;
  try {
    const d = await api("/strategies");
    sel.innerHTML = (d.strategies || []).map(s =>
      `<option value="${esc(s.id)}">${esc(s.name)} — ${esc(s.holding)}</option>`).join("");
  } catch (_) { sel.innerHTML = "<option value='supertrend_rsi'>supertrend_rsi</option>"; }
}
window.opportunityPanel = async function () {
  await populateOppStrats();
  const st = $("#oppStatus"), strat = $("#oppStrat").value;
  const watch = ($("#oppWatch").value || "").split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
  st.textContent = `scanning ${watch.length} instruments on ${esc(strat)}…`;
  try {
    const results = await Promise.all(watch.map(async sym => {
      try {
        const s = await api("/signals", { method: "POST", body: JSON.stringify({ symbol: sym, strategy: strat }) });
        const dist = s.entry != null ? (s.entry / (s.rationale && s.rationale.ltp ? s.rationale.ltp : s.entry) - 1) * 100 : null;
        return {
          sym, strat, dir: s.direction, conf: s.confidence || 0, rr: s.rr,
          entry: s.entry, stop: s.stop, t1: s.target1, dist,
          regime: s.regime ? s.regime.label : "—",
          verdict: s.insight ? insightVerdict(s.insight) : "—",
        };
      } catch (e) { return { sym, strat, dir: 0, conf: 0, dist: null, regime: "—", verdict: "—", err: e.message }; }
    }));
    const good = results.filter(r => !r.err);
    const dm = { positive: 0, negative: 0, neutral: 0, error: 0 };
    results.forEach(r => { if (r.err) dm.error++; else dm[vcat(r.verdict)]++; });
    const bestRR = good.some(r => r.rr) ? Math.max.apply(null, good.filter(r => r.rr).map(r => r.rr)) : null;
    $("#oppKpis").innerHTML =
      kpi("Scanned", String(results.length), `${good.length} actionable`, good.length ? "pos" : "neu")
      + kpi("FAVORABLE", String(dm.positive), "agree with regime", "pos")
      + kpi("ADVERSE", String(dm.negative), "trap / avoid", "neg")
      + kpi("Best R:R", bestRR != null ? "1:" + num(bestRR, 1) : "—", "risk / reward", "neu");

    $("#oppTable").innerHTML =
      `<tr><th>Symbol</th><th>Signal</th><th>Entry</th><th>Stop</th><th>T1</th><th>R:R</th><th>Dist→entry</th><th>Regime</th><th>Verdict</th></tr>`
      + results.map(r => `<tr><td class="mono"><b>${esc(r.sym)}</b></td>
          <td>${r.dir === 1 ? '<span class="pos">▲ BUY</span>' : r.dir === -1 ? '<span class="neg">▼ SELL</span>' : '<span class="neu">— flat</span>'}</td>
          <td class="num">${r.entry != null ? num(r.entry) : "—"}</td>
          <td class="num neg">${r.stop != null ? num(r.stop) : "—"}</td>
          <td class="num pos">${r.t1 != null ? num(r.t1) : "—"}</td>
          <td class="num">${r.rr ? "1:" + r.rr : "—"}</td>
          <td class="num ${r.dist != null ? cls(-r.dist) : ""}">${r.dist != null ? num(r.dist, 1) + "%" : "—"}</td>
          <td class="small">${esc(r.regime)}</td>
          <td class="small ${vcat(r.verdict) === "positive" ? "pos" : vcat(r.verdict) === "negative" ? "neg" : "neu"}">${esc(String(r.verdict).slice(0, 44))}</td></tr>`).join("");

    await new Promise(r => setTimeout(r, 0));
    const dCfg = {
      type: "doughnut",
      data: { labels: ["FAVORABLE", "ADVERSE", "NEUTRAL"].concat(dm.error ? ["ERROR"] : []),
        datasets: [{ data: [dm.positive, dm.negative, dm.neutral].concat(dm.error ? [dm.error] : []),
          backgroundColor: ["#22c55e", "#ef4444", "#f59e0b", "#5b6683"], borderColor: "#0f1420", borderWidth: 2 }] },
      options: { plugins: { legend: { position: "right", labels: LG.labels } } }
    };
    regChart("oppDist", () => new Chart($("#oppDistChart"), dCfg));
    const pts = good.filter(r => r.dist != null).map(r => ({ x: r.dist, y: r.conf, r: Math.max(3, (r.rr || 1) * 3), s: r.sym, d: r.dir }));
    const bCfg = {
      type: "bubble",
      data: { datasets: [
        { label: "BUY", data: pts.filter(p => p.d === 1).map(p => ({ x: p.x, y: p.y, r: p.r, s: p.s })), backgroundColor: "rgba(34,197,94,.55)", borderColor: "#22c55e" },
        { label: "SELL", data: pts.filter(p => p.d === -1).map(p => ({ x: p.x, y: p.y, r: p.r, s: p.s })), backgroundColor: "rgba(239,68,68,.55)", borderColor: "#ef4444" } ] },
      options: { plugins: { legend: LG, tooltip: { callbacks: { label: c => `${c.raw.s} · conf ${c.raw.y} · dist ${c.raw.x}% · ${c.dataset.label}` } } },
        scales: { x: { title: { display: true, text: "distance to entry %", color: "#8a97ad" }, grid: { color: GRID }, ticks: { color: TICK } },
          y: { title: { display: true, text: "confidence %", color: "#8a97ad" }, grid: { color: GRID }, ticks: { color: TICK } } } }
    };
    regChart("oppScat", () => new Chart($("#oppScatChart"), bCfg));
    st.textContent = `${results.length} instruments @ ${new Date().toLocaleTimeString("en-IN")}`;
  } catch (e) { st.textContent = ""; $("#oppKpis").innerHTML += kpi("Error", "—", esc(e.message), "neg"); }
};
function insightVerdict(ins) {
  if (!ins) return "—";
  return (ins.regime_label || "") + " · " + String(ins.verdict || "").slice(0, 60);
}
$("#btnOpp")?.addEventListener("click", () => { window._oppLoaded = false; window.opportunityPanel(); });
$("#oppStrat")?.addEventListener("change", () => { window._oppLoaded = false; window.opportunityPanel(); });


/* ── RISK MAP (correlation · drawdown · concentration) ── */
window.riskMapPanel = async function () {
   const st = $("#rmStatus"), grid = $("#rmCheat");
   const syms = ($("#rmSyms").value || "").split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
   const horizon = +($("#rmHor").value || 5);
   const alpha = (+($("#rmAlpha").value || 95)) / 100;
   st.textContent = `computing risk for ${syms.length} instruments…`;
   try {
     const q = `symbols=${encodeURIComponent(syms.join(","))}&horizon_days=${horizon}&alpha=${alpha}`;
     const d = await api(`/risk/corrmap?${q}`);
     const v = d.var, c = d.correlation, dd = d.drawdown, cc = d.concentration;

      $("#rmKpis").innerHTML =
       kpi("VaR", "₹" + num(v.var_amount, 0), `${Math.round(v.alpha*100)}% conf · ${v.horizon_days}d`, "neu")
        + kpi("CVaR", "₹" + num(v.cvar_amount, 0), "expected shortfall", "neg")
        + kpi("Avg correlation", num(c.avg_pair_corr, 2), `eff ${cc.eff_n} of ${d.n} bets`, "neu")
        + kpi("Max drawdown", num(dd.max_dd_pct, 1) + "%", "portfolio 2y", "neg");

      // correlation DOM heatmap (diverging: red=low, green=high)
      grid.innerHTML = c.labels.map((sym, i) =>
       `<div class="corr-row"><div class="corr-rowh">${esc(sym)}</div>`
        + c.labels.map((_, j) => {
          const val = c.matrix[i][j];
          const bg = i === j ? "rgba(120,140,170,.35)" : heatColor(val, -1, 1);
          return `<div class="corr-cell" title="${esc(sym)} · ${esc(c.labels[j])} = ${val}"
             style="background:${bg}">${val}</div>`;
        }).join("") + `</div>`).join("");

      // underwater drawdown chart (equal-weighted portfolio, ~120 sampled points)
      await new Promise(r => setTimeout(r, 0));
      regChart("rmUnderwater", () => new Chart($("#rmUnderwaterChart"), {
         type: "line",
         data: { labels: dd.ts, datasets: [{ label: "drawdown %", data: dd.dd_pct,
            borderColor: "#ef4444", backgroundColor: "rgba(239,68,68,.14)",
            borderWidth: 1.5, pointRadius: 0, fill: 0 }] },
         options: { scales: {
            x: { grid: { display: false }, ticks: { color: TICK, maxTicksLimit: 8 } },
            y: { grid: { color: GRID }, ticks: { color: TICK, callback: x => x + "%" },
              title: { display: true, text: "underwater %", color: "#8a97ad" } } },
            plugins: { legend: { display: false } } } }));

      // per-symbol max drawdown bars (worst first)
      await new Promise(r => setTimeout(r, 0));
      regChart("rmDdBars", () => new Chart($("#rmDdBars"), {
         type: "bar",
         data: { labels: dd.per_symbol.map(r => r.symbol),
            datasets: [{ label: "max DD %", data: dd.per_symbol.map(r => r.max_dd_pct),
              backgroundColor: "rgba(239,68,68,.65)", borderWidth: 0 }] },
         options: { indexAxis: "y",
            scales: { x: { grid: { color: GRID }, ticks: { color: TICK, callback: x => x + "%" } },
              y: { grid: { display: false }, ticks: { color: "#8a97ad" } } },
            plugins: { legend: { display: false } } } }));

      // VaR simulated-distribution histogram + VaR/CVaR marker bars
      const dist = v.distribution;
      if (dist && dist.buckets.length) {
       await new Promise(r => setTimeout(r, 0));
        const top = Math.max.apply(null, dist.counts) || 1;
       const varBar = dist.buckets.map(b => Math.abs((+b) - dist.var_line_pct) < 0.12 ? top : null);
       const cvarBar = dist.buckets.map(b => Math.abs((+b) - dist.cvar_line_pct) < 0.12 ? top : null);
        regChart("rmDist", () => new Chart($("#rmDistChart"), {
          type: "bar",
          data: { labels: dist.buckets.map(b => (+b).toFixed(1) + "%"),
            datasets: [
               { label: "simulated returns", data: dist.counts,
                backgroundColor: "rgba(56,189,248,.55)", borderWidth: 0 },
               { label: `VaR ${Math.round(v.alpha*100)}%`, data: varBar,
                backgroundColor: "#f59e0b", borderWidth: 0, barPercentage: 0.5 },
               { label: "CVaR", data: cvarBar, backgroundColor: "#ef4444",
                borderWidth: 0, barPercentage: 0.5 } ] },
            options: { scales: {
              x: { grid: { display: false }, ticks: { color: TICK, maxTicksLimit: 10 } },
              y: { grid: { color: GRID }, ticks: { color: TICK },
                title: { display: true, text: "frequency", color: "#8a97ad" } } },
              plugins: { legend: LG } } }));
      }

      // concentration stat cells
       $("#rmConc").innerHTML =
        statCell("HHI index", num(cc.hhi, 1),
          cc.hhi < 1500 ? "diversified" : cc.hhi < 2500 ? "moderate" : "concentrated", "neu")
        + statCell("Max single weight", num(cc.max_weight_pct, 1) + "%", "equal-weighted", "neu")
        + statCell("Effective # bets", cc.eff_n, `of ${d.n} nominal`,
          cc.eff_n < 1.5 * d.n ? "neg" : "pos")
        + statCell("Avg pairwise corr", num(cc.avg_pair_corr, 2), cc.advice,
          cc.avg_pair_corr > 0.75 ? "neg" : cc.avg_pair_corr > 0.5 ? "neu" : "pos");

      // high-correlation pairs table
      const pairs = c.high_corr_pairs || [];
       $("#rmPairs").innerHTML = pairs.length
        ? `<table class="tbl"><tr><th>A</th><th>B</th><th>corr</th></tr>`
          + pairs.map(p => `<tr><td class="mono">${esc(p.a)}</td><td class="mono">${esc(p.b)}</td>
             <td class="num neg">${num(p.corr, 2)}</td></tr>`).join("") + `</table>
          <p class="muted small mt8">${esc(c.advice)}</p>`
        : `<p class="muted small">No pair exceeds the correlation
          threshold — positions are distinct exposures.</p>`;

       $("#rmNote").textContent = `${d.n} instruments · ${v.horizon_days}d horizon · `
        + `${Math.round(v.alpha*100)}% conf · generated `
        + new Date(d.generated_at || Date.now()).toLocaleTimeString("en-IN");
      st.textContent = "risk map @ " + new Date().toLocaleTimeString("en-IN");
   } catch (e) {
      st.textContent = "";
      $("#rmKpis").innerHTML += kpi("Error", "—", esc(e.message), "neg");
   }
};
$("#btnRiskMap")?.addEventListener("click", () => { window._rmLoaded = false; window.riskMapPanel(); });
$("#rmSyms")?.addEventListener("change", () => { window._rmLoaded = false; window.riskMapPanel(); });
$("#rmHor")?.addEventListener("change", () => { window._rmLoaded = false; window.riskMapPanel(); });
$("#rmAlpha")?.addEventListener("change", () => { window._rmLoaded = false; window.riskMapPanel(); });
})();
