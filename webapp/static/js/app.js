/* ═════════════ QuantDesk India — frontend app ═════════════ */
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];
const api = async (path, opts={}) => {
  const r = await fetch(`/api${path}`, {
    headers: {"Content-Type": "application/json"}, ...opts});
  if (!r.ok) { let e; try{e=(await r.json()).detail}catch(_){e=r.statusText}
    throw new Error(typeof e==="string"?e:JSON.stringify(e)); }
  return r.json();
};
const fmtINR = v => "₹" + Number(v).toLocaleString("en-IN");
const num = (v,d=2) => v==null||Number.isNaN(v)? "—" : Number(v).toFixed(d);
const cls = v => v>0?"pos":v<0?"neg":"neu";
const esc = s => String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function toast(msg, ms=3200){
  const t=$("#toast"); t.textContent=msg; t.classList.remove("hidden");
  clearTimeout(t._h); t._h=setTimeout(()=>t.classList.add("hidden"),ms);
}

/* ─────────────────────────────────────────────
   ⓘ FORMULA EXPLAINABILITY SYSTEM
──────────────────────────────────────────────*/
document.addEventListener("click", e=>{
  const ic = e.target.closest(".fi");
  if(ic && ic.dataset.f){ e.stopPropagation(); openFormula(ic.dataset.f, $("#fmSymbol")?.value || currentSymbol()); }
});

async function openFormula(fid, symbol){
  const m=$("#formulaModal"); m.classList.remove("hidden");
  $("#fmTitle").textContent=fid;
  $("#fmExampleCtl").classList.toggle("hidden", !["rsi","macd","bollinger","atr","adx","supertrend",
    "volume_zscore","realized_vol_cc","ewma_vol","yang_zhang","parkinson","bs_price","delta","gamma",
    "theta","vega","implied_vol","estimate_gbm_params","gbm"].includes(fid));
  if(symbol) $("#fmSymbol").value=symbol;
  await loadFormula(fid, symbol);
  bindInfoIcons(m);
}

// Modal close handlers
function closeFormulaModal(){
  $("#formulaModal").classList.add("hidden");
}
$("#fmClose")?.onclick = closeFormulaModal;
$("#formulaModal")?.addEventListener("click", e=>{ if(e.target.id==="formulaModal") closeFormulaModal(); });
document.addEventListener("keydown", e=>{ if(e.key==="Escape") closeFormulaModal(); });

async function loadFormula(fid, symbol){
  const body=$("#fmBody"); body.innerHTML=`<p class="muted">loading ${esc(fid)}…</p>`;
  try{
    const d=await api(`/formula/${fid}?symbol=${encodeURIComponent(symbol||"RELIANCE")}&depth=1`);
    renderFormula(body,d,symbol); renderMathInEl(body);
  }catch(e){ body.innerHTML=`<p class="neg">failed: ${esc(e.message)}</p>`; }
}
function depHtml(children){
  if(!children?.length) return "";
  return `<div class="fm-cascade">${children.map(c=>`
    <div class="fm-dep" data-f="${esc(c.id)}"><b>ƒ ${esc(c.title)}</b>
      <small>${esc(c.text_formula)}</small></div>${depHtml(c.children)}`).join("")}</div>`;
}
function renderFormula(root,d,symbol){
  root.innerHTML=`
   <div class="fm-section">
     <span class="fm-tag">${esc(d.category)}</span>
     <h2 style="margin-top:8px">${esc(d.title)} <i class="fi hidden"></i></h2>
     <p class="muted small mt8">${esc(d.what)}</p>
     <div class="fm-latex">$${(Array.isArray(d.latex)?d.latex:[d.latex]).map(l=>l.replace(/\$/g,"")).join("$$")}$$</div>
     <p class="mono muted small mt8">code: ${esc(d.text_formula)}</p>
   </div>
   <div class="fm-section"><h3>Derivation steps</h3><ol class="fm-steps">${d.how.map(s=>`<li>${esc(s)}</li>`).join("")}</ol></div>
   <div class="grid g2">
     <div class="fm-section"><h3>Inputs</h3>
       <table class="tbl tiny">${Object.entries(d.inputs||{}).map(([k,v])=>`<tr><td class="mono cyan">${esc(k)}</td><td class="muted">${esc(v)}</td></tr>`).join("")}</table>
     </div>
     <div class="fm-section"><h3>Trading interpretation</h3><p class="small" style="line-height:1.7">${esc(d.interpretation||"—")}</p></div>
   </div>
   ${d.static_example&&Object.keys(d.static_example).length?`<div class="fm-section fm-example">
     <h3>Worked example (static)</h3>
     <table>${Object.entries(d.static_example).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table></div>`:""}
   ${d.live_example?`<div class="fm-section fm-example">
     <h3>🔴 LIVE worked example — ${esc(d.example_symbol||symbol||"")} right now</h3>
     <table>${d.live_example.rows.map(r=>`<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`).join("")}</table>
     <p class="muted small mt8">${esc(d.live_example.note||"")}</p></div>`
     :`<div class="fm-section muted small">live example unavailable for this one${symbol?` on ${esc(symbol)}`:""}.</div>`}
   ${d.depends_on?.length?`<div class="fm-section"><h3>Cascading dependencies (click to expand)</h3>
     <div>${d.depends_on.map(id=>`<div class="fm-dep" data-f="${esc(id)}"><b>ƒ ${esc(id)}</b></div>`).join("")}${depHtml(d.children?.map?[]:"")}</div></div>`:""}
   ${d.children?.length?`<div class="fm-section"><h3>Nested sub-formula docs</h3>${depHtml(d.children)}</div>`:""}`;
  $$(".fm-dep[data-f]",root).forEach(el=>el.onclick=e=>{e.stopPropagation();
    openFormula(el.dataset.f, $("#fmSymbol").value)});
}
function renderMathInEl(el){
  try{renderMathInElement(el,{delimiters:[{left:"$$",right:"$$",display:true},
    {left:"$",right:"$",display:false}],throwOnError:false});}catch(_){}
}

/* ─────────────────────────────────────────────
   NAV / GLOBALS
──────────────────────────────────────────────*/
let chartRegistry={};
function regChart(key,inst){ if(chartRegistry[key])chartRegistry[key].destroy(); chartRegistry[key]=inst; return inst;}
function currentSymbol(){return $("#chSymbol").value.trim().toUpperCase()||"RELIANCE"}

$$("#sideNav a").forEach(a=>a.onclick=()=>{
  $$("#sideNav a").forEach(x=>x.classList.remove("active")); a.classList.add("active");
  $$(".panel").forEach(p=>p.classList.remove("active"));
  $(`#panel-${a.dataset.panel}`).classList.add("active");
  if(a.dataset.panel==="charts"&&!window._chLoaded){loadChart();window._chLoaded=true;}
  if(a.dataset.panel==="options"&&!window._optLoaded){initOptions();window._optLoaded=true;}
  if(a.dataset.panel==="library")buildLibrary();
});
$("#btnGoSymbol").onclick=()=>{$("#chSymbol").value=$("#globalSymbol").value.trim().toUpperCase();
  $$("#sideNav a").find(a=>a.dataset.panel==="charts").click();};
$("#globalSymbol").addEventListener("keydown",e=>{if(e.key==="Enter")$("#btnGoSymbol").click()});
bindInfoIcons(document);
function bindInfoIcons(root){ /* icons are self-binding via delegation */ }

/* clock + health */
setInterval(()=>{ $("#clock").textContent=new Date().toLocaleTimeString("en-IN",{hour12:false}); },1000);
api("/health").then(h=>{ $("#marketPhase").textContent=h.phase;
  $("#modePill").textContent=h.kite_configured?`LIVE(${h.mode})`:"PAPER"; }).catch(()=>{});

/* ─────────────────────────────────────────────
   DASHBOARD
──────────────────────────────────────────────*/
async function loadDashboard(){
  try{
    const o=await api("/market/overview");
    $("#indexTiles").innerHTML=o.indices.map(i=>`
      <div class="tile"><div class="t-label">${esc(i.name)}</div>
        <div class="t-value mono">${num(i.ltp)}</div>
        <div class="t-sub ${cls(i.change_pct)}">${i.change_pct>0?"▲":"▼"} ${num(Math.abs(i.change_pct),2)}%</div>
      </div>`).join("");
    drawGauge(o.regime.score,o.regime.label);
    $("#regimeDetail").textContent=
      `FII net 5d: ₹${num(o.regime.detail.fii_net_5d_cr,0)}cr · DII: ${o.regime.detail.dii_net_5d_cr!=null?"₹"+num(o.regime.detail.dii_net_5d_cr,0)+"cr":"—"} | phase ${o.phase}`;
    const f=await api("/market/fii-dii");
    $("#flowTable").innerHTML=`<tr><th>Date</th><th>Category</th><th>Buy ₹cr</th><th>Sell ₹cr</th><th>Net ₹cr</th></tr>`+
      f.table.slice(-10).reverse().map(r=>`<tr><td>${esc(r.date)}</td><td>${r.category.includes("FII")?
        '<span class="pos">FII</span>':'<span style="color:var(--violet)">DII</span>'}</td>
        <td class="num">${num(r.buy_cr,0)}</td><td class="num">${num(r.sell_cr,0)}</td>
        <td class="num ${cls(r.net_cr)}">${num(r.net_cr,0)}</td></tr>`).join("");
    const cats={},nets={};
    f.table.forEach(r=>{(cats[r.category]=cats[r.category]||new Set()).add(String(r.date));
      nets[r.category]=nets[r.category]||{}; nets[r.category][String(r.date)]=r.net_cr;});
    const dates=[...new Set(f.table.map(r=>String(r.date)))].sort();
    regChart("flow",new Chart($("#flowChart"),{type:"bar",data:{labels:dates,
      datasets:Object.keys(nets).map((c,i)=>({label:c,data:dates.map(d=>nets[c][d]??0),
        backgroundColor:i===0?"rgba(56,189,248,.75)":"rgba(167,139,250,.75)"}))},
      options:{plugins:{legend:{labels:{color:"#7c8aa5"}}},scales:{x:{ticks:{color:"#7c8aa5"}},
        y:{ticks:{color:"#7c8aa5"}}}}}));
    const w=await api("/market/deals?type=whale_table&days=3");
    $("#dashWhaleTable").innerHTML=headRow(["Date","Sym","Client","Side","₹Cr"]) +
      w.rows.slice(0,9).map(r=>`<tr><td>${esc(r.date??"")}</td><td class="mono">${esc(r.symbol)}</td>
        <td class="small">${esc((r.client??"").slice(0,26))}</td>
        <td>${String(r.side??"").toUpperCase().startsWith("B")?'<span class="pos">BUY</span>':'<span class="neg">SELL</span>'}</td>
        <td class="num">${num(r.value_cr,1)}</td></tr>`).join("");
    const pp=await api("/paper/portfolio");
    $("#paperSnapshot").innerHTML=`cash ${fmtINR(pp.cash)} · mv ${fmtINR(pp.market_value)}
      · liq ${fmtINR(pp.net_liquidation)} · realized P&L <span class="${cls(pp.realized_pnl)}">${fmtINR(pp.realized_pnl)}</span>
      · open positions ${pp.positions.length}`;
  }catch(e){console.warn(e)}
}
function headRow(cols){return `<tr>${cols.map(c=>`<th>${c}</th>`).join("")}</tr>`}
function drawGauge(score,label){
  const a=Math.PI*(1-Math.min(Math.max(score,-1),1))/1; // map -1..1 -> pi..0
  const cx=100,cy=100,r=78;
  const x=cx+r*Math.cos(Math.PI-a*0+a),y=cy-r*Math.sin(a);
  const ang=Math.PI-(score+1)/2*Math.PI;
  const nx=cx+r*Math.cos(ang), ny=cy-r*Math.sin(ang);
  const col=score>0.25?"var(--green)":score<-0.25?"var(--red)":"var(--amber)";
  $("#regimeGauge").innerHTML=`
    <path d="M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${cx+r} ${cy}" fill="none" stroke="#232b40" stroke-width="14"/>
    <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="${col}" stroke-width="4"/>
    <circle cx="${cx}" cy="${cy}" r="6" fill="${col}"/>`;
  const el=$("#regimeLabel"); el.textContent=label;
  el.style.color=col;
}
loadDashboard(); setInterval(loadDashboard,120000);

/* ─────────────────────────────────────────────
   SCREENER & SIGNALS
──────────────────────────────────────────────*/
const FACTOR_DOCS={score:"screener_composite",rsi:"rsi",adx:"adx",vol_z:"volume_anomaly",
  rs_vs_nifty_pct:"relative_strength",atr_pct:"atr"};
$("#btnScreener").onclick=async()=>{
  $("#scrStatus").textContent="scanning universe…"; 
  try{
    const u=$("#scrUniverse").value.trim();
    const q=`/screener?top_n=${$("#scrTopN").value}${u?`&universe=${encodeURIComponent(u)}`:""}`;
    const d=await api(q);
    $("#screenerTable").innerHTML=headRow(["#","Symbol","Close","RSI ⓘ","ADX","ST","EMAs","3m %","RS vs Nifty %","Vol Z","From 52wH %","ATR %","SCORE"])
      +d.rows.map((r,i)=>`<tr data-sym="${esc(r.symbol)}">
        <td class="muted">${i+1}</td><td class="mono"><b>${esc(r.symbol)}</b></td>
        <td class="num">${num(r.close)}</td><td class="num">${num(r.rsi,1)}</td>
        <td class="num">${num(r.adx,1)}</td><td>${r.st_dir===1?'<span class="pos">▲long</span>':'<span class="neg">▼short</span>'}</td>
        <td>${r.above_emas?'<span class="pos">✓stacked</span>':'—'}</td>
        <td class="num ${cls(r.ret_3m_pct)}">${num(r.ret_3m_pct,1)}</td>
        <td class="num ${cls(r.rs_vs_nifty_pct)}">${num(r.rs_vs_nifty_pct,1)}</td>
        <td class="num">${num(r.vol_z,2)}</td>
        <td class="num ${cls(-r.pct_from_52wh)}">${num(r.pct_from_52wh,1)}</td>
        <td class="num">${num(r.atr_pct,2)}</td>
        <td class="num"><b style="color:${r.score>=65?"var(--green)":r.score>=50?"var(--cyan)":"var(--amber)"}">${num(r.score,1)}</b></td></tr>`).join("");
    $$("#screenerTable tbody tr").forEach(tr=>tr.onclick=()=>showSignal(tr.dataset.sym));
    $("#scrStatus").textContent=`done @ ${new Date(d.generated_at).toLocaleTimeString("en-IN")}`;
    toast(`Top ${d.rows.length} candidates ranked`);
  }catch(e){$("#scrStatus").textContent="failed: "+e.message;}
};

async function showSignal(sym){
  const strat=$("#sigStrategy").value;
  $("#signalCard").classList.remove("hidden");
  $("#sigTitle").innerHTML=`Signal — <span class="mono pos">${esc(sym)}</span>`;
  $("#signalBody").innerHTML='<p class="muted">computing…</p>';
  try{
    const s=await api("/signals",{method:"POST",body:JSON.stringify({symbol:sym,strategy:strat})});
    if(s.direction===0){
      $("#signalBody").innerHTML=`<p class="neu">NO TRADE — strategy conditions not met. Rationale:
        <span class="mono small">${esc(JSON.stringify(s.rationale))}</span></p>`; return;}
    const cells=[["Direction",s.direction===1?'BUY':'SELL',s.direction===1?"pos":"neg"],
      ["Entry",num(s.entry)],["Stop",num(s.stop),"neg"],["Target 1 (+1R)",num(s.target1)],
      ["Target 2",num(s.target2),"pos"],["R:R",s.rr?`1 : ${s.rr}`:"—"],
      ["Confidence",`${s.confidence}%`],["Horizon",s.holding_period]];
    $("#signalBody").innerHTML=`
      <div class="sig-grid">${cells.map(c=>`<div class="sig-cell"><div class="k">${c[0]}</div>
        <div class="v ${c[2]||""}">${c[1]}</div></div>`).join("")}
        ${s.sizing?`<div class="sig-cell"><div class="k">Qty @1% risk <i class="fi" data-f="atr_position_size"></i></div>
          <div class="v">${s.sizing.qty}</div></div>`:""}
      </div>
      <div class="rationale"><b>why:</b> ${esc(JSON.stringify(s.rationale))}
       · <b>regime:</b> FII bias ${s.regime.label} (${s.regime.score}) <i class="fi" data-f="fii_dii_regime_score"></i></div>
      ${s.sizing&&s.sizing.qty>0?`<div class="row-actions"><button id="btnPaperFromSig" class="primary">
        ➕ Paper-buy ${s.sizing.qty} @ ~₹${num(s.entry)}</button></div>`:""}`;
    const b=$("#btnPaperFromSig");
    if(b)b.onclick=async()=>{try{
      await api("/paper/order",{method:"POST",body:JSON.stringify(
        {symbol:sym,side:"BUY",qty:s.sizing.qty,price:s.entry,tag:strat.slice(0,12)})});
      toast("Paper order filled ✓");}catch(e){toast("✗ "+e.message);}};
  }catch(e){$("#signalBody").innerHTML=`<p class="neg">error: ${esc(e.message)}</p>`;}
}
$("#btnRegenSignal").onclick=()=>{const sym=$("#screenerTable tbody tr")?.dataset.sym||currentSymbol();showSignal(sym);};

/* ─────────────────────────────────────────────
   CHARTS PANEL (lightweight-charts)
──────────────────────────────────────────────*/
let tvMain,tvRsi,tvMacd,seriesMap={};
function initTV(){
  const copts={layout:{background:{color:"#11151f"},textColor:"#7c8aa5"},
    grid:{vertLines:{color:"#161c2c"},horzLines:{color:"#161c2c"}},
    timeScale:{timeVisible:false,borderColor:"#232b40"}};
  tvMain=LightweightCharts.createChart($("#tvMain"),copts);
  seriesMap.candles=tvMain.addCandlestickSeries({upColor:"#22c55e",downColor:"#ef4444",
    borderVisible:false,wickUpColor:"#22c55e",wickDownColor:"#ef4444"});
  seriesMap.vol=tvMain.addHistogramSeries({priceFormat:{type:"volume"},priceScaleId:""});
  seriesMap.vol.priceScale().applyOptions({scaleMargins:{top:.85,bottom:0}});
  seriesMap.ema20=tvMain.addLineSeries({color:"#f59e0b",lineWidth:1,title:"EMA20"});
  seriesMap.ema50=tvMain.addLineSeries({color:"#38bdf8",lineWidth:2,title:"EMA50"});
  seriesMap.ema200=tvMain.addLineSeries({color:"#a78bfa",lineWidth:2,title:"EMA200"});
  seriesMap.bbU=tvMain.addLineSeries({color:"rgba(124,138,165,.5)",lineWidth:1});
  seriesMap.bbL=tvMain.addLineSeries({color:"rgba(124,138,165,.5)",lineWidth:1});
  seriesMap.st=tvMain.addLineSeries({color:"#22c55e",lineWidth:2,title:"Supertrend"});
  tvRsi=LightweightCharts.createChart($("#tvRsi"),{...copts,height:110});
  seriesMap.rsi=tvRsi.addLineSeries({color:"#38bdf8",lineWidth:2,priceScaleId:""});
  tvMacd=LightweightCharts.createChart($("#tvMacd"),{...copts,height:110});
  seriesMap.macd=tvMacd.addLineSeries({color:"#38bdf8",lineWidth:1.5});
  seriesMap.macdsig=tvMacd.addLineSeries({color:"#f59e0b",lineWidth:1});
  seriesMap.hist=tvMacd.addHistogramSeries({});
  ["ovEma200"].forEach(id=>$("#"+id).onchange=applyOverlays);
  ["ovEma50","ovBB","ovST"].forEach(id=>$("#"+id).onchange=applyOverlays);
  window._tvReady=true;
}
function applyOverlays(){
  if(!seriesMap.raw)return;
  const o=seriesMap.raw.overlays,st=seriesMap.raw.st_dir_arr;
  const stSplit=[]; let prev=null;
  o.supertrend.forEach((p,i)=>{const d=st[i];if(prev!==null&&d!==prev)stSplit.push({time:p[0],value:null});
    stSplit.push({time:p[0],value:p[1]});prev=d;});
  seriesMap.ema20.setData($("#ovEma20").checked?o.ema20:[]);
  seriesMap.ema50.setData($("#ovEma50").checked?o.ema50:[]);
  seriesMap.ema200.setData($("#ovEma200").checked?o.ema200:[]);
  seriesMap.bbU.setData($("#ovBB").checked?o.bb_upper:[]);
  seriesMap.bbL.setData($("#ovBB").checked?o.bb_lower:[]);
  seriesMap.st.setData($("#ovST").checked?stSplit.filter(p=>p.value!=null):[]);
}
async function loadChart(){
  if(!window._tvReady)initTV();
  const sym=currentSymbol(),per=$("#chPeriod").value;
  try{
    const d=await api(`/history/${sym}?period=${per}&interval=1d`);
    seriesMap.raw=d; seriesMap.raw.st_dir_arr=d.overlays.st_dir;
    seriesMap.candles.setData(d.candles.map(c=>({time:c[0],open:c[1],high:c[2],low:c[3],close:c[4]})));
    seriesMap.vol.setData(d.volume.map(v=>({time:v[0],value:v[1],
      color:d.candles.find(c=>c[0]===v[0])[4]>=d.candles.find(c=>c[0]===v[0])[1]?"rgba(34,197,94,.35)":"rgba(239,68,68,.35)"})));
    applyOverlays();
    seriesMap.rsi.setData(d.sub.rsi.map(p=>({time:p[0],value:p[1]})));
    seriesMap.macd.setData(d.sub.macd.map(p=>({time:p[0],value:p[1]})));
    seriesMap.macdsig.setData(d.sub.macd_sig.map(p=>({time:p[0],value:p[1]})));
    seriesMap.hist.setData(d.sub.macd_hist.map(p=>({time:p[0],value:p[1],
      color:p[1]>=0?"rgba(34,197,94,.6)":"rgba(239,68,68,.6)"})));
    const s=d.snapshot;
    const rows=[["RSI 14 <i class='fi' data-f='rsi'></i>",num(s.rsi,1),s.rsi>70?"neg overbought":s.rsi<30?"pos oversold":""],
      ["ADX <i class='fi' data-f='adx'></i>",num(s.adx,1),s.adx>25?"pos trending":"neu range"],
      ["Supertrend <i class='fi' data-f='supertrend'></i>",s.st_dir===1?"LONG":"SHORT",s.st_dir===1?"pos":"neg"],
      ["ATR ₹ (% of px) <i class='fi' data-f='atr'></i>",`${num(s.atr)} (${num(s.atr_pct,1)}%)`,""],
      ["Volume z-score <i class='fi' data-f='volume_anomaly'></i>",num(s.volz,2),Math.abs(s.volz)>2?"neu anomaly!":""],
      ["From 52w high",num(s.pct_from_52wh,1)+"%",cls(-s.pct_from_52wh)]];
    $("#indReadout").innerHTML=rows.map(r=>`<div class="ind-row"><span class="muted">${r[0]}</span>
      <b class="${r[2].split(" ")[0]||""}">${r[1]}</b></div>`).join("");
  }catch(e){toast("chart failed: "+e.message);}
}
$("#btnChart").onclick=loadChart;

/* ─────────────────────────────────────────────
   OPTIONS LAB
──────────────────────────────────────────────*/
async function initOptions(){
  try{
    const u=$("#optUnderlying").value;
    const d=await api(`/options/expiries/${u}`);
    $("#optExpiry").innerHTML=d.expiries.map(e=>`<option>${esc(e)}</option>`).join("");
    loadChain();
  }catch(e){$("#chainStatus").textContent="NSE chain unavailable ("+e.message+") — works once market API reachable";}
}
$("#optUnderlying").onchange=initOptions;
$("#btnChain").onclick=()=>{const u=$("#optUnderlying").value,e=$("#optExpiry").value;
  window._chainData=null; loadChain(u,e);};
async function loadChain(u=$("#optUnderlying").value,e=$("#optExpiry").value){
  $("#chainStatus").textContent="fetching from NSE OSINT…";
  try{
    const d=await api(`/options/chain?underlying=${u}&expiry=${encodeURIComponent(e)}`);
    window._chainData=d; $("#chainStatus").textContent=`expiry ${d.expiry_used} · DTE ${d.dte}`;
    const intel=d.intel;
    $("#optIntelTiles").innerHTML=[
      ["PCR OI",intel.pcr,intel.pcr_read,"pcr"],
      ["Max Pain",intel.max_pain,"spot drift magnet into expiry","max_pain"],
      ["Support (max PE OI)",intel.support_max_pe_oi,"heaviest put wall",""],
      ["Resistance (max CE OI)",intel.resistance_max_ce_oi,"heaviest call wall",""]]
      .map(t=>`<div class="tile"><div class="t-label">${t[0]} <i class="fi" data-f="${t[3]||"max_pain"}"></i></div>
        <div class="t-value mono">${typeof t[1]==="number"?num(t[1]):esc(t[1])}</div>
        <div class="t-sub">${esc(t[2])}</div></div>`).join("");
    bindInfoIcons();
    const strikes=d.chain.map(c=>c.strike),mid=strikes.length>60?strikes.slice(30,-30):strikes;
    const sub=d.chain.filter(c=>mid.includes(c.strike));
    regChart("oi",new Chart($("#oiChart"),{type:"bar",data:{
      labels:sub.map(c=>c.strike),
      datasets:[{label:"CE OI",data:sub.map(c=>c.ce_oi),backgroundColor:"rgba(239,68,68,.65)"},
                {label:"PE OI",data:sub.map(c=>c.pe_oi),backgroundColor:"rgba(34,197,94,.65)"}]},
      options:{scales:{x:{ticks:{color:"#7c8aa5",maxRotation:90}},y:{ticks:{color:"#7c8aa5"}}}}}));
    regChart("iv",new Chart($("#ivSmile"),{type:"line",data:{
      labels:sub.map(c=>c.strike),
      datasets:[{label:"CE IV%",data:sub.map(c=>c.ce_iv),borderColor:"#ef4444",tension:.35},
                {label:"PE IV%",data:sub.map(c=>c.pe_iv),borderColor:"#22c55e",tension:.35}]},
      options:{plugins:{legend:{labels:{color:"#7c8aa5"}}},scales:{x:{ticks:{color:"#7c8aa5",maxRotation:90}},y:{ticks:{color:"#7c8aa5"}}}}}));
    const spot=d.chain[0]?.spot;
    $("#chainTable").innerHTML=`<tr><th colspan="8" style="color:#ef4444">CALLS ← spot ${spot} → PUTS</th></tr>
      <tr><th>OI</th><th>ChgOI</th><th>IV%</th><th>Δ</th><th>LTP</th><th>Strike</th>
      <th>LTP</th><th>IV% / Δ</th></tr>`+
      d.chain.filter(c=>Math.abs(c.strike-spot)<Math.max(spot*.08,300))
        .map(c=>`<tr class="${Math.abs(c.strike-spot)<150?"atm-row":""}">
        <td class="num">${num(c.ce_oi/1e5,1)}L</td><td class="num ${cls(c.ce_chg_oi)}">${num(c.ce_chg_oi/1e5,1)}L</td>
        <td class="num">${num(c.ce_iv,1)}</td><td class="num">${num(c.ce_delta,2)}</td>
        <td class="num pos">${num(c.ce_ltp,1)}</td><td><b>${num(c.strike,0)}</b></td>
        <td class="num neg">${num(c.pe_ltp,1)}</td><td class="num">${num(c.pe_iv,1)} / ${num(c.pe_delta,2)}</td></tr>`).join("");
  }catch(err){$("#chainStatus").textContent="chain failed: "+err.message;}
}
$("#btnBuild").onclick=async()=>{
  const spot=parseFloat($("#pbSpot").value)||24500;
  try{
    const st=await api("/options/preset",{method:"POST",body:JSON.stringify({
      preset:$("#presetSel").value,spot,sigma:(parseFloat($("#pbSigma").value)||15)/100,
      days:parseInt($("#pbDays").value)||21})});
    regChart("payoff",new Chart($("#payoffChart"),{type:"line",data:{
      labels:st.payoff.spots,
      datasets:[{label:"PnL at expiry ₹",data:st.payoff.pnl,borderColor:"#38bdf8",
        pointRadius:0,tension:0,
        segment:{borderColor:c=>c.p1.y<0?"#ef4444":"#38bdf8"}}]},
      options:{plugins:{legend:{labels:{color:"#7c8aa5"}}},
        scales:{x:{ticks:{color:"#7c8aa5",maxTicksLimit:12}},y:{ticks:{color:"#7c8aa5"}}}}}));
    $("#structureStats").innerHTML=[
      ["Structure",st.label],["Net premium ₹",num(st.net_premium)],
      ["Max profit ₹",num(st.max_profit)],["Max loss ₹",num(st.max_loss)],
      ["Breakevens",(st.breakevens||[]).join(" , ")||"—"]]
      .map(r=>`<div class="ind-row"><span class="muted">${esc(r[0])}</span><b class="mono">${esc(r[1])}</b></div>`).join("")
      +`<table class="tbl tiny mono mt8"><tr><th>Type</th><th>Strike</th><th>Side</th><th>Px</th><th>Δ</th><th>Θ/d</th><th>Vega</th></tr>`+
       st.legs.map(l=>`<tr><td>${l.type}</td><td>${l.strike}</td><td class="${l.side==="buy"?"pos":"neg"}">${l.side}</td>
         <td>${num(l.price)}</td><td>${num(l.delta,2)}</td><td>${num(l.theta,1)}</td><td>${num(l.vega,1)}</td></tr>`).join("")+"</table>";
    toast(`${st.label}: maxP ${fmtINR(st.max_profit)} / maxL ${fmtINR(st.max_loss)}`);
  }catch(e){toast("✗ "+e.message);}
};

/* ─────────────────────────────────────────────
   BACKTEST LAB
──────────────────────────────────────────────*/
const METRIC_LABELS={total_return_pct:"Total Return %",cagr_pct:["CAGR % <i class='fi' data-f='cagr'></i>"],
  sharpe:["Sharpe <i class='fi' data-f='sharpe_ratio'></i>"],sortino:["Sortino <i class='fi' data-f='sortino_ratio'></i>"],
  max_drawdown_pct:["Max DD % <i class='fi' data-f='max_drawdown'></i>"],calmar:["Calmar <i class='fi' data-f='calmar_ratio'></i>"],
  win_rate_pct:["Win Rate % <i class='fi' data-f='win_rate'></i>"],profit_factor:["Profit Factor <i class='fi' data-f='profit_factor'></i>"],
  trades:"Trades",expectancy_rs:"Expectancy ₹/trade",avg_r_multiple:"Avg R",avg_hold_days:"Avg Hold d",
  final_equity:"Final Equity ₹",exposure_pct:"Exposure %"};
$("#btnBacktest").onclick=async()=>{
  $("#btStatus").textContent="running simulation…";
  try{
    const b={symbol:$("#btSymbol").value.trim().toUpperCase(),strategy:$("#btStrategy").value,
      capital:+$("#btCapital").value,risk_pct:+$("#btRisk").value,atr_mult:+$("#btAtr").value,
      max_hold_days:+$("#btHold").value};
    const d=await api("/backtest",{method:"POST",body:JSON.stringify(b)});
    const m=d.metrics;
    const keys=["total_return_pct","cagr_pct","sharpe","sortino","max_drawdown_pct","win_rate_pct",
      "profit_factor","trades","expectancy_rs","avg_r_multiple","avg_hold_days","final_equity"];
    $("#btMetricTiles").innerHTML=keys.map(k=>`<div class="tile">
      <div class="t-label">${METRIC_LABELS[k]||k}</div>
      <div class="t-value mono ${k.includes("drawdown")?(m[k]<0?"neg":""):cls(m[k])}">${num(m[k],k==="final_equity"?0:2)}</div></div>`).join("");
    bindInfoIcons();
    const toXY=a=>a.map(p=>({x:new Date(p[0]*1000).toLocaleDateString("en-IN"),y:p[1]}));
    regChart("eq",new Chart($("#eqChart"),{type:"line",data:{labels:d.equity.map(p=>new Date(p[0]*1000).toLocaleDateString("en-IN")),
      datasets:[{label:"Strategy ₹",data:d.equity.map(p=>p[1]),borderColor:"#38bdf8",pointRadius:0,borderWidth:2},
                {label:"Buy&Hold ₹",data:d.buy_hold.map(p=>p[1]),borderColor:"rgba(124,138,165,.7)",
                 pointRadius:0,borderWidth:1.5,borderDash:[5,4]}]},
      options:{plugins:{legend:{labels:{color:"#7c8aa5"}}},scales:{x:{ticks:{color:"#7c8aa5",maxTicksLimit:10}},
        y:{ticks:{color:"#7c8aa5"}}}}}));
    regChart("dd",new Chart($("#ddChart"),{type:"line",data:{labels:d.drawdown.map(p=>new Date(p[0]*1000).toLocaleDateString("en-IN")),
      datasets:[{label:"Drawdown %",data:d.drawdown.map(p=>p[1]),borderColor:"#ef4444",
        backgroundColor:"rgba(239,68,68,.15)",fill:true,pointRadius:0}]},
      options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#7c8aa5",maxTicksLimit:10}},
        y:{ticks:{color:"#7c8aa5"}}}}}));
    const rs=d.trades.map(t=>t.r_mult).filter(r=>r!=null&&!Number.isNaN(r));
    const buckets={};rs.forEach(r=>{const b=Math.round(r);buckets[b]=(buckets[b]||0)+1;});
    regChart("rh",new Chart($("#rHist"),{type:"bar",data:{labels:Object.keys(buckets).sort((a,b)=>a-b),
      datasets:[{data:Object.keys(buckets).sort((a,b)=>a-b).map(k=>buckets[k]),
        backgroundColor:Object.keys(buckets).sort((a,b)=>a-b).map(k=>k>=0?"rgba(34,197,94,.7)":"rgba(239,68,68,.7)")}]},
      options:{plugins:{title:{display:true,text:"R-multiples per closed trade",color:"#7c8aa5"}},
        scales:{x:{title:{display:true,text:"R multiple",color:"#7c8aa5"},ticks:{color:"#7c8aa5"}},
          y:{ticks:{color:"#7c8aa5"}}}}}));
    $("#btTrades").innerHTML=headRow(["Entry","Exit","Px in","Px out","Qty","P&L ₹","R","Why","Days"])+
      [...d.trades].reverse().map(t=>`<tr><td>${t.entry_date?.slice(0,10)}</td><td>${t.exit_date?.slice(0,10)}</td>
        <td>${num(t.entry)}</td><td>${num(t.exit)}</td><td>${t.qty}</td>
        <td class="num ${cls(t.pnl)}">${num(t.pnl,0)}</td><td class="num">${num(t.r_mult,2)}</td>
        <td><span class="${t.reason==="STOP"?"neg":"pos"}">${t.reason}</span></td><td>${t.hold_days}</td></tr>`).join("");
    $("#btStatus").textContent=`done — ${m.trades} trades, PF ${m.profit_factor}, Sharpe ${m.sharpe}`;
    toast(`Backtest complete: CAGR ${m.cagr_pct}% · MDD ${m.max_drawdown_pct}%`);
  }catch(e){$("#btStatus").textContent="failed: "+e.message;}
};

/* ─────────────────────────────────────────────
   WHALE RADAR
──────────────────────────────────────────────*/
$("#btnWhaleTable").onclick=loadWhales;
async function loadWhales(){
  try{
    const d=await api(`/market/deals?type=whale_table&days=${$("#whDays").value}`);
    $("#whaleTable").innerHTML=headRow(["Date","Type","Symbol","Client","Class","Side","Qty","Avg ₹","Value ₹Cr"])+
      d.rows.map(r=>`<tr><td>${esc(r.date??"")}</td><td>${r.deal_type==="BLOCK"?
        '<span style="color:var(--violet)">BLOCK</span>':"bulk"}</td><td class="mono"><b>${esc(r.symbol)}</b></td>
        <td class="small">${esc((r.client??"").slice(0,30))}</td>
        <td><span class="${r.class==="INSTITUTION"?"pos":r.class==="HNI/DESK"?"neu":"muted"}">${esc(r.class)}</span></td>
        <td>${String(r.side??"").toUpperCase().startsWith("B")?'<span class="pos">BUY</span>':'<span class="neg">SELL</span>'}</td>
        <td class="num">${num(r.qty,0)}</td><td class="num">${num(r.avg_price,1)}</td>
        <td class="num"><b>${num(r.value_cr,1)}</b></td></tr>`).join("");
    toast(`${d.rows.length} whale prints loaded`);
  }catch(e){toast("✗ "+e.message);}
}
$("#btnWhaleScore").onclick=async()=>{
  const s=$("#whSymbol").value.trim().toUpperCase(); if(!s)return;
  try{
    const d=await api(`/market/whale/${s}`);
    $("#whaleScoreCard").classList.remove("hidden");
    const pct=Math.min(d.whale_score,100);
    const col=pct>=65?"var(--green)":pct>=45?"var(--cyan)":pct<=20?"var(--red)":"var(--amber)";
    $("#whaleScoreBody").innerHTML=`
      <div class="big-label" style="color:${col}">${d.label} — ${pct}/100</div>
      <div style="background:var(--bg2);border-radius:99px;height:12px;margin:12px 0;overflow:hidden">
        <div style="width:${pct}%;height:100%;background:${col};transition:width .6s"></div></div>
      <table class="tbl compact">${Object.entries(d.components).map(([k,v])=>
        `<tr><td class="mono">${esc(k)}</td><td class="num">${esc(v)}</td></tr>`).join("")}</table>
      <p class="muted small mt8">How this is computed <i class="fi" data-f="whale_score"></i></p>`;
  }catch(e){toast("✗ "+e.message);}
};

/* ─────────────────────────────────────────────
   PORTFOLIO & RISK
──────────────────────────────────────────────*/
$("#btnSize").onclick=async()=>{
  try{
    const d=await api("/risk/size",{method:"POST",body:JSON.stringify({
      entry:+$("#szEntry").value,stop:+$("#szStop").value,
      capital:+$("#szCap").value,risk_pct:+$("#szRisk").value})});
    $("#sizeOut").innerHTML=[["Quantity",d.qty],["Rupees at risk",fmtINR(d.risk_rs)],
      ["Notional exposure",fmtINR(d.notional_rs)],["Risk as % capital",d.risk_pct_of_capital+"%"]]
      .map(r=>`<div class="ind-row"><span class="muted">${r[0]}</span><b class="mono">${r[1]}</b></div>`).join("")
      +`<p class="muted small mt8">qty = (capital × risk%) ÷ |entry − stop| <i class="fi" data-f="atr_position_size"></i></p>`;
  }catch(e){toast("✗ "+e.message);}
};
$("#btnKelly").onclick=async()=>{
  try{
    const d=await api("/risk/kelly",{method:"POST",body:JSON.stringify({
      win_rate:+$("#klWin").value/100,rr:+$("#klRR").value,capital:+$("#klCap").value})});
    $("#kellyOut").innerHTML=[["Full Kelly fraction",d.full_kelly_fraction],
      ["Applied (half-Kelly)",d.applied_fraction],["Allocation",fmtINR(d.allocation_rs)],
      ["Note",d.note]].map(r=>`<div class="ind-row"><span class="muted">${esc(r[0])}</span>
        <b class="mono small">${esc(r[1])}</b></div>`).join("")
      +`<p class="muted small mt8">f* = W − (1−W)/RR <i class="fi" data-f="kelly_criterion"></i></p>`;
  }catch(e){toast("✗ "+e.message);}
};
$("#btnVar").onclick=async()=>{
  try{
    const d=await api("/risk/var",{method:"POST",body:JSON.stringify({
      symbols:$("#varSyms").value.split(",").map(s=>s.trim()),
      value:+$("#varVal").value,horizon_days:+$("#varHor").value,
      alpha:+$("#varAlpha").value/100})});
    $("#varOut").innerHTML=[["VaR "+(d.alpha*100)+"% ("+d.horizon_days+"d)",fmtINR(d.var_amount)],
      ["CVaR (expected shortfall)",fmtINR(d.cvar_amount)],["VaR %",d.var_pct+"%"],["CVaR %",d.cvar_pct+"%"]]
      .map(r=>`<div class="ind-row"><span class="muted">${esc(r[0])}</span><b class="mono neg">${esc(r[1])}</b></div>`).join("")
      +`<p class="muted small mt8">${esc(d.interpretation)} <i class="fi" data-f="var_historical"></i> <i class="fi" data-f="cvar"></i></p>`;
  }catch(e){toast("✗ "+e.message);}
};
$("#btnOptimize").onclick=async()=>{
  try{
    const syms=$("#poSymbols").value.split(",").map(s=>s.trim());
    const d=await api(`/portfolio/optimize?symbols=${encodeURIComponent(syms.join(","))}`);
    const ms=d.summary.max_sharpe.weights;
    regChart("alloc",new Chart($("#allocChart"),{type:"doughnut",data:{
      labels:Object.keys(ms),datasets:[{data:Object.values(ms).map(w=>w*100),
        backgroundColor:["#38bdf8","#22c55e","#f59e0b","#ef4444","#a78bfa","#06b6d4","#84cc16","#fb7185"]}]},
      options:{plugins:{legend:{position:"right",labels:{color:"#7c8aa5",boxWidth:10}},
        title:{display:true,text:"Max-Sharpe weights %",color:"#7c8aa5"}}}}));
    regChart("fr",new Chart($("#frontierChart"),{type:"scatter",data:{datasets:[
      {label:"Efficient frontier",data:d.frontier.map(p=>({x:p.vol,y:p.ret})),
       borderColor:"#38bdf8",showLine:true,pointRadius:2},
      {label:"Max Sharpe",data:[{x:d.summary.max_sharpe.vol_pct,y:d.summary.max_sharpe.exp_ret_pct}],
       pointBackgroundColor:"#22c55e",pointRadius:6}]},
      options:{plugins:{legend:{labels:{color:"#7c8aa5"}}},
        scales:{x:{title:{display:true,text:"volatility %",color:"#7c8aa5"},ticks:{color:"#7c8aa5"}},
          y:{title:{display:true,text:"return %",color:"#7c8aa5"},ticks:{color:"#7c8aa5"}}}}}));
    $("#optOut").innerHTML=Object.entries(d.summary).map(([k,v])=>
      `<div class="ind-row"><span class="muted mono">${k}</span>
       <span class="small">ret <b>${num(v.exp_ret_pct,1)}%</b> vol <b>${num(v.vol_pct,1)}%</b></span></div>`).join("")
      +`<p class="muted small mt8">HRP = hierarchical risk parity <i class="fi" data-f="hrp_cluster_var"></i> ·
        Markowitz QP <i class="fi" data-f="markowitz_variance"></i></p>`;
  }catch(e){toast("✗ "+e.message);}
};
async function refreshPaper(){
  try{
    const p=await api("/paper/portfolio");const o=await api("/paper/orders");
    $("#paperPositions").innerHTML=headRow(["Symbol","Qty","Avg","LTP","Value","P&L","%"])+
      p.positions.map(r=>`<tr><td class="mono"><b>${esc(r.symbol)}</b></td><td>${r.qty}</td>
        <td>${num(r.avg)}</td><td>${num(r.ltp)}</td><td class="num">${num(r.value,0)}</td>
        <td class="num ${cls(r.pnl)}">${num(r.pnl,0)}</td><td class="num ${cls(r.pnl_pct)}">${num(r.pnl_pct,1)}</td></tr>`).join("");
    $("#paperOrders").innerHTML=headRow(["ID","Time","Sym","Side","Qty","Price"])+
      o.orders.map(r=>`<tr><td>${r.order_id}</td><td>${r.time.slice(11,19)}</td><td class="mono">${esc(r.symbol)}</td>
        <td class="${r.side==="BUY"?"pos":"neg"}">${r.side}</td><td>${r.qty}</td><td>${num(r.price)}</td></tr>`).join("");
  }catch(e){}
}
$("#btnPaperOrder").onclick=async()=>{
  try{
    const r=await api("/paper/order",{method:"POST",body:JSON.stringify({
      symbol:$("#poSym").value.trim().toUpperCase(),side:$("#poSide").value,
      qty:+$("#poQty").value,price:+$("#poPrice").value})});
    toast(r.status==="FILLED"?`filled ${r.symbol} ${r.side} ${r.qty}@${r.price}`:`rejected: ${r.reason??""}`);
    refreshPaper();
  }catch(e){toast("✗ "+e.message);}
};
$("#btnPaperRefresh").onclick=refreshPaper;
refreshPaper();

/* ─────────────────────────────────────────────
   CASE STUDY PANEL
──────────────────────────────────────────────*/
const VERIFY_BADGE = v => {
  if (["verified","ok","curated-osint"].includes(v)) return '<span class="badge ok">'+esc(v)+'</span>';
  if (String(v).startsWith("verify") || String(v).startsWith("unverified"))
    return '<span class="badge warn">'+esc(v)+'</span>';
  return '<span class="badge info">'+esc(v||"osint")+'</span>';
};
$("#btnCaseBuild").onclick=()=>buildCase(false);
async function buildCase(refresh){
  $("#caseStatus").textContent="assembling dossier: resolving symbol → OHLCV → forensics → patterns → KB…";
  try{
    const d=await api(`/case/shree_refrigerations/full${refresh?"?refresh=true":""}`);
    window._caseData=d;
    renderCase(d);
    $("#caseStatus").textContent=`dossier ${d.generated_at.slice(0,16)} · ${(d.resolution.method||"unresolved").split("|")[0]} · ${(d.patterns||[]).length} pattern events`;
  }catch(e){ $("#caseStatus").textContent="failed: "+e.message; }
}
function renderCase(d){
  const pa=d.price_action, sf=d.surge_forensics||{};
  const ws=d.whale_score||{};
  const whaleKnown = ws.whale_score>0 || Object.keys(ws.components||{}).length>0;
  const verdictCls=(sf.verdict||"").includes("PARABOLIC")?"PARABOLIC":
    (sf.verdict||"").includes("IMPULSE")?"IMPULSE":
    (sf.verdict||"").includes("MILD")?"MILD":"NONE";
  const initials=d.display.split(" ").filter(Boolean).map(w=>w[0]).slice(0,2).join("");
  $("#csHero").innerHTML=`
    <div class="cs-id">
      <div class="cs-logo">${esc(initials)}</div>
      <div>
        <div class="cs-name">${esc(d.display)}</div>
        <div class="cs-chips">
          <span class="chip2 hl">${esc(d.resolution.exchange||"?")}</span>
          <span class="chip2">${esc(d.resolution.symbol||"—")}</span>
          <span class="chip2">${esc((d.ipo||{}).platform||"SME")}</span>
          <span class="chip2">listed ${(pa.first_date||"").slice(0,7)||"—"}</span>
        </div>
      </div>
    </div>
    <div class="hero-kpis">
      <div class="kpi"><div class="k">LTP ₹</div>
        <div class="v">${num(pa.ltp)}</div>
        <div class="s mono tiny">${esc((pa.first_date||"").slice(0,10))} → now</div></div>
      <div class="kpi"><div class="k">Since 1st print</div>
        <div class="v ${cls(pa.all_time_return_pct)}">${pa.all_time_return_pct>0?"+":""}${num(pa.all_time_return_pct,1)}%</div>
        <div class="s">all-time</div></div>
      <div class="kpi"><div class="k">Max DD <i class="fi" data-f="max_drawdown"></i></div>
        <div class="v neg">${num(pa.max_drawdown_pct,1)}%</div>
        <div class="s">peak → trough</div></div>
      <div class="kpi"><div class="k">Whale <i class="fi" data-f="whale_score"></i></div>
        <div class="v ${whaleKnown?(ws.whale_score>=45?"pos":"neg"):"muted"}">${whaleKnown?num(ws.whale_score,0):"n/a"}</div>
        <div class="s">${whaleKnown?esc(ws.label||""):"BSE · no NSE prints"}</div></div>
      <div class="kpi" style="align-self:center">
        <span class="verdict-pill ${verdictCls}">◈ ${esc(sf.verdict||"NO SURGE")}</span></div>
    </div>`;
  // price chart with gradient fill + pattern markers
  if(pa.series?.length){
    const labels=pa.series.map(p=>p[0]), vals=pa.series.map(p=>p[1]);
    const patNames={}; (d.patterns||[]).forEach(p=>patNames[p.date]=p.pattern);
    const cv=$("#csChart");
    const g=cv.getContext("2d").createLinearGradient(0,0,0,cv.height||240);
    g.addColorStop(0,"rgba(56,189,248,.30)"); g.addColorStop(1,"rgba(56,189,248,0)");
    regChart("cs",new Chart(cv,{type:"line",data:{labels,
      datasets:[{label:"Close ₹",data:vals,borderColor:"#38bdf8",borderWidth:1.8,
        tension:.2,fill:true,backgroundColor:g,pointRadius:0,pointHitRadius:8},
        {label:"Pattern events",data:vals.map((v,i)=>patNames[labels[i]]?v:null),
         pointBackgroundColor:"#f59e0b",pointBorderColor:"#0b0e14",pointBorderWidth:1.5,
         pointRadius:5.5,pointHoverRadius:7.5,showLine:false,borderColor:"#f59e0b"}]},
      options:{plugins:{legend:{display:false},
        tooltip:{mode:"index",intersect:false,backgroundColor:"#1a2032",
          borderColor:"#232b40",borderWidth:1,titleColor:"#38bdf8",padding:10,
          callbacks:{label:c=>c.datasetIndex===1
            ?"◈ "+(patNames[labels[c.dataIndex]]||"event")
            :" ₹"+num(c.parsed.y)}}},
        interaction:{mode:"index",intersect:false},
        scales:{x:{grid:{color:"rgba(35,43,64,.35)"},ticks:{color:"#7c8aa5",maxTicksLimit:9,maxRotation:0}},
          y:{grid:{color:"rgba(35,43,64,.35)"},ticks:{color:"#7c8aa5"}}}}}));
    $("#csLegend").innerHTML=
      `<span><span class="lg-dot" style="background:#38bdf8"></span>Close ₹</span>
       <span><span class="lg-dot" style="background:#f59e0b"></span>Pattern event</span>
       <span class="muted">${(d.patterns||[]).length} events detected — full log below</span>`;
  }
  if(sf.status!=="insufficient-history"){
    const blocks=[
      ["Window return",`${sf.window_return_pct>0?"+":""}${num(sf.window_return_pct,1)}%`,
       cls(sf.window_return_pct),Math.min(Math.abs(sf.window_return_pct)/40*100,100),
       sf.window_return_pct>=0?"#22c55e":"#ef4444","rsi"],
      ["Volume vs baseline",num(sf.volume_multiple_vs_baseline,2)+"×",
       sf.volume_multiple_vs_baseline>2?"pos":"",
       Math.min(sf.volume_multiple_vs_baseline/5*100,100),"#38bdf8","volume_anomaly"],
      ["ATR expansion",num(sf.atr_expansion_x,2)+"×",
       sf.atr_expansion_x>1.5?"neg":"",Math.min(sf.atr_expansion_x/3*100,100),"#f59e0b","atr"],
      ["Days >±4% move",String(sf.days_with_gt4pct_move),"neu",
       Math.min(sf.days_with_gt4pct_move/10*100,100),"#a78bfa","atr_percentile"],
      ["Max up-streak",String(sf.max_consecutive_up_days),"pos",
       Math.min(sf.max_consecutive_up_days/10*100,100),"#22c55e",""],
      ["Gap days >3%",String(sf.gap_days_gt3pct),"",
       Math.min(sf.gap_days_gt3pct/10*100,100),"#fb7185",""],
    ];
    $("#csForensics").innerHTML=`<div class="stat-grid">`+blocks.map(b=>`
      <div class="stat-block"><div class="sk">${esc(b[0])}${b[5]?` <i class="fi" data-f="${b[5]}"></i>`:""}</div>
        <div class="sv ${b[2]}">${b[1]}</div>
        <div class="mini-bar"><div style="width:${b[3]}%;background:${b[4]}"></div></div></div>`).join("")
      +`</div><div class="callout"><b>Read:</b> ${esc(sf.verdict||"").toLowerCase()} —
        ${num(sf.volume_multiple_vs_baseline,2)}× normal volume with ${num(sf.atr_expansion_x,2)}× ATR expansion
        (last ${sf.window_sessions} sessions vs prior ${sf.baseline_sessions}). ${
        sf.volume_multiple_vs_baseline>3&&sf.atr_expansion_x>2
        ?"Profile matches momentum-crowding, not quiet accumulation — trail stops hard and respect circuit-limit risk."
        :"Moderate expansion — cross-check whale prints & delivery behaviour before assuming operator drive."}</div>`;
  } else $("#csForensics").innerHTML='<p class="muted">insufficient history</p>';

  $("#csHypo").innerHTML=(d.hypotheses||[]).map(h=>`<div class="hypo-card">
    <b>${h.id}</b> · ${esc(h.claim)}
    <div class="hypo-bar"><div style="width:${h.weight*100}%"></div></div>
    <div class="muted small mt8">evidence to check: ${esc(h.evidence_needed)} · weight ${(h.weight*100)|0}%</div>
    </div>`).join("");
  $("#csRisks").innerHTML=(d.risks||[]).map(r=>`<li>${esc(r)}</li>`).join("");
  $("#csPatterns").innerHTML=headRow(["Date","Pattern","Detail"])+
    (d.patterns||[]).map(p=>`<tr><td>${esc(p.date)}</td>
      <td><span class="${p.pattern.includes("TOP")?"neg":"pos"}">${esc(p.pattern)}</span></td>
      <td>${esc(p.detail)}</td></tr>`).join("");
  if(d.competitors?.length){
    regChart("cscomp",new Chart($("#csCompChart"),{type:"bar",data:{
      labels:d.competitors.map(c=>c.symbol),
      datasets:[{label:"RS vs Nifty 3m %",data:d.competitors.map(c=>c.rs_vs_nifty_3m),
        backgroundColor:d.competitors.map(c=>c.rs_vs_nifty_3m>=0?"rgba(34,197,94,.7)":"rgba(239,68,68,.7)")}]},
      options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#7c8aa5"}},y:{ticks:{color:"#7c8aa5"}}}}}));
    $("#csCompTable").innerHTML=headRow(["Symbol","3m %","1y %","Vol%"]) +
      d.competitors.map(c=>`<tr><td class="mono"><b>${esc(c.symbol)}</b></td>
        <td class="num ${cls(c.ret_3m_pct)}">${num(c.ret_3m_pct,1)}</td>
        <td class="num ${cls(c.ret_1y_pct)}">${num(c.ret_1y_pct,1)}</td>
        <td class="num">${num(c.ann_vol_pct,1)}</td></tr>`).join("");
  }
  const metaMap={}; (d.competitor_meta||[]).forEach(m=>metaMap[m.symbol]=m);
  $("#csNews").innerHTML=[...(d.news_curated||[]).map(n=>({headline:n.headline,tag:n.tag,verify:n.verify,date:n.date,source:"curated KB"})),
    ...d.profile.business_lines.map(b=>({headline:b,tag:"BUSINESS",verify:"profile",source:"company profile"}))]
    .map(n=>`<div class="news-item"><div class="nh">${esc(n.headline)}</div>
      <div class="nm"><span>${esc(n.date||"")}</span>${VERIFY_BADGE(n.verify)}
      <span class="badge info">${esc(n.tag)}</span></div></div>`).join("");
  $("#csFin").innerHTML="<tr><th>Metric</th><th>Value</th><th>Flag</th></tr>"+
    (d.financials_kb?.metrics||[]).map(m=>`<tr><td>${esc(m.metric)}</td>
      <td class="mono">${esc(m.value)}</td><td>${VERIFY_BADGE(m.verify)}</td></tr>`).join("")
    +`<tr><td colspan=3 class="muted small">${esc(d.financials_kb?.note||"")}</td></tr>`;
  $("#csWhaleBox").innerHTML=whaleKnown?`
    <div class="big-label" style="font-size:20px;color:${ws.whale_score>=65?"var(--green)":ws.whale_score>=45?"var(--cyan)":ws.whale_score>0?"var(--red)":"var(--muted)"}">
      ${esc(ws.label||"—")} · ${num(ws.whale_score,0)}/100</div>
    <table class="tbl tiny mono mt8">${Object.entries(ws.components||{}).map(([k,v])=>
      `<tr><td>${esc(k)}</td><td class=num>${esc(v)}</td></tr>`).join("")}</table>`
    :`<p class="muted small">No institutional prints available — ${esc(d.resolution.symbol||"")} is
      BSE-listed and NSE bulk/block-deal feeds don't cover it. Only volume-anomaly evidence
      applies here (see forensics panel).</p>`;
  loadCaseNotes();
  $("#csRaw").textContent=JSON.stringify(d,null,2).slice(0,20000);
}
async function loadCaseNotes(){
  try{ const d=await api("/case/shree_refrigerations/notes");
    $("#csNotes").innerHTML=headRow(["When","Note"]) + d.notes.slice(0,20).map(n=>
      `<tr><td class="muted tiny">${n.at.slice(0,16)}</td><td class="small">${esc(n.text)}</td></tr>`).join("");
  }catch(e){}
}
$("#btnSaveNote").onclick=async()=>{
  const t=$("#noteText").value.trim(); if(!t)return;
  try{ await api("/case/shree_refrigerations/notes",{method:"POST",
    body:JSON.stringify({text:t})}); $("#noteText").value="";
    toast("note saved to research store ✓"); loadCaseNotes();
  }catch(e){toast("✗ "+e.message);}
};

/* ─────────────────────────────────────────────
   VOLATILITY RADAR PANEL
──────────────────────────────────────────────*/
$("#btnRadarScan").onclick=async()=>{
  $("#radarStatus").textContent="scanning instruments…";
  try{
    const d=await api("/radar/instruments");
    window._radarRows=d.rows;
    $("#radarTable").innerHTML=headRow(["Instrument","Type","LTP","Ann Vol YZ % ⓘ","Vol Pctl 1y ⓘ","ATR %","Avg Range %","1w %","1m %","Vol Z","Next Expiry","Stance","Playbook"])
      +d.rows.map(r=>{
        const e=r.next_expiries[0]||{};
        return `<tr data-inst="${esc(r.instrument)}">
        <td class="mono"><b>${esc(r.instrument)}</b><br/><span class="muted tiny">${esc(r.label)}</span></td>
        <td>${esc(r.kind)}</td><td class="num">${num(r.ltp)}</td>
        <td class="num ${r.vol_percentile_1y>75?"neg":r.vol_percentile_1y<25?"pos":""}"><b>${num(r.ann_vol_yz_pct,1)}</b></td>
        <td class="num">${num(r.vol_percentile_1y,0)}</td>
        <td class="num">${num(r.atr_pct,2)}</td><td class="num">${num(r.avg_daily_range_pct,2)}</td>
        <td class="num ${cls(r.ret_1w_pct)}">${num(r.ret_1w_pct,1)}</td>
        <td class="num ${cls(r.ret_1m_pct)}">${num(r.ret_1m_pct,1)}</td>
        <td class="num">${num(r.volume_z,2)}</td>
        <td title="${esc(e.rule||"")}">${esc(e.date||"—")} <span class="muted tiny">(${esc(e.kind||"")})</span></td>
        <td>${r.stance.includes("RICH")?'<span class="badge warn">RICH</span>':r.stance.includes("CHEAP")?'<span class="badge ok">CHEAP</span>':'<span class="badge info">FAIR</span>'}${r.stance.includes("TRENDING")?' <span class="badge warn">TREND</span>':""}</td>
        <td class="tiny muted" style="white-space:normal;min-width:230px">${esc(r.play)}</td></tr>`}).join("");
    $$("#radarTable tbody tr").forEach(tr=>tr.onclick=()=>loadStudy(tr.dataset.inst));
    $("#buzzSymbol").innerHTML=d.rows.map(r=>`<option value="${esc(r.instrument)}">${esc(r.instrument)}</option>`).join("");
    $("#radarStatus").textContent=`scanned ${d.rows.length} instruments @ ${new Date(d.generated_at).toLocaleTimeString("en-IN")} — click any row for deep study`;
  }catch(e){$("#radarStatus").textContent="failed: "+e.message;}
};
async function loadStudy(inst){
  try{
    const s=await api(`/radar/study/${inst}`);
    $("#studyWrap").classList.remove("hidden");
    $("#studyTitle").textContent=`Study — ${s.instrument}`;
    $("#studyBody").innerHTML=[
      ["Current vol (YZ ann)",num(s.current_vol_pct,1)+"%"],
      ["Percentile vs 2y",num(s.percentile_2y,0)+"th"],
      ["Kind",s.kind],
      ["Session notes",esc(s.session_notes)],
      ...s.expiries.slice(0,4).map((e,i)=>[`Expiry ${i+1}`,`${e.date} <span class="muted tiny">(${e.kind})</span>`])]
      .map(r=>`<div class="ind-row"><span class="muted">${r[0]}</span><b class="mono small">${r[1]}</b></div>`).join("");
    regChart("cone",new Chart($("#coneChart"),{type:"bar",data:{
      labels:s.cone.map(c=>c.window_days+"d"),
      datasets:[{label:"p25",data:s.cone.map(c=>c.p25),backgroundColor:"rgba(34,197,94,.35)"},
        {label:"median",data:s.cone.map(c=>c.median),backgroundColor:"rgba(56,189,248,.55)"},
        {label:"p75",data:s.cone.map(c=>c.p75),backgroundColor:"rgba(167,139,250,.4)"},
        {label:"CURRENT",data:s.cone.map(c=>c.current),backgroundColor:"rgba(239,68,68,.85)"}]},
      options:{plugins:{legend:{labels:{color:"#7c8aa5"}}},
        scales:{x:{title:{display:true,text:"realized vol lookback",color:"#7c8aa5"},ticks:{color:"#7c8aa5"}},
          y:{title:{display:true,text:"annualized vol %",color:"#7c8aa5"},ticks:{color:"#7c8aa5"}}}}}));
    $("#studyWrap").scrollIntoView({behavior:"smooth"});
  }catch(e){toast("✗ "+e.message);}
}
$("#btnBuzz").onclick=async()=>{
  const sym=$("#buzzSymbol").value; if(!sym)return;
  try{
    const b=await api(`/radar/buzz/${sym}`);
    $("#buzzCard").classList.remove("hidden");
    const news=b.feeds.news.items||[], posts=b.feeds.reddit.posts||[];
    $("#buzzBody").innerHTML=
      `<div class="ind-row"><span class="muted">buzz score (mentions×news heuristic)</span>
       <b class="mono">${b.buzz_score}/100</b></div>
       <div class="muted small mb8">${esc(b.note||"")}</div>`
      + news.slice(0,6).map(n=>`<div class="news-item"><div class="nh">${esc(n.title)}</div>
          <div class="nm"><span>${esc(n.source)}</span><span class="badge info">NEWS</span></div></div>`).join("")
      + (b.feeds.reddit.status==="ok"
         ? posts.slice(0,6).map(p=>`<div class="news-item"><div class="nh">${esc(p.title)}</div>
             <div class="nm"><span>r/${esc(p.subreddit)}</span><span>▲${p.score} 💬${p.comments}</span>
             <span class="badge info">REDDIT</span></div></div>`).join("")
         : `<div class="news-item"><div class="nm">reddit: ${esc(b.feeds.reddit.status)}</div></div>`);
  }catch(e){toast("✗ "+e.message);}
};
async function buildLibrary(){
  const c=$("#libContainer");
  if(c.dataset.built){filterLibrary();return;}
  try{
    const d=await api("/formulas");
    c.innerHTML=Object.entries(d.registry).map(([cat,ids])=>`
      <div class="card lib-cat mt" data-cat="${esc(cat)}">
        <h3>${esc(d.categories[cat]||cat)}</h3>
        <div class="lib-chips">${ids.map(id=>`<span class="chip mono" data-f="${esc(id)}">ƒ ${esc(id)}</span>`).join("")}</div>
      </div>`).join("");
    $$(".chip",c).forEach(ch=>ch.onclick=()=>openFormula(ch.dataset.f,"RELIANCE"));
    c.dataset.built=1;
  }catch(e){c.innerHTML="<p class=neg>registry unavailable</p>";}
}
function filterLibrary(){ /* simple text filter hook */ }
$("#libSearch")?.addEventListener("input",e=>{
  const q=e.target.value.toLowerCase();
  $$(".chip").forEach(ch=>ch.style.display=ch.textContent.toLowerCase().includes(q)?"":"none");
});
