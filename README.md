# 🔄 Universal File Converter

A powerful local file conversion tool that runs entirely on your machine.
No internet required. No data sent to any server. Supports files up to **2 GB**.

---

## ✨ Features

| Category | Supported Conversions |
|---|---|
| 📝 Documents | DOCX ↔ PDF, DOC → PDF, ODT ↔ PDF, RTF ↔ PDF, TXT → PDF |
| 🖼 Images | PNG ↔ JPG ↔ WEBP ↔ GIF ↔ BMP ↔ TIFF ↔ AVIF |
| 🎵 Audio | MP3 ↔ WAV ↔ AAC ↔ OGG ↔ FLAC ↔ OPUS |
| 🎬 Video | MP4 ↔ AVI ↔ MOV ↔ MKV ↔ WEBM + extract audio (MP4 → MP3) |
| 🎵→🎬 Special | MP3 → MP4 (audio with black background video) |

**Other highlights:**
- 🇸🇦 Full Arabic RTL support — correct text shaping and direction in PDFs
- 🌙 Dark / Light mode toggle
- 🌐 Arabic / English UI
- 📱 Responsive design — works on any screen size
- 🔒 100% private — files are auto-deleted after 2 hours
- ⚡ Handles files up to 2 GB with real-time progress bar

---

## 📦 What You Need to Install

There are two types of dependencies: **Python packages** (installed via pip) and **external programs** (installed separately on your OS).

### 1. Python Packages

| Package | Purpose |
|---|---|
| `flask` | Runs the local web server |
| `Pillow` | Handles all image conversions |

Install both with one command:

```bash
pip install flask Pillow
```

> On macOS/Linux you may need to use `pip3` instead of `pip`

---

### 2. External Programs

These are **not** Python packages — they are standalone programs.

| Program | Purpose | Required for |
|---|---|---|
| **LibreOffice** | Document conversion engine | DOCX ↔ PDF and all document formats |
| **ffmpeg** | Audio & video processing | All audio/video conversions |

> The app will run fine without them, but those conversion types will be disabled and a warning will appear in the UI.

---

## 🖥 Installation Guide

### 🍎 macOS

#### Step 1 — Install Python
Download the latest Python 3 installer from [python.org/downloads](https://www.python.org/downloads/) and run it.

#### Step 2 — Install Python packages
Open Terminal and run:
```bash
pip3 install flask Pillow
```

#### Step 3 — Install LibreOffice
**Option A** — Download directly from [libreoffice.org/download](https://www.libreoffice.org/download/download-libreoffice/), open the `.dmg` file and drag LibreOffice to Applications.

**Option B** — Using Homebrew:
```bash
brew install --cask libreoffice
```

> Don't have Homebrew? Install it first:
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

#### Step 4 — Install ffmpeg
```bash
brew install ffmpeg
```

---

### 🪟 Windows

#### Step 1 — Install Python
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the latest Python 3.x installer
3. Run it — **make sure to check "Add Python to PATH"** before clicking Install

#### Step 2 — Install Python packages
Open Command Prompt (`Win + R` → type `cmd` → Enter):
```cmd
pip install flask Pillow
```

#### Step 3 — Install LibreOffice
1. Go to [libreoffice.org/download](https://www.libreoffice.org/download/download-libreoffice/)
2. Download the Windows `.msi` installer
3. Run it and follow the setup wizard
4. Install to the default path: `C:\Program Files\LibreOffice\`

#### Step 4 — Install ffmpeg
1. Go to [ffmpeg.org/download.html](https://ffmpeg.org/download.html) → Windows builds → download from **gyan.dev** (choose the `full` build)
2. Extract the zip file anywhere (e.g. `C:\ffmpeg\`)
3. Make sure `ffmpeg.exe` is at: `C:\ffmpeg\bin\ffmpeg.exe`
4. Add it to your PATH:
   - Press `Win + S` → search **"Environment Variables"** → open it
   - Under **System Variables** → find `Path` → click **Edit**
   - Click **New** → type `C:\ffmpeg\bin` → click OK on all windows
5. Restart Command Prompt, then verify it works:
```cmd
ffmpeg -version
```

---

## 🚀 Running the App

**1. Clone or download the project:**
```bash
git clone https://github.com/your-username/universal-file-converter.git
cd universal-file-converter
```

**2. Start the app:**
```bash
# macOS / Linux
python3 run.py

# Windows
python run.py
```

**3. Open your browser and go to:**
```
http://localhost:8080
```

The launcher (`run.py`) will automatically check all dependencies and show you which ones are missing before starting. The web UI will also show warnings for any disabled features.

---

## 📁 Project Structure

```
universal-file-converter/
├── app.py              # Flask app — all conversion logic lives here
├── run.py              # Launcher — checks dependencies and starts server
├── templates/
│   └── index.html      # Web UI (Arabic/English, Dark/Light mode)
├── uploads/            # Temporary uploaded files (auto-cleaned every 2h)
└── outputs/            # Converted output files (auto-cleaned every 2h)
```

---

## 🔧 How It Works

### Document Conversion (LibreOffice)
LibreOffice runs in headless (no GUI) mode. Arabic support is enabled by setting the locale to `ar_EG.UTF-8` and using Tagged PDF export, which ensures correct RTL text direction and proper Arabic character shaping.

### Image Conversion (Pillow)
Pillow handles all image format conversions. It automatically handles tricky cases like RGBA → JPEG conversion (transparency is flattened onto a white background since JPEG doesn't support alpha channels).

### Audio / Video Conversion (ffmpeg)
ffmpeg handles all media conversions. The app reads ffmpeg's stderr output in real time, parses the `time=` progress field, and sends live progress updates to the browser. This means the progress bar shows actual conversion progress for large files.

### MP3 → MP4 (Special case)
ffmpeg generates a black 1280×720 background video using its built-in `lavfi` virtual input filter, then combines it with the audio. This is useful for uploading audio-only content to platforms that require a video format (like YouTube).

---

## ⚠️ Troubleshooting

**Document conversion not working**
→ Make sure LibreOffice is installed. On macOS it should be at `/Applications/LibreOffice.app`. On Windows at `C:\Program Files\LibreOffice\`.

**Audio/video conversion not working**
→ Verify ffmpeg is installed and on your PATH: run `ffmpeg -version` in a terminal. If it says "command not found", revisit Step 4 of the installation.

**Image conversion not working**
→ Run `pip3 install Pillow` to make sure it's installed.

**Port 8080 already in use**
→ In `run.py`, change `port=8080` to another port like `8081`, then open `http://localhost:8081`.

**Large file upload fails**
→ The app supports up to 2 GB. Make sure you have enough free disk space — the app needs room for both the uploaded file and the converted output.
