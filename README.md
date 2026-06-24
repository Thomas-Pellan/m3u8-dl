# m3u8-dl

Captures HLS streams (m3u8 + TS segments) from websites and assembles them into local MP4 files.

Uses [camoufox](https://github.com/daijro/camoufox) to spoof a real Firefox fingerprint and bypass bot-protection, with Playwright response interception to detect and save video segments.

---

## About AI

This project is made with Claude Code for personal use. As its manager, I'm still taking the credit for its work though.

Not all cases are tested. Worked for my use case. You wouldn't steal a car? *Then don't use this to steal copyrighted content* (or do it, I'm not your dad).

---

## Quick start (Docker)

```bash
docker compose up --build
```

Then open [http://localhost:3000](http://localhost:3000).

Downloaded `.mp4` files land in `~/Downloads/` (override with `M3U8DL_OUTPUT_DIR`).

---

## Features

### Simple tab
Queue a download by pasting an m3u8 URL or a page URL. The backend runs camoufox headless, intercepts the playlist, downloads all segments in parallel and assembles the final MP4. Supports scheduling.

### Captured tab (manual browser control)
Opens a full camoufox session in a virtual display (Xvfb). A live screenshot stream lets you navigate the site manually — click, scroll, go back, navigate to a URL. HLS playlists intercepted by the browser appear as candidates below the viewer. Pick one, give it a name, and start the download.

### Sessions tab
Lists all past and active browser sessions and their downloads. For each completed download you can confirm whether it was correct:

- **✓ OK** — marks the CDN as trusted (keeps it in the website's known-CDN list)
- **✗ Wrong** — removes the CDN from the known list, with an option to delete the output file

### Websites tab
Records every site you've downloaded from, across both Simple and Captured modes. Per website:

- **Star rating** (1–5)
- **Works / Broken** toggle — the "Flush broken" button removes all broken entries at once
- **CDN count** — number of trusted CDN origins learned from past downloads; "flush" resets them
- **Captured mode →** — opens a new Captured session for that URL (or defers close if one is already running)

### CDN learning
When a Captured download starts, the CDN origin (scheme + host of the playlist URL) is stored and associated with the website. In subsequent Captured sessions for the same site, candidates whose CDN matches a known one are **highlighted in green** — making it easy to pick the right stream again.

---

## Requirements

- Docker + Docker Compose (recommended)
- Or: Python 3.12+, ffmpeg, Node 20+ (manual setup)

---

## Docker setup

```bash
docker compose up --build
```

| Variable | Default | Description |
|---|---|---|
| `M3U8DL_OUTPUT_DIR` | `~/Downloads` | Host directory for `.mp4` output |
| `M3U8DL_PORT` | `3000` | Host port for the web UI |
| `UID` / `GID` | `1000` | Run the backend as this user |

Persistent data (browser profile, SQLite DB) is stored in the `m3u8dl-data` Docker volume.

---

## Manual setup

### Backend

```bash
cd backend

# Create venv
python3.12 -m venv .venv
source .venv/bin/activate

# Install camoufox (pick one)
pip install "camoufox[geoip] @ git+https://github.com/JWriter20/camoufox.git#subdirectory=pythonlib"
# or: pip install 'camoufox[geoip]'

# Download Firefox binary (one-time, ~100 MB)
python -m camoufox fetch

# Install dependencies
pip install -e .

# Run
uvicorn m3u8_dl.web.app:app --host 0.0.0.0 --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # dev server (proxies /api → backend)
# or: npm run build && serve dist/
```

Open [http://localhost:5173](http://localhost:5173) in dev mode.

---

## Project structure

```
backend/src/m3u8_dl/
├── config.py                  # AppConfig (pydantic-settings, M3U8DL_ prefix)
├── models/
│   ├── segment.py
│   ├── playlist.py
│   └── session.py
├── services/
│   ├── browser.py             # Camoufox lifecycle (headless / virtual Xvfb)
│   ├── interceptor.py         # Playlist interception
│   ├── downloader.py          # Parallel segment downloader
│   ├── assembler.py           # ffmpeg concat → mp4
│   ├── capture.py             # Simple-mode orchestration
│   └── title_scraper.py       # Page title suggestions
├── utils/
│   ├── m3u8_parser.py
│   └── ffmpeg_check.py
└── web/
    ├── app.py                 # FastAPI app + lifespan
    ├── router.py              # Simple jobs API
    ├── service.py             # JobService (queue + scheduling)
    ├── repository.py          # SQLite jobs table
    ├── browse_session_router.py   # Captured mode API + SSE
    ├── browse_session_service.py  # Browser session lifecycle
    ├── browse_session_repository.py
    ├── website_router.py      # Websites + CDN API
    ├── website_service.py     # Website + CDN logic
    └── website_repository.py  # SQLite websites + website_cdns tables

frontend/src/
├── App.tsx                    # Tab routing (Simple / Captured / Sessions / Websites)
├── components/
│   ├── SimpleTab/             # Job queue UI
│   ├── CapturedTab/           # Browser viewer + candidate panel
│   ├── SessionsTab/           # Session list + download confirm
│   └── WebsitesTab/           # Website history + CDN management
├── hooks/                     # SSE hooks (useJobs, useBrowseSessions, useWebsites)
├── models/                    # TypeScript interfaces
├── services/                  # API clients
└── styles/                    # SCSS modules
```

---

## Environment variables (backend)

| Variable | Default | Description |
|---|---|---|
| `M3U8DL_OUTPUT_DIR` | `~/Downloads` | Where `.mp4` files are written |
| `M3U8DL_TEMP_DIR` | `/tmp/m3u8-dl` | Temp segment storage |
| `M3U8DL_PREFERRED_QUALITY` | `best` | `best`, `worst`, or `1920x1080` |
| `M3U8DL_MAX_PARALLEL_DOWNLOADS` | `4` | Concurrent segment downloads |
| `M3U8DL_HEADLESS` | `true` | Browser headless mode |
