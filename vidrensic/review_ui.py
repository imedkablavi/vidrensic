from __future__ import annotations


REVIEW_WORKSTATION_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vidrensic Review Workstation</title>
<style>
:root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; background:#0b0f14; color:#e6edf3; }
* { box-sizing:border-box; }
body { margin:0; min-height:100vh; background:#0b0f14; }
button, input, textarea, select { font:inherit; }
button { border:1px solid #303844; background:#161d26; color:#e6edf3; border-radius:7px; padding:7px 10px; cursor:pointer; }
button:hover { background:#202938; }
button.active { border-color:#6ea8fe; box-shadow:0 0 0 1px #6ea8fe inset; }
button.keep { border-color:#3fb950; }
button.discard { border-color:#f85149; }
input, textarea, select { width:100%; background:#0f141b; color:#e6edf3; border:1px solid #303844; border-radius:7px; padding:8px; }
textarea { min-height:110px; resize:vertical; }
.shell { display:grid; grid-template-columns:minmax(250px, 330px) 1fr; min-height:100vh; }
.sidebar { border-right:1px solid #242b34; padding:14px; background:#0e131a; overflow:auto; }
.main { padding:14px; min-width:0; }
.header { display:flex; gap:10px; align-items:center; margin-bottom:12px; flex-wrap:wrap; }
.header h1 { font-size:17px; margin:0; margin-right:auto; }
.pill { border:1px solid #303844; border-radius:999px; padding:4px 8px; font-size:12px; }
.status { font-size:12px; color:#9da7b3; min-height:18px; }
.filters { display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; margin:10px 0; }
.items { display:flex; flex-direction:column; gap:7px; }
.item { border:1px solid #242b34; border-radius:8px; padding:9px; text-align:left; background:#111821; }
.item.selected { border-color:#6ea8fe; }
.item.changed { border-color:#f85149; }
.item-title { font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.item-meta { display:flex; gap:7px; margin-top:6px; font-size:11px; color:#8b949e; }
.state { font-weight:700; }
.state-KEEP { color:#3fb950; } .state-DISCARD { color:#f85149; } .state-REVIEW { color:#d29922; }
.player-panel { position:sticky; top:14px; z-index:2; background:#0e131a; border:1px solid #242b34; border-radius:10px; padding:10px; }
video { width:100%; max-height:58vh; background:#000; border-radius:7px; display:block; }
.info-row { display:grid; grid-template-columns:1fr auto; gap:10px; align-items:center; margin-top:8px; }
.controls { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.timeline { margin-top:10px; }
.track { position:relative; height:28px; border:1px solid #303844; background:#10161e; border-radius:6px; overflow:hidden; cursor:pointer; }
.fill { position:absolute; inset:0 auto 0 0; width:0; background:#26364d; }
.marker { position:absolute; top:0; bottom:0; width:2px; background:#d29922; pointer-events:none; }
.marker.bookmark { background:#58a6ff; width:3px; }
.legend { display:flex; gap:12px; font-size:11px; color:#8b949e; margin-top:6px; }
.detail { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px; }
.card { border:1px solid #242b34; border-radius:10px; padding:11px; background:#0e131a; }
.card h2 { font-size:13px; margin:0 0 8px; }
.buttons { display:flex; gap:6px; flex-wrap:wrap; }
.bookmarks { display:flex; flex-direction:column; gap:5px; max-height:180px; overflow:auto; }
.bookmark { display:flex; gap:7px; align-items:center; border-bottom:1px solid #1e252e; padding:6px 0; }
.bookmark button { margin-left:auto; }
.small { font-size:11px; color:#8b949e; }
.qc { display:flex; gap:6px; flex-wrap:wrap; }
.qc .pill.bad { border-color:#f85149; color:#ff7b72; }
.qc .pill.warn { border-color:#d29922; color:#e3b341; }
.qc .pill.ok { border-color:#3fb950; color:#56d364; }
.empty { padding:20px 4px; color:#8b949e; font-size:13px; text-align:center; }
@media (max-width:900px) { .shell{grid-template-columns:1fr;} .sidebar{border-right:0;border-bottom:1px solid #242b34; max-height:40vh;} .detail{grid-template-columns:1fr;} }
</style>
</head>
<body>
<div class="shell">
<aside class="sidebar">
  <div class="header"><h1>Vidrensic Review</h1><span id="count" class="pill">0</span></div>
  <input id="search" placeholder="Search artifact / note">
  <div class="filters">
    <button data-filter="ALL" class="filter active">All</button>
    <button data-filter="REVIEW" class="filter">Review</button>
    <button data-filter="KEEP" class="filter">Keep</button>
  </div>
  <div class="filters">
    <button data-filter="DISCARD" class="filter">Discard</button>
    <button id="refresh">Refresh</button>
    <button id="clear-search">Clear</button>
  </div>
  <div id="items" class="items"></div>
</aside>
<main class="main">
  <div class="header">
    <h1 id="artifact-title">Select a review item</h1>
    <span id="state-pill" class="pill state-REVIEW">REVIEW</span>
    <span id="hash-pill" class="pill">SHA-256: —</span>
  </div>
  <div id="status" class="status"></div>

  <section class="player-panel">
    <video id="player" controls preload="metadata"></video>
    <div class="info-row">
      <div class="small" id="time-readout">00:00 / —</div>
      <div class="qc" id="qc"></div>
    </div>
    <div class="controls">
      <button data-jump="-30">−30s</button><button data-jump="-5">−5s</button><button data-jump="-1">−1s</button>
      <button id="step-back">Frame −</button><button id="step-forward">Frame +</button>
      <button data-jump="1">+1s</button><button data-jump="5">+5s</button><button data-jump="30">+30s</button>
      <button data-speed="0.25">0.25×</button><button data-speed="0.5">0.5×</button><button data-speed="1" class="speed active">1×</button>
      <button data-speed="2">2×</button><button data-speed="5">5×</button><button data-speed="8">8×</button>
    </div>
    <div class="timeline">
      <div id="track" class="track"><div id="fill" class="fill"></div><div id="markers"></div></div>
      <div class="legend"><span>orange = timing anomaly</span><span>blue = bookmark</span></div>
    </div>
  </section>

  <section class="detail">
    <div class="card">
      <h2>Review decision</h2>
      <div class="buttons">
        <button id="keep" class="keep">KEEP</button>
        <button id="review">REVIEW</button>
        <button id="discard" class="discard">DISCARD</button>
      </div>
      <div style="margin-top:9px"><textarea id="note" placeholder="Analyst note"></textarea></div>
      <div class="buttons" style="margin-top:7px"><button id="save-note">Save note</button></div>
    </div>
    <div class="card">
      <h2>Bookmarks</h2>
      <div class="buttons">
        <input id="bookmark-label" placeholder="Label" style="flex:1 1 140px">
        <button id="add-bookmark">Bookmark current frame</button>
      </div>
      <div id="bookmarks" class="bookmarks" style="margin-top:8px"></div>
    </div>
  </section>
</main>
</div>
<script>
const state = { items: [], filter: 'ALL', selected: null, detail: null, timeline: null };
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setStatus(message) { $('status').textContent = message || ''; }
function fmtTime(value) { if (!Number.isFinite(value)) return '—'; value=Math.max(0,Math.round(value)); const h=Math.floor(value/3600),m=Math.floor((value%3600)/60),s=value%60; return h ? `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; }
async function api(path, options={}) { const response = await fetch(path, options); const data = await response.json().catch(()=>({error:'invalid response'})); if(!response.ok) throw new Error(data.error || `HTTP ${response.status}`); return data; }
async function loadItems() { const query = state.filter==='ALL' ? '' : `?state=${encodeURIComponent(state.filter)}`; state.items = (await api(`/api/items${query}`)).items || []; renderItems(); $('count').textContent=state.items.length; if(state.selected) { const still=state.items.find(x=>x.item_id===state.selected); if(still) await selectItem(still.item_id); } }
function renderItems() { const search=$('search').value.trim().toLowerCase(); const filtered=state.items.filter(item => !search || `${item.artifact} ${item.note}`.toLowerCase().includes(search)); if(!filtered.length){$('items').innerHTML='<div class="empty">No review items</div>'; return;} $('items').innerHTML=filtered.map(item=>`<button class="item ${item.item_id===state.selected?'selected':''} ${item.artifact_changed?'changed':''}" data-item="${esc(item.item_id)}"><div class="item-title">${esc(item.artifact.split('/').pop())}</div><div class="item-meta"><span class="state state-${item.state}">${esc(item.state)}</span><span>${fmtTime(item.duration_seconds)}</span><span>${item.bookmark_count||0} marks</span></div></button>`).join(''); document.querySelectorAll('[data-item]').forEach(btn=>btn.onclick=()=>selectItem(btn.dataset.item)); }
async function selectItem(itemId) { state.selected=itemId; renderItems(); setStatus('Loading artifact…'); try { const detail=await api(`/api/item/${encodeURIComponent(itemId)}`); state.detail=detail; $('artifact-title').textContent=detail.artifact.split('/').pop(); $('hash-pill').textContent=`SHA-256: ${detail.artifact_sha256.slice(0,16)}…`; $('state-pill').textContent=detail.state; $('state-pill').className=`pill state-${detail.state}`; $('note').value=detail.note || ''; $('player').src=`/media/${encodeURIComponent(itemId)}`; renderBookmarks(detail.bookmarks || []); await loadTimeline(itemId); setStatus(detail.artifact_changed ? 'WARNING: artifact changed after registration.' : 'Ready'); } catch(error){ setStatus(error.message); } }
async function loadTimeline(itemId) { state.timeline=null; $('qc').innerHTML=''; renderMarkers(); try { const data=await api(`/api/timeline/${encodeURIComponent(itemId)}`); state.timeline=data; const t=data.timeline||{}; $('qc').innerHTML=`<span class="pill ${t.duration_confidence==='High'?'ok':'warn'}">Duration ${esc(t.duration_confidence||'—')}</span><span class="pill ${t.frame_rate_confidence==='High'?'ok':'warn'}">FPS ${esc(t.frame_rate_confidence||'—')}</span><span class="pill ${t.truncated?'bad':'ok'}">${t.truncated?'Truncated':'Complete'}</span>`; renderMarkers(); } catch(error) { setStatus(error.message.includes('no timeline report') ? 'Timeline report not available; player/review state still usable.' : `Timeline: ${error.message}`); } }
function renderBookmarks(bookmarks) { $('bookmarks').innerHTML=bookmarks.length ? bookmarks.map(b=>`<div class="bookmark"><span>${fmtTime(b.timestamp_seconds)}</span><span>${esc(b.label||'Bookmark')}</span><span class="small">${esc(b.note||'')}</span><button data-bookmark-time="${b.timestamp_seconds}">Go</button></div>`).join('') : '<div class="small">No bookmarks yet</div>'; document.querySelectorAll('[data-bookmark-time]').forEach(btn=>btn.onclick=()=>seek(Number(btn.dataset.bookmarkTime))); renderMarkers(); }
function renderMarkers() { const markers=$('markers'); markers.innerHTML=''; const duration=Number($('player').duration)||Number(state.detail?.duration_seconds)||0; if(!duration) return; for(const b of (state.detail?.bookmarks||[])){ const el=document.createElement('div'); el.className='marker bookmark'; el.style.left=`${Math.min(100,(b.timestamp_seconds/duration)*100)}%`; el.title=b.label||'Bookmark'; markers.appendChild(el); } for(const anomaly of (state.timeline?.timeline?.anomalies||[])){ const t=Number(anomaly.current ?? anomaly.previous ?? 0); const el=document.createElement('div'); el.className='marker'; el.style.left=`${Math.min(100,Math.max(0,(t/duration)*100))}%`; el.title=anomaly.kind||'Timing anomaly'; markers.appendChild(el); } }
function seek(seconds) { const video=$('player'); if(Number.isFinite(video.duration)) video.currentTime=Math.max(0,Math.min(video.duration,seconds)); }
async function mutate(path, body) { if(!state.detail) return; try { const updated=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); return updated; } catch(error){setStatus(error.message); throw error;} }
async function setReviewState(next){ if(!state.detail) return; const item=await mutate(`/api/item/${state.detail.item_id}/state`,{state:next,sha256:state.detail.artifact_sha256}); state.detail={...state.detail,...item}; $('state-pill').textContent=next; $('state-pill').className=`pill state-${next}`; await loadItems(); setStatus(`State updated to ${next}`); }
$('player').addEventListener('loadedmetadata',()=>{ renderMarkers(); updateReadout(); });
$('player').addEventListener('timeupdate',updateReadout);
function updateReadout(){ const v=$('player'); const duration=Number.isFinite(v.duration)?v.duration:Number(state.detail?.duration_seconds)||NaN; $('time-readout').textContent=`${fmtTime(v.currentTime)} / ${fmtTime(duration)}`; $('fill').style.width=duration>0?`${(v.currentTime/duration)*100}%`:'0%'; }
document.querySelectorAll('[data-jump]').forEach(btn=>btn.onclick=()=>seek(($('player').currentTime||0)+Number(btn.dataset.jump)));
document.querySelectorAll('[data-speed]').forEach(btn=>btn.onclick=()=>{ $('player').playbackRate=Number(btn.dataset.speed); document.querySelectorAll('[data-speed]').forEach(b=>b.classList.toggle('active',b===btn)); });
$('step-back').onclick=()=>seek(($('player').currentTime||0)-1/30); $('step-forward').onclick=()=>seek(($('player').currentTime||0)+1/30);
$('track').onclick=event=>{ const rect=$('track').getBoundingClientRect(); const ratio=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)); const duration=Number($('player').duration)||Number(state.detail?.duration_seconds)||0; if(duration) seek(duration*ratio); };
$('keep').onclick=()=>setReviewState('KEEP'); $('review').onclick=()=>setReviewState('REVIEW'); $('discard').onclick=()=>setReviewState('DISCARD');
$('save-note').onclick=async()=>{ if(!state.detail)return; const item=await mutate(`/api/item/${state.detail.item_id}/note`,{note:$('note').value,sha256:state.detail.artifact_sha256}); state.detail={...state.detail,...item}; await loadItems(); setStatus('Note saved'); };
$('add-bookmark').onclick=async()=>{ if(!state.detail)return; const bookmark=await mutate(`/api/item/${state.detail.item_id}/bookmark`,{timestamp_seconds:$('player').currentTime||0,label:$('bookmark-label').value,note:$('note').value.slice(0,512),sha256:state.detail.artifact_sha256}); state.detail.bookmarks=[...(state.detail.bookmarks||[]),bookmark].sort((a,b)=>a.timestamp_seconds-b.timestamp_seconds); $('bookmark-label').value=''; renderBookmarks(state.detail.bookmarks); setStatus('Bookmark created'); };
document.querySelectorAll('.filter').forEach(btn=>btn.onclick=async()=>{ document.querySelectorAll('.filter').forEach(b=>b.classList.toggle('active',b===btn)); state.filter=btn.dataset.filter; await loadItems(); });
$('search').oninput=renderItems; $('refresh').onclick=loadItems; $('clear-search').onclick=()=>{ $('search').value=''; renderItems(); };
loadItems().catch(error=>setStatus(error.message));
</script>
</body>
</html>
'''
