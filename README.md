# m3u8-dl

Captures HLS streams (m3u8 + ts segments) from a website page (that can use some anti bot protections) and assembles them into a local MP4 file.

Uses [camoufox](https://github.com/daijro/camoufox) to spoof a real Firefox fingerprint and avoid bans, with Playwright response interception to detect and save video segments.

---

## About AI

This project is made with claude code for my personal use.

Not all cases are tested. Worked for my use case with auto and interception mode.

You wouldn't steal a car ? *Then don't use this to steal some copyrighted content* (or do it, I'm not your dad).

---

## Requirements

- Python 3.12+
- ffmpeg
- Git

---

## 1. Install Python 3.12+

### Linux (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

Verify the install:

```bash
python3.12 --version
```

---

## 2. Install ffmpeg

### Linux

```bash
sudo apt install -y ffmpeg
```

Verify:

```bash
ffmpeg -version
```

---

## 3. Clone the repository

```bash
git clone <repo-url>
cd m3u8-dl
```

---

## 4. Create and activate a virtual environment

```bash
python3.12 -m venv .venv
```

**Linux :**

```bash
source .venv/bin/activate
```

Your prompt should now show `(.venv)`.

---

## 5. Install camoufox

Pick one of the following. All three expose the same API.

```bash
# JWriter20 stabilisation fork (recommended)
pip install "camoufox[geoip] @ git+https://github.com/JWriter20/camoufox.git#subdirectory=pythonlib"

# Official package
pip install 'camoufox[geoip]'

# CloverLabs fork (most actively maintained as of 2025)
pip install cloverlabs-camoufox
```

Then download the Firefox binary (one-time, ~100 MB):

```bash
python -m camoufox fetch
```

---

## 6. Install the project

```bash
pip install -e .
```

---

## 7. Verify the install

```bash
python -c "from camoufox.async_api import AsyncCamoufox; print('camoufox ok')"
ffmpeg -version | head -1
m3u8-dl --help
```

---

## Usage

### Capture a movie

```bash
m3u8-dl capture
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--mode` | `auto` | `auto`: detect m3u8 then download in parallel. `intercept`: save TS chunks as the browser streams them. `direct`: download immediately from a known m3u8 URL. |
| `--quality` | `best` | `best`, `worst`, or a resolution string like `1920x1080`. |
| `--output-dir` | `~/Desktop` | Directory where the final mp4 is saved. |
| `--keep-segments` | off | Keep `.ts` segment files after assembly. |
| `--parallel` | `8` | Number of concurrent segment downloads (auto/direct mode). |
| `--headless` | off | Run browser without a window. Not recommended for Cloudflare sites. |

### Examples

```bash
# Best quality, auto mode, save to Desktop
m3u8-dl capture

# Force a specific resolution
m3u8-dl capture --quality 1920x1080

# Keep segments in case you need to re-assemble
m3u8-dl capture --keep-segments --output-dir /tmp

# Re-assemble from saved segments without re-downloading
m3u8-dl assemble ~/.m3u8-dl/temp/my-movie ~/Desktop/my-movie.mp4
```

---

## Capture modes

| Mode | How it works | Best for |
|---|---|---|
| `auto` | Waits up to 30s for m3u8 detection, then downloads all segments in parallel. Falls back to intercept if no playlist is found. | Long movies — fast parallel download. |
| `intercept` | Saves every TS chunk as the browser receives it. You must let the video play from start to finish. | Sites where the m3u8 URL cannot be parsed directly. |
| `direct` | Immediately fetches and downloads the playlist. Useful when you already know the m3u8 URL appears early. | Short clips or known playlist structures. |

---

## Project structure

```
src/m3u8_dl/
├── cli.py               # Click CLI (capture, assemble commands)
├── config.py            # AppConfig (pydantic-settings, env prefix M3U8DL_)
├── models/
│   ├── segment.py       # Segment dataclass
│   ├── playlist.py      # Playlist + Variant dataclasses
│   └── session.py       # CaptureSession + status enum
├── services/
│   ├── browser.py       # Camoufox browser lifecycle
│   ├── interceptor.py   # Playwright response event listener
│   ├── downloader.py    # Parallel httpx segment downloader
│   ├── assembler.py     # ffmpeg concat → mp4
│   └── capture.py       # Orchestration
└── utils/
    ├── m3u8_parser.py   # Playlist parsing and variant selection
    └── ffmpeg_check.py  # ffmpeg availability check
```

---

## Configuration via environment variables

All options can also be set via environment variables with the `M3U8DL_` prefix:

```bash
M3U8DL_OUTPUT_DIR=~/Videos
M3U8DL_KEEP_SEGMENTS=true
M3U8DL_MAX_PARALLEL_DOWNLOADS=16
M3U8DL_PREFERRED_QUALITY=1920x1080
```

Or place them in a `.env` file at the project root.

---

## Resuming a failed capture

If a capture fails after downloading segments, use the `assemble` command to rebuild the mp4 without re-downloading:

```bash
m3u8-dl assemble ~/.m3u8-dl/temp/my-movie ~/Desktop/my-movie.mp4
```

Segments are stored in `~/.m3u8-dl/temp/<output-name>/` when `--keep-segments` is used.
