const $=s=>document.querySelector(s);
let latest=null;
const fmt=(v)=>Number(v).toLocaleString(undefined,{maximumFractionDigits:2});
async function getJSON(url){let r=await fetch(url);let j=await r.json();if(!r.ok)throw Error(j.detail||r.statusText);return j}
async function loadRun(){
 $("#status").textContent="Fetching latest detector run…";
 try{
  latest=await getJSON("/api/latest-run");
  if(!latest||!latest.events) throw Error("No detector run is available yet. Run the detector in the main Test Lab first.");
  const all=Object.values(latest.events).flat();
  const countries=[...new Set(all.map(e=>e.country).filter(Boolean))].sort();
  const products=[...new Set(all.map(e=>e.product_id).filter(Boolean))].sort();
  $("#country").innerHTML='<option value="ALL">All countries</option>'+countries.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join("");
  $("#product").innerHTML='<option value="ALL">All products</option>'+products.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join("");
  $("#status").textContent=`Loaded run ${latest.id||"latest"} · dataset: ${latest.dataset||"active dataset"} · events available`;
  render();
 }catch(e){$("#status").innerHTML=`<span class="error">${esc(e.message)}</span>`;$("#rows").innerHTML='<tr><td colspan="11" class="empty">Run detector in the main Test Lab, then load again.</td></tr>';}
}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function render(){
 if(!latest)return;
 const mode=$("#mode").value,country=$("#country").value,product=$("#product").value;
 const q=Number($("#quantity").value),d=Number($("#duration").value);
 if(!Number.isFinite(q)||q<0||!Number.isFinite(d)||d<1){$("#status").textContent="Quantity must be ≥0 and duration ≥1 day.";return}
 const ev=(latest.events?.[mode]||[]).filter(e=>(country==="ALL"||e.country===country)&&(product==="ALL"||e.product_id===product));
 const calc=ev.map(e=>{const delta=Number(e.reset_price)-Number(e.previous_price);return {...e,delta,estimate:delta*q*d}});
 const net=calc.reduce((s,e)=>s+e.estimate,0),ups=calc.filter(e=>e.delta>0),downs=calc.filter(e=>e.delta<0),grossUp=ups.reduce((s,e)=>s+e.estimate,0),grossDown=downs.reduce((s,e)=>s+e.estimate,0);
 $("#summary").innerHTML=`<div class="stat"><span>Episodes included</span><strong>${calc.length}</strong></div><div class="stat"><span>Upward resets</span><strong>${ups.length}</strong></div><div class="stat"><span>Downward resets</span><strong>${downs.length}</strong></div><div class="stat"><span>Net estimated spend impact</span><strong>${fmt(net)}</strong></div>`;
 $("#rows").innerHTML=calc.map(e=>`<tr><td>${esc(e.event_date)}</td><td>${esc(e.country)}</td><td>${esc(e.product_id)}</td><td>${esc(e.direction)}</td><td>${fmt(e.previous_price)}</td><td>${fmt(e.reset_price)}</td><td>${fmt(e.delta)}</td><td>${fmt(e.pct_change)}%</td><td>${d}</td><td>${fmt(q)}</td><td>${fmt(e.estimate)}</td></tr>`).join("")||'<tr><td colspan="11" class="empty">No events in this filter. Run detector or change filters.</td></tr>';
}
$("#reload").addEventListener("click",loadRun);$("#apply").addEventListener("click",render);$("#mode").addEventListener("change",render);loadRun();
