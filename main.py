import asyncio
import json
import os
import queue as q_module
import re
import shutil
import tempfile
import threading
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from ytmusicapi import YTMusic

app = FastAPI()
ytmusic = YTMusic()

SAVE_DIR = Path.home() / "Music" / "grab"
SAVE_DIR.mkdir(parents=True, exist_ok=True)


def sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()


def _search_raw(q: str, limit: int):
    try:
        return ytmusic.search(q, filter="songs", limit=limit)
    except Exception:
        return []


def _fmt(r):
    return {
        "videoId": r["videoId"],
        "title": r.get("title", "Unknown"),
        "artist": r["artists"][0]["name"] if r.get("artists") else "Unknown",
        "thumbnail": r["thumbnails"][-1]["url"] if r.get("thumbnails") else "",
    }



HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>grab</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0a0a;--surface:#141414;--surface2:#1c1c1c;--border:#252525;
  --accent:#c8f04a;--accent-dim:#8aaa28;--accent-glow:rgba(200,240,74,0.12);
  --text:#e2e2e2;--muted:#555;--muted2:#3a3a3a;--danger:#f04a4a;
}
html{scroll-behavior:smooth}
body{
  background:var(--bg);color:var(--text);
  font-family:"IBM Plex Sans",sans-serif;font-weight:300;
  min-height:100vh;display:flex;flex-direction:column;align-items:center;
  padding:52px 24px 80px;
}

/* ── HEADER ── */
header{width:100%;max-width:680px;margin-bottom:44px;display:flex;align-items:baseline;gap:14px}
h1{
  font-family:"IBM Plex Mono",monospace;font-size:1rem;font-weight:600;
  letter-spacing:0.1em;color:var(--accent);text-transform:uppercase;
}
.subtitle{font-family:"IBM Plex Mono",monospace;font-size:0.68rem;color:var(--muted);letter-spacing:0.04em}

/* ── SEARCH ── */
.search-wrap{width:100%;max-width:680px;position:relative;margin-bottom:36px}
.search-row{display:flex;gap:8px}
input#q{
  flex:1;background:var(--surface);border:1px solid var(--border);
  color:var(--text);font-family:"IBM Plex Mono",monospace;font-size:0.88rem;
  padding:13px 16px;outline:none;transition:border-color 0.2s,box-shadow 0.2s;
}
input#q::placeholder{color:var(--muted)}
input#q:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
button#searchBtn{
  background:var(--accent);color:#0a0a0a;border:none;
  font-family:"IBM Plex Mono",monospace;font-size:0.8rem;font-weight:600;
  letter-spacing:0.07em;padding:13px 22px;cursor:pointer;
  text-transform:uppercase;transition:background 0.15s,opacity 0.15s;white-space:nowrap;
}
button#searchBtn:hover{background:var(--accent-dim)}
button#searchBtn:disabled{opacity:0.4;cursor:default}

/* ── AUTOCOMPLETE ── */
#suggest-box{
  position:absolute;top:calc(100% + 4px);left:0;right:0;
  background:var(--surface2);border:1px solid var(--border);
  z-index:100;display:none;
}
.suggest-item{
  display:flex;align-items:center;gap:12px;padding:10px 14px;cursor:pointer;
  transition:background 0.1s;border-bottom:1px solid var(--muted2);
}
.suggest-item:last-child{border-bottom:none}
.suggest-item:hover{background:var(--accent-glow)}
.suggest-thumb{width:36px;height:36px;object-fit:cover;flex-shrink:0;background:var(--border)}
.suggest-text{min-width:0}
.suggest-title{font-family:"IBM Plex Mono",monospace;font-size:0.78rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.suggest-artist{font-size:0.72rem;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* ── RESULTS ── */
#results{width:100%;max-width:680px;display:flex;flex-direction:column;gap:1px}
.track{
  background:var(--surface);border-left:2px solid transparent;
  display:flex;align-items:center;gap:14px;padding:12px 14px;
  transition:border-color 0.15s,background 0.15s;
}
.track:hover{border-left-color:var(--accent);background:var(--surface2)}
.thumb{width:50px;height:50px;object-fit:cover;flex-shrink:0;background:var(--border)}
.track-info{flex:1;min-width:0}
.track-title{
  font-family:"IBM Plex Mono",monospace;font-size:0.82rem;font-weight:500;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.track-artist{font-size:0.75rem;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-saved{font-family:"IBM Plex Mono",monospace;font-size:0.62rem;color:var(--accent-dim);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* ── DOWNLOAD AREA ── */
.dl-area{flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:6px;min-width:90px}
button.dl-btn{
  background:transparent;border:1px solid var(--border);color:var(--accent);
  font-family:"IBM Plex Mono",monospace;font-size:0.72rem;letter-spacing:0.06em;
  padding:7px 12px;cursor:pointer;text-transform:uppercase;
  transition:all 0.15s;white-space:nowrap;width:100%;
}
button.dl-btn:hover{border-color:var(--accent);background:var(--accent-glow)}
button.dl-btn:disabled{cursor:default;opacity:0.5}
button.dl-btn.done{color:var(--accent-dim);border-color:var(--accent-dim)}
button.dl-btn.err{color:var(--danger);border-color:var(--danger)}

/* ── PROGRESS BAR ── */
.prog-wrap{width:100%;display:none;flex-direction:column;gap:4px}
.prog-wrap.active{display:flex}
.prog-bar-bg{
  width:100%;height:3px;background:var(--muted2);position:relative;overflow:hidden;
}
.prog-bar-fill{
  height:100%;background:var(--accent);width:0%;
  transition:width 0.3s ease;
}
.prog-bar-fill.converting{
  width:100%!important;
  background:repeating-linear-gradient(90deg,var(--accent) 0%,var(--accent-dim) 50%,var(--accent) 100%);
  background-size:200% 100%;
  animation:shimmer 1.2s linear infinite;
}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.prog-label{font-family:"IBM Plex Mono",monospace;font-size:0.6rem;color:var(--muted);text-align:right}

/* ── STATUS ── */
.status{
  font-family:"IBM Plex Mono",monospace;font-size:0.7rem;color:var(--muted);
  text-align:center;margin-top:28px;letter-spacing:0.04em;
}
</style>
</head>
<body>

<header>
  <h1>&#11015; grab</h1>
  <div class="subtitle">// personal music downloader</div>
</header>

<div class="search-wrap">
  <div class="search-row">
    <input type="text" id="q" placeholder="artist — title..." autocomplete="off" spellcheck="false"/>
    <button id="searchBtn" onclick="doSearch()">Search</button>
  </div>
  <div id="suggest-box"></div>
</div>

<div id="results"></div>
<div class="status" id="status"></div>

<script>
const $ = id => document.getElementById(id);
const input = $('q');
let suggestTimer = null;
const TRACKS = {};  // videoId -> track object, avoids JSON-in-onclick

// ── AUTOCOMPLETE ──
input.addEventListener('input', () => {
  clearTimeout(suggestTimer);
  const q = input.value.trim();
  if (q.length < 2) { hideSuggest(); return; }
  suggestTimer = setTimeout(() => fetchSuggest(q), 280);
});

input.addEventListener('keydown', e => {
  if (e.key === 'Enter') { hideSuggest(); doSearch(); }
  if (e.key === 'Escape') hideSuggest();
});

document.addEventListener('click', e => {
  if (!e.target.closest('.search-wrap')) hideSuggest();
});

async function fetchSuggest(q) {
  try {
    const res = await fetch('/suggest?q=' + encodeURIComponent(q));
    const tracks = await res.json();
    storeTracks(tracks);
    renderSuggest(tracks);
  } catch { hideSuggest(); }
}

function renderSuggest(tracks) {
  const box = $('suggest-box');
  if (!tracks.length) { hideSuggest(); return; }
  box.innerHTML = tracks.map(t => `
    <div class="suggest-item" onclick="pickSuggest('${t.videoId}')">
      <img class="suggest-thumb" src="${t.thumbnail}" onerror="this.style.visibility='hidden'"/>
      <div class="suggest-text">
        <div class="suggest-title">${esc(t.title)}</div>
        <div class="suggest-artist">${esc(t.artist)}</div>
      </div>
    </div>`).join('');
  box.style.display = 'block';
}

function hideSuggest() { $('suggest-box').style.display = 'none'; }

function pickSuggest(videoId) {
  const track = TRACKS[videoId];
  hideSuggest();
  input.value = track.title + ' ' + track.artist;
  renderResults([track]);
}

// ── SEARCH ──
async function doSearch() {
  const q = input.value.trim();
  if (!q) return;
  hideSuggest();
  const btn = $('searchBtn');
  btn.disabled = true; btn.textContent = '...';
  $('results').innerHTML = ''; $('status').textContent = 'searching...';
  try {
    const res = await fetch('/search?q=' + encodeURIComponent(q));
    const tracks = await res.json();
    if (!tracks.length) { $('status').textContent = 'no results.'; return; }
    $('status').textContent = '';
    storeTracks(tracks);
    renderResults(tracks);
  } catch(e) {
    $('status').textContent = 'error: ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Search';
  }
}

function storeTracks(tracks) {
  tracks.forEach(t => TRACKS[t.videoId] = t);
}

function renderResults(tracks) {
  $('results').innerHTML = tracks.map(t => `
    <div class="track">
      <img class="thumb" src="${t.thumbnail}" loading="lazy" onerror="this.style.visibility='hidden'"/>
      <div class="track-info">
        <div class="track-title">${esc(t.title)}</div>
        <div class="track-artist">${esc(t.artist)}</div>
        <div class="track-saved" id="saved-${t.videoId}"></div>
      </div>
      <div class="dl-area" id="area-${t.videoId}">
        <select class="br-sel" id="br-${t.videoId}">
          <option value="128">128 kbps</option>
          <option value="192" selected>192 kbps</option>
          <option value="256">256 kbps</option>
          <option value="320">320 kbps</option>
        </select>
        <button class="dl-btn" onclick="startDl('${t.videoId}', this)">&#8659; mp3</button>
        <div class="prog-wrap" id="prog-${t.videoId}">
          <div class="prog-bar-bg"><div class="prog-bar-fill" id="fill-${t.videoId}"></div></div>
          <div class="prog-label" id="label-${t.videoId}">0%</div>
        </div>
      </div>
    </div>`).join('');
}

// ── DOWNLOAD ──
async function startDl(videoId, btn) {
  const track = TRACKS[videoId];
  const { title, artist } = track;
  const filename = (artist ? artist + ' - ' : '') + title + '.mp3';

  let savePath = '';
  if (window.pywebview) {
    savePath = await window.pywebview.api.choose_path(filename);
    if (!savePath) return;
  }

  btn.disabled = true; btn.textContent = 'starting...';
  const prog  = $('prog-'  + videoId);
  const fill  = $('fill-'  + videoId);
  const label = $('label-' + videoId);
  const saved = $('saved-' + videoId);
  prog.classList.add('active');

  const bitrate = $('br-' + videoId).value;
  const url = '/download?videoId=' + videoId
    + '&title='    + encodeURIComponent(title)
    + '&artist='   + encodeURIComponent(artist)
    + '&savePath=' + encodeURIComponent(savePath)
    + '&bitrate='  + bitrate;

  const es = new EventSource(url);

  es.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.type === 'progress') {
      fill.classList.remove('converting');
      fill.style.width = d.pct + '%';
      label.textContent = d.pct + '%';
      btn.textContent = d.pct + '%';
    } else if (d.type === 'converting') {
      fill.classList.add('converting');
      label.textContent = 'converting...';
      btn.textContent = 'converting...';
    } else if (d.type === 'done') {
      fill.classList.remove('converting');
      fill.style.width = '100%';
      label.textContent = '100%';
      btn.className = 'dl-btn done'; btn.textContent = '\u2713 saved'; btn.disabled = false;
      saved.textContent = d.path;
      es.close();
    } else if (d.type === 'error') {
      btn.className = 'dl-btn err'; btn.textContent = 'error'; btn.disabled = false;
      saved.textContent = d.msg;
      prog.classList.remove('active');
      es.close();
    }
  };

  es.onerror = () => {
    btn.className = 'dl-btn err'; btn.textContent = 'error'; btn.disabled = false;
    es.close();
  };
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/suggest")
def suggest(q: str):
    if len(q) < 2:
        return []
    raw = _search_raw(q, 5)
    return [_fmt(r) for r in raw if r.get("videoId")]


@app.get("/search")
def search(q: str):
    raw = _search_raw(q, 12)
    if not raw:
        raise HTTPException(status_code=500, detail="Search failed")
    return [_fmt(r) for r in raw if r.get("videoId")]


@app.get("/download")
async def download(videoId: str, title: str = "song", artist: str = "", savePath: str = "", bitrate: str = "192"):
    if savePath:
        out_path = Path(savePath)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        safe_name = sanitize(f"{artist} - {title}" if artist else title)
        out_path = SAVE_DIR / f"{safe_name}.mp3"

    progress_q: q_module.Queue = q_module.Queue()
    tmpdir = tempfile.mkdtemp()
    tmp_out = os.path.join(tmpdir, "audio.%(ext)s")

    def progress_hook(d):
        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            pct = int(downloaded / total * 100) if total > 0 else 0
            progress_q.put({"type": "progress", "pct": pct})
        elif d["status"] == "finished":
            progress_q.put({"type": "converting"})

    def run():
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate,
            }],
            "outtmpl": tmp_out,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={videoId}"])
            tmp_mp3 = os.path.join(tmpdir, "audio.mp3")
            if os.path.exists(tmp_mp3):
                shutil.move(tmp_mp3, out_path)
                progress_q.put({"type": "done", "path": str(out_path)})
            else:
                progress_q.put({"type": "error", "msg": "Conversion failed — check ffmpeg."})
        except Exception as e:
            progress_q.put({"type": "error", "msg": str(e)})
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    threading.Thread(target=run, daemon=True).start()

    async def stream():
        loop = asyncio.get_event_loop()
        while True:
            try:
                msg = await loop.run_in_executor(
                    None, lambda: progress_q.get(timeout=120)
                )
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("done", "error"):
                    break
            except Exception:
                yield f"data: {json.dumps({'type': 'error', 'msg': 'timeout'})}\n\n"
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
