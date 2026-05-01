# grab — Android Port Specification

Complete technical reference for porting the `grab` desktop music downloader to Android. The backend is unchanged — this document covers what the backend exposes, how the current frontend consumes it, and how to replicate that in an Android client.

---

## 1. Backend Overview

The backend is a **FastAPI** server (`main.py`) that handles all heavy lifting: search, audio resolution, ffmpeg conversion. The Android app is a pure client — it calls the API and handles file saving natively.

The server can be run:
- Locally on a PC, accessed via LAN IP
- On a small VPS (Railway, Render, Hetzner), accessed from anywhere

When deploying for Android access, bind uvicorn to `0.0.0.0` and expose port `8765`.

---

## 2. API Reference

### `GET /search`

Search YouTube Music for songs.

**Query params:**
| Param | Type | Description |
|---|---|---|
| `q` | string | Search query, e.g. `michael jackson billie jean` |

**Response:** `application/json` — array of track objects

```json
[
  {
    "videoId": "Zi_XLOBDo_Y",
    "title": "Billie Jean",
    "artist": "Michael Jackson",
    "thumbnail": "https://lh3.googleusercontent.com/..."
  }
]
```

- Returns up to 12 results
- `videoId` is a YouTube video ID — used as the identifier for all subsequent calls
- `thumbnail` is a direct image URL, high resolution

---

### `GET /suggest`

Lightweight autocomplete — same shape as `/search` but faster, fewer results.

**Query params:**
| Param | Type | Description |
|---|---|---|
| `q` | string | Partial query (min 2 chars) |

**Response:** same schema as `/search`, max 5 results

Used to power the search bar dropdown as the user types. Fire with ~300ms debounce.

---

### `GET /download`

Downloads and converts the audio to MP3, streams progress as Server-Sent Events.

**Query params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `videoId` | string | required | YouTube video ID |
| `title` | string | `"song"` | Track title (used for filename) |
| `artist` | string | `""` | Artist name (used for filename) |
| `savePath` | string | `""` | Absolute local path to save to. Empty = save to `~/Music/grab/` |
| `bitrate` | string | `"192"` | MP3 quality: `128`, `192`, `256`, or `320` |

**Response:** `text/event-stream` (SSE)

The connection stays open during the entire download + conversion. Events are newline-delimited JSON:

```
data: {"type": "progress", "pct": 42}\n\n
data: {"type": "progress", "pct": 87}\n\n
data: {"type": "converting"}\n\n
data: {"type": "done", "path": "C:\\Users\\...\\Music\\grab\\Michael Jackson - Billie Jean.mp3"}\n\n
```

**Event types:**

| Type | Payload | Meaning |
|---|---|---|
| `progress` | `pct: int (0–100)` | Download progress percentage |
| `converting` | — | yt-dlp finished downloading, ffmpeg is now re-encoding |
| `done` | `path: string` | File saved successfully, absolute path on server |
| `error` | `msg: string` | Something failed |

**Notes:**
- `converting` has no percentage — it is indeterminate. Show a shimmer/pulse animation.
- `done.path` is the server-side path. On a remote server this is useless to the client — see section 5.
- The connection closes naturally after `done` or `error`. Always close your SSE client on these events.

---

## 3. Current Frontend Logic (Desktop)

Documented here as reference for replicating in Android.

### Search flow

```
user types → debounce 280ms → GET /suggest?q=... → render dropdown
user presses Enter / taps Search → GET /search?q=... → render results list
user taps suggestion → populate search field + render that one result directly
```

### Download flow

```
user taps ↓ mp3 →
  open native save dialog (pre-filled: "Artist - Title.mp3") →
  if cancelled: abort →
  open SSE connection to GET /download?videoId=...&savePath=...&bitrate=... →
  on progress event: update progress bar (0–100%) →
  on converting event: show indeterminate animation →
  on done event: show saved path, close SSE →
  on error event: show error, close SSE
```

### Track store pattern

Tracks are stored in a `Map<videoId, TrackObject>` in memory as they are fetched. This avoids passing complex objects through UI callbacks — only the `videoId` string is passed around, the full object is looked up when needed.

In Android: store tracks in a `ViewModel` as a `Map<String, Track>`.

---

## 4. Data Models

### Track

```kotlin
data class Track(
    val videoId: String,
    val title: String,
    val artist: String,
    val thumbnail: String  // URL
)
```

### DownloadEvent (SSE)

```kotlin
sealed class DownloadEvent {
    data class Progress(val pct: Int) : DownloadEvent()
    object Converting : DownloadEvent()
    data class Done(val path: String?) : DownloadEvent()
    data class Error(val msg: String) : DownloadEvent()
}
```

---

## 5. Android-Specific Considerations

### File saving

On Android, `savePath` sent to the server is irrelevant — the server saves to its own filesystem. The Android client needs the file streamed back.

**Required backend change for Android:** Add a `/serve/<token>` endpoint (already prototyped during development):

```
download flow (Android):
  SSE: on done event → receive token instead of path
  GET /serve/<token> → stream MP3 bytes
  save to Android MediaStore (Music collection)
```

Backend change: when `savePath` is empty, save to a temp file, issue a UUID token, return `{"type": "done", "token": "uuid"}`. Token expires after one download.

### SSE on Android

Use **OkHttp** with a custom SSE listener or the `okhttp-sse` extension. Do not use `java.net.HttpURLConnection` for SSE — it buffers.

```kotlin
val request = Request.Builder().url("$BASE_URL/download?videoId=$id&bitrate=$bitrate").build()
val listener = object : EventSourceListener() {
    override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
        val event = parseEvent(data)  // deserialize JSON
        // post to ViewModel StateFlow
    }
}
EventSources.createFactory(okHttpClient).newEventSource(request, listener)
```

### Thumbnail loading

Use **Coil** (`io.coil-kt:coil-compose`) — direct URL loading, no config needed.

```kotlin
AsyncImage(
    model = track.thumbnail,
    contentDescription = null,
    modifier = Modifier.size(52.dp)
)
```

### Recommended stack

| Concern | Library |
|---|---|
| HTTP + SSE | OkHttp + `com.launchdarkly:okhttp-eventsource` |
| JSON | Kotlin Serialization (`kotlinx.serialization`) |
| Image loading | Coil |
| UI | Jetpack Compose |
| State | ViewModel + StateFlow |
| File saving | MediaStore API (Music collection) |
| Navigation | None needed — single screen app |

---

## 6. UI Specification

### Screen layout (single screen)

```
┌─────────────────────────────────┐
│  ⬇ GRAB  // personal music...  │  ← header
├─────────────────────────────────┤
│  [──────── search ────────][GO] │  ← search bar
│  ┌ suggestion dropdown ───────┐ │
│  │ thumb  Title / Artist      │ │
│  └────────────────────────────┘ │
├─────────────────────────────────┤
│  ┌─────────────────────────────┐│
│  │ [img] Title        [▼ MP3] ││  ← result card
│  │       Artist  [192kbps ▾]  ││
│  │       ████████░░░  67%     ││  ← progress bar
│  │       ✓ saved              ││
│  └─────────────────────────────┘│
└─────────────────────────────────┘
```

### Color tokens

```kotlin
object GrabColors {
    val Background  = Color(0xFF0A0A0A)
    val Surface     = Color(0xFF141414)
    val Surface2    = Color(0xFF1C1C1C)
    val Border      = Color(0xFF252525)
    val Accent      = Color(0xFFC8F04A)
    val AccentDim   = Color(0xFF8AAA28)
    val TextPrimary = Color(0xFFE2E2E2)
    val TextMuted   = Color(0xFF555555)
    val Danger      = Color(0xFFF04A4A)
}
```

### Typography

- **Primary font**: IBM Plex Mono (monospace) — titles, labels, buttons
- **Secondary font**: IBM Plex Sans Light — artist names, subtitles
- Both available on Google Fonts, loadable via `androidx.compose.ui:ui-text-google-fonts`

### Key UI behaviors

- Search bar: debounce suggestions at 280ms, clear suggestions on search or Escape
- Download button: disabled during active download, shows percentage as text while in progress
- Progress bar: smooth animated fill 0→100%, shimmer animation during `converting` phase
- Per-track bitrate selector: compact dropdown (128 / 192 / 256 / 320), default 192
- Track store: results persist in ViewModel across recompositions

---

## 7. Base URL Configuration

Hardcode or expose via a settings screen:

```kotlin
// BuildConfig or a simple preferences key
const val BASE_URL = "http://192.168.1.X:8765"  // LAN
// or
const val BASE_URL = "https://your-vps.example.com"  // remote
```

Consider a first-launch screen asking for the server URL if you want portability.

---

## 8. Permissions

```xml
<!-- AndroidManifest.xml -->
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE"
    android:maxSdkVersion="28" />
```

On API 29+, use `MediaStore.Audio.Media` to save files — no storage permission needed.

---

## 9. What Does NOT Change

- `main.py` — entirely unchanged
- `run.py` — entirely unchanged (desktop only)
- Search, suggest, and SSE progress logic — identical, just consumed by Kotlin instead of JS
- The one backend addition needed: `/serve/<token>` endpoint for streaming the file back to the client instead of saving to a local path
