#!/usr/bin/env python3
"""
Converter Alpha — Single file, no templates folder needed
- Documents: DOCX ↔ PDF (Arabic + English)
- Images:    PNG ↔ JPEG ↔ WEBP ↔ BMP ↔ TIFF ↔ GIF
- Audio/Video: MP3 ↔ MP4, WAV ↔ MP3, etc.
- Max file size: 2 GB
"""

import os, uuid, subprocess, threading, time, shutil, mimetypes
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort, Response

# ── Tool detection ─────────────────────────────────────────────────────────────
def _find_soffice():
    for c in [
        '/Applications/LibreOffice.app/Contents/MacOS/soffice',
        'libreoffice', 'soffice',
        r'C:\Program Files\LibreOffice\program\soffice.exe',
        r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
    ]:
        try:
            r = subprocess.run([c, '--version'], capture_output=True, timeout=10)
            if r.returncode == 0:
                return c
        except Exception:
            pass
    return None

def _find_ffmpeg():
    for c in ['ffmpeg', '/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg',
              '/opt/homebrew/bin/ffmpeg', r'C:\ffmpeg\bin\ffmpeg.exe']:
        try:
            r = subprocess.run([c, '-version'], capture_output=True, timeout=10)
            if r.returncode == 0:
                return c
        except Exception:
            pass
    return None

SOFFICE = _find_soffice()
FFMPEG  = _find_ffmpeg()

try:
    from PIL import Image as PILImage
    PILLOW = True
except ImportError:
    PILLOW = False

# ── Flask setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2 GB

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / '_uploads'
OUTPUT_DIR = BASE_DIR / '_outputs'
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

jobs = {}

# ── Format definitions ─────────────────────────────────────────────────────────
DOC_EXTS   = {'.pdf', '.docx', '.doc', '.odt', '.rtf', '.txt'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.avif', '.ico'}
AUDIO_EXTS = {'.mp3', '.wav', '.aac', '.ogg', '.flac', '.opus', '.m4a', '.wma'}
VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.3gp', '.mpeg', '.mpg'}
ALL_EXTS   = DOC_EXTS | IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS

TARGETS = {
    '.pdf':  ['.docx', '.odt', '.txt'],
    '.docx': ['.pdf', '.odt', '.rtf', '.txt'],
    '.doc':  ['.pdf', '.docx', '.odt', '.rtf', '.txt'],
    '.odt':  ['.pdf', '.docx', '.rtf', '.txt'],
    '.rtf':  ['.pdf', '.docx', '.odt', '.txt'],
    '.txt':  ['.pdf', '.docx'],
    '.png':  ['.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff'],
    '.jpg':  ['.png', '.webp', '.gif', '.bmp', '.tiff'],
    '.jpeg': ['.png', '.webp', '.gif', '.bmp', '.tiff'],
    '.gif':  ['.png', '.jpg', '.webp', '.mp4'],
    '.bmp':  ['.png', '.jpg', '.webp', '.tiff'],
    '.webp': ['.png', '.jpg', '.gif', '.bmp', '.tiff'],
    '.tiff': ['.png', '.jpg', '.webp', '.bmp'],
    '.tif':  ['.png', '.jpg', '.webp', '.bmp'],
    '.avif': ['.png', '.jpg', '.webp'],
    '.ico':  ['.png', '.jpg'],
    '.mp3':  ['.mp4', '.wav', '.ogg', '.flac', '.aac', '.opus'],
    '.wav':  ['.mp3', '.mp4', '.ogg', '.flac', '.aac'],
    '.aac':  ['.mp3', '.wav', '.ogg', '.flac'],
    '.ogg':  ['.mp3', '.wav', '.flac', '.aac'],
    '.flac': ['.mp3', '.wav', '.ogg', '.aac'],
    '.opus': ['.mp3', '.wav', '.ogg'],
    '.m4a':  ['.mp3', '.wav', '.ogg', '.flac', '.aac'],
    '.wma':  ['.mp3', '.wav', '.ogg', '.flac'],
    '.mp4':  ['.mp3', '.wav', '.avi', '.mov', '.mkv', '.webm'],
    '.avi':  ['.mp4', '.mov', '.mkv', '.webm', '.mp3'],
    '.mov':  ['.mp4', '.avi', '.mkv', '.webm', '.mp3'],
    '.mkv':  ['.mp4', '.avi', '.mov', '.webm', '.mp3'],
    '.webm': ['.mp4', '.avi', '.mkv', '.mp3'],
    '.flv':  ['.mp4', '.avi', '.mkv', '.mp3'],
    '.wmv':  ['.mp4', '.avi', '.mkv', '.mp3'],
    '.3gp':  ['.mp4', '.avi', '.mp3'],
    '.mpeg': ['.mp4', '.avi', '.mkv', '.mp3'],
    '.mpg':  ['.mp4', '.avi', '.mkv', '.mp3'],
}

# ── Cleanup thread ─────────────────────────────────────────────────────────────
def _cleanup_loop():
    while True:
        time.sleep(600)
        cutoff = time.time() - 7200
        for base in [UPLOAD_DIR, OUTPUT_DIR]:
            for item in base.iterdir():
                try:
                    if item.is_dir() and item.stat().st_mtime < cutoff:
                        shutil.rmtree(item, ignore_errors=True)
                except Exception:
                    pass

threading.Thread(target=_cleanup_loop, daemon=True).start()

# ── Conversion functions ───────────────────────────────────────────────────────
def convert_document(src: Path, target_ext: str, out_dir: Path):
    env = os.environ.copy()
    env['LANG']   = 'ar_EG.UTF-8'
    env['LC_ALL'] = 'ar_EG.UTF-8'
    fmt_map = {
        '.pdf':  'pdf:writer_pdf_Export:{"UseTaggedPDF":{"type":"bool","value":"true"}}',
        '.docx': 'docx', '.odt': 'odt', '.rtf': 'rtf', '.txt': 'txt',
    }
    fmt   = fmt_map.get(target_ext, target_ext.lstrip('.'))
    extra = ['--infilter=writer_pdf_import'] if src.suffix.lower() == '.pdf' else []
    cmd   = ([SOFFICE, '--headless', '--norestore', '--nofirststartwizard']
             + extra + ['--convert-to', fmt, '--outdir', str(out_dir), str(src)])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env, cwd=str(out_dir))
    for f in out_dir.iterdir():
        if f.suffix.lower() == target_ext:
            return True, str(f)
    return False, r.stderr or r.stdout or 'LibreOffice conversion failed'


def convert_image(src: Path, target_ext: str, out_dir: Path):
    out = out_dir / (src.stem + target_ext)
    img = PILImage.open(src)
    if img.mode == 'P':
        img = img.convert('RGBA')
    if target_ext in ('.jpg', '.jpeg'):
        if img.mode in ('RGBA', 'LA'):
            bg = PILImage.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert('RGB')
        img.save(out, quality=95, optimize=True)
    elif target_ext == '.png':
        img.save(out, optimize=True)
    elif target_ext == '.webp':
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA')
        img.save(out, quality=92)
    elif target_ext in ('.tiff', '.tif'):
        img.save(out, compression='lzw')
    else:
        img.save(out)
    return True, str(out)


def convert_media(src: Path, target_ext: str, out_dir: Path, job_id: str):
    out = out_dir / (src.stem + target_ext)
    src_ext      = src.suffix.lower()
    src_is_audio = src_ext in AUDIO_EXTS
    dst_is_audio = target_ext in AUDIO_EXTS
    dst_is_video = target_ext in VIDEO_EXTS

    if src_is_audio and dst_is_audio:
        cmd = [FFMPEG, '-y', '-i', str(src)]
        cmd += {
            '.mp3': ['-codec:a','libmp3lame','-q:a','2'],
            '.aac': ['-codec:a','aac','-b:a','192k'],
            '.ogg': ['-codec:a','libvorbis','-q:a','6'],
            '.flac':['-codec:a','flac'],
            '.wav': ['-codec:a','pcm_s16le'],
            '.opus':['-codec:a','libopus','-b:a','128k'],
        }.get(target_ext, [])
        cmd.append(str(out))
    elif src_is_audio and dst_is_video:
        cmd = [FFMPEG,'-y','-f','lavfi','-i','color=c=black:s=1280x720:r=30',
               '-i',str(src),'-shortest','-c:v','libx264','-preset','fast',
               '-crf','28','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out)]
    elif not src_is_audio and dst_is_audio:
        cmd = [FFMPEG, '-y', '-i', str(src), '-vn']
        cmd += {
            '.mp3': ['-codec:a','libmp3lame','-q:a','2'],
            '.aac': ['-codec:a','aac','-b:a','192k'],
            '.ogg': ['-codec:a','libvorbis','-q:a','6'],
            '.flac':['-codec:a','flac'],
            '.wav': ['-codec:a','pcm_s16le'],
        }.get(target_ext, [])
        cmd.append(str(out))
    else:
        cmd = [FFMPEG, '-y', '-i', str(src)]
        if target_ext == '.mp4':
            cmd += ['-c:v','libx264','-preset','fast','-crf','22','-c:a','aac','-b:a','192k','-movflags','+faststart']
        elif target_ext == '.webm':
            cmd += ['-c:v','libvpx-vp9','-crf','30','-b:v','0','-c:a','libopus']
        else:
            cmd += ['-c:v','libx264','-preset','fast','-crf','22','-c:a','aac','-b:a','192k']
        cmd.append(str(out))

    duration = [None]
    def read_stderr(proc):
        for line in proc.stderr:
            line = line.strip()
            if 'Duration:' in line and duration[0] is None:
                try:
                    t = line.split('Duration:')[1].split(',')[0].strip()
                    h,m,s = t.split(':')
                    duration[0] = float(h)*3600+float(m)*60+float(s)
                except Exception: pass
            if 'time=' in line and duration[0]:
                try:
                    ts = line.split('time=')[1].split(' ')[0]
                    h,m,s = ts.split(':')
                    cur = float(h)*3600+float(m)*60+float(s)
                    jobs[job_id]['progress'] = min(97, int(cur/duration[0]*100))
                except Exception: pass

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    t = threading.Thread(target=read_stderr, args=(proc,), daemon=True)
    t.start()
    proc.wait(timeout=7200)
    t.join(timeout=5)
    if proc.returncode != 0:
        return False, 'ffmpeg conversion failed'
    if out.exists():
        return True, str(out)
    return False, 'Output file not found'


# ── Main dispatcher ────────────────────────────────────────────────────────────
def do_conversion(job_id, src: Path, original_name: str, target_ext: str, out_dir: Path):
    try:
        src_ext    = src.suffix.lower()
        final_name = Path(original_name).stem + target_ext
        jobs[job_id]['progress'] = 5

        if src_ext in DOC_EXTS or target_ext in DOC_EXTS:
            if not SOFFICE:
                raise RuntimeError('LibreOffice not found.\nInstall: brew install --cask libreoffice')
            ok, result = convert_document(src, target_ext, out_dir)
        elif src_ext in IMAGE_EXTS and target_ext in IMAGE_EXTS:
            if not PILLOW:
                raise RuntimeError('Pillow not installed.\nInstall: pip3 install Pillow')
            ok, result = convert_image(src, target_ext, out_dir)
        elif src_ext in AUDIO_EXTS | VIDEO_EXTS or target_ext in AUDIO_EXTS | VIDEO_EXTS:
            if not FFMPEG:
                raise RuntimeError('ffmpeg not found.\nInstall: brew install ffmpeg')
            ok, result = convert_media(src, target_ext, out_dir, job_id)
        else:
            raise RuntimeError(f'No converter for {src_ext} → {target_ext}')

        if ok:
            out_file   = Path(result)
            final_path = out_dir / final_name
            if out_file.resolve() != final_path.resolve() and out_file.exists():
                shutil.move(str(out_file), str(final_path))
            jobs[job_id].update({'status':'done','output_name':final_name,
                                 'file_path':str(final_path),'progress':100})
        else:
            jobs[job_id].update({'status':'error','message':result})
    except subprocess.TimeoutExpired:
        jobs[job_id].update({'status':'error','message':'Conversion timed out — file too large?'})
    except Exception as e:
        jobs[job_id].update({'status':'error','message':str(e)})

# ── Embedded HTML UI ─────────────────────────────────────────────────────────
HTML = r'''
<!DOCTYPE html>
<html lang="ar" dir="rtl" id="html-root">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Converter Alpha</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #f0f2f7;
    --surface: #ffffff;
    --surface2: #f7f9fc;
    --border: #e2e8f0;
    --text: #1a1f36;
    --text-muted: #64748b;
    --primary: #3d5aff;
    --primary-light: #eef0ff;
    --primary-dark: #2944e8;
    --success: #10b981;
    --success-light: #d1fae5;
    --error: #ef4444;
    --error-light: #fee2e2;
    --warning: #f59e0b;
    --shadow: 0 4px 24px rgba(61,90,255,0.08);
    --shadow-lg: 0 12px 48px rgba(61,90,255,0.14);
    --radius: 16px;
    --radius-sm: 10px;
    --transition: 0.25s cubic-bezier(0.4,0,0.2,1);
    --font-ar: 'Tajawal', sans-serif;
    --font-en: 'Plus Jakarta Sans', sans-serif;
  }

  [data-theme="dark"] {
    --bg: #0d0f1a;
    --surface: #161827;
    --surface2: #1c1f33;
    --border: #2a2e4a;
    --text: #e8ecff;
    --text-muted: #7c85b5;
    --primary: #6b7fff;
    --primary-light: #1a1f40;
    --primary-dark: #8b9fff;
    --success: #34d399;
    --success-light: #064e3b30;
    --error: #f87171;
    --error-light: #450a0a30;
    --shadow: 0 4px 24px rgba(0,0,0,0.4);
    --shadow-lg: 0 12px 48px rgba(0,0,0,0.5);
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-ar);
    min-height: 100vh;
    transition: background var(--transition), color var(--transition);
    overflow-x: hidden;
  }
  body.lang-en { font-family: var(--font-en); direction: ltr; }

  /* BACKGROUND */
  .bg-orbs { position: fixed; inset: 0; overflow: hidden; pointer-events: none; z-index: 0; }
  .orb { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.35; animation: float 8s ease-in-out infinite; }
  [data-theme="dark"] .orb { opacity: 0.15; }
  .orb-1 { width:500px;height:500px;background:radial-gradient(circle,#6b7fff,transparent);top:-10%;left:-10%;animation-delay:0s; }
  .orb-2 { width:400px;height:400px;background:radial-gradient(circle,#a78bfa,transparent);top:30%;right:-5%;animation-delay:-3s; }
  .orb-3 { width:300px;height:300px;background:radial-gradient(circle,#34d399,transparent);bottom:10%;left:20%;animation-delay:-6s; }
  @keyframes float {
    0%,100% { transform: translate(0,0) scale(1); }
    33% { transform: translate(20px,-30px) scale(1.05); }
    66% { transform: translate(-15px,20px) scale(0.97); }
  }

  /* LAYOUT */
  .app {
    position: relative; z-index: 1;
    max-width: 860px; margin: 0 auto;
    padding: 24px 16px 60px;
    min-height: 100vh;
    display: flex; flex-direction: column; gap: 24px;
  }

  /* HEADER */
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 20px 28px;
    background: var(--surface);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    border: 1px solid var(--border);
    gap: 16px;
  }
  .logo { display: flex; align-items: center; gap: 14px; }
  .logo-icon {
    width:52px;height:52px;
    background: linear-gradient(135deg, var(--primary), #a78bfa);
    border-radius:14px;
    display:flex;align-items:center;justify-content:center;
    font-size:24px;
    box-shadow:0 6px 20px rgba(107,127,255,0.35);
    flex-shrink:0;
  }
  .logo-text h1 {
    font-size:1.4rem;font-weight:800;
    background:linear-gradient(135deg,var(--primary),#a78bfa);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
    line-height:1.2;
  }
  .logo-text p { font-size:0.8rem;color:var(--text-muted);margin-top:2px; }
  .header-actions { display:flex;align-items:center;gap:12px;flex-shrink:0; }

  /* BUTTONS */
  .btn-icon {
    width:42px;height:42px;border-radius:10px;
    border:1px solid var(--border);background:var(--surface2);color:var(--text-muted);
    cursor:pointer;display:flex;align-items:center;justify-content:center;
    font-size:18px;transition:all var(--transition);
  }
  .btn-icon:hover { background:var(--primary-light);color:var(--primary);border-color:var(--primary); }
  .lang-toggle {
    padding:8px 16px;border-radius:10px;
    border:1px solid var(--border);background:var(--surface2);color:var(--text-muted);
    cursor:pointer;font-size:0.82rem;font-weight:600;transition:all var(--transition);font-family:inherit;
  }
  .lang-toggle:hover { background:var(--primary-light);color:var(--primary);border-color:var(--primary); }

  /* FORMATS BAR */
  .formats-bar {
    display:flex;gap:8px;flex-wrap:wrap;
    padding:14px 20px;
    background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);
    align-items:center;
  }
  .formats-label { font-size:0.8rem;color:var(--text-muted);font-weight:600;margin-inline-end:4px;white-space:nowrap; }
  .badge {
    display:inline-flex;align-items:center;gap:5px;
    padding:5px 12px;border-radius:50px;
    font-size:0.75rem;font-weight:700;letter-spacing:0.01em;white-space:nowrap;
  }
  .badge-blue  { background:var(--primary-light);color:var(--primary); }
  .badge-green { background:var(--success-light);color:var(--success); }
  .badge-red   { background:var(--error-light);color:var(--error); }
  .badge-purple{ background:#f3e8ff;color:#7c3aed; }
  [data-theme="dark"] .badge-purple { background:#2d1f4a;color:#c084fc; }

  /* TARGET SELECT */
  .target-select {
    padding:8px 12px;
    border-radius:9px;
    border:1.5px solid var(--border);
    background:var(--surface2);
    color:var(--text);
    font-size:0.88rem;font-weight:700;
    font-family:inherit;
    cursor:pointer;outline:none;
    min-width:100px;
    transition:border-color var(--transition),background var(--transition);
  }
  .target-select:focus { border-color:var(--primary); }
  .target-label {
    font-size:0.82rem;color:var(--text-muted);font-weight:600;white-space:nowrap;
  }

  /* UPLOAD ZONE */
  .upload-card {
    background:var(--surface);border-radius:var(--radius);
    border:1px solid var(--border);box-shadow:var(--shadow);overflow:hidden;
  }
  .drop-zone {
    position:relative;padding:60px 40px;text-align:center;cursor:pointer;
    transition:all var(--transition);
    border:2.5px dashed var(--border);border-radius:calc(var(--radius) - 2px);
    margin:20px;background:var(--surface2);
  }
  .drop-zone:hover,.drop-zone.drag-over {
    border-color:var(--primary);background:var(--primary-light);transform:scale(1.005);
  }
  .drop-zone input[type="file"] { position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%; }
  .drop-icon {
    width:80px;height:80px;margin:0 auto 20px;
    background:linear-gradient(135deg,var(--primary-light),#f3e8ff);
    border-radius:20px;display:flex;align-items:center;justify-content:center;
    font-size:36px;transition:transform var(--transition);box-shadow:var(--shadow);
  }
  .drop-zone:hover .drop-icon { transform:translateY(-4px) scale(1.05); }
  .drop-title { font-size:1.2rem;font-weight:700;margin-bottom:8px;color:var(--text); }
  .drop-subtitle { font-size:0.88rem;color:var(--text-muted);line-height:1.6;max-width:380px;margin:0 auto; }
  .drop-cta {
    margin-top:20px;display:inline-flex;align-items:center;gap:8px;
    padding:12px 28px;border-radius:50px;
    background:linear-gradient(135deg,var(--primary),#a78bfa);
    color:white;font-size:0.9rem;font-weight:600;
    box-shadow:0 6px 20px rgba(107,127,255,0.4);
    transition:all var(--transition);pointer-events:none;
  }
  .drop-zone:hover .drop-cta { box-shadow:0 8px 28px rgba(107,127,255,0.55);transform:translateY(-2px); }

  /* FILE PREVIEW */
  .file-preview {
    display:none;padding:16px 20px;
    border-top:1px solid var(--border);background:var(--surface2);
    align-items:center;gap:12px;flex-wrap:wrap;
  }
  .file-preview.visible { display:flex; }
  .file-icon-wrap {
    width:48px;height:48px;border-radius:12px;
    display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;
  }
  .file-icon-wrap.pdf   { background:#fee2e2; }
  .file-icon-wrap.word  { background:#dbeafe; }
  .file-icon-wrap.image { background:#dcfce7; }
  .file-icon-wrap.audio { background:#fef9c3; }
  .file-icon-wrap.video { background:#ede9fe; }

  .file-meta { flex:1;min-width:0; }
  .file-name { font-weight:600;font-size:0.92rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text); }
  .file-size { font-size:0.76rem;color:var(--text-muted);margin-top:2px; }

  .file-convert-row { display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap; }

  .convert-btn {
    padding:11px 26px;border-radius:12px;
    background:linear-gradient(135deg,var(--primary),#a78bfa);
    color:white;font-size:0.9rem;font-weight:700;border:none;cursor:pointer;
    transition:all var(--transition);box-shadow:0 6px 20px rgba(107,127,255,0.35);
    font-family:inherit;white-space:nowrap;display:flex;align-items:center;gap:8px;
  }
  .convert-btn:hover:not(:disabled) { transform:translateY(-2px);box-shadow:0 10px 28px rgba(107,127,255,0.5); }
  .convert-btn:disabled { opacity:0.5;cursor:not-allowed;transform:none; }
  .btn-clear {
    width:34px;height:34px;border-radius:8px;
    border:1px solid var(--border);background:var(--surface);color:var(--text-muted);
    cursor:pointer;display:flex;align-items:center;justify-content:center;
    font-size:15px;transition:all var(--transition);
  }
  .btn-clear:hover { background:var(--error-light);color:var(--error);border-color:var(--error); }

  /* PROGRESS */
  .progress-section { display:none;padding:24px;border-top:1px solid var(--border);background:var(--surface); }
  .progress-section.visible { display:block; }
  .progress-header { display:flex;justify-content:space-between;align-items:center;margin-bottom:12px; }
  .progress-label { font-size:0.9rem;font-weight:600;color:var(--text);display:flex;align-items:center;gap:8px; }
  .spinner { width:18px;height:18px;border:2.5px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin 0.8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .progress-track { height:8px;background:var(--surface2);border-radius:50px;overflow:hidden;margin-bottom:8px; }
  .progress-fill {
    height:100%;border-radius:50px;
    background:linear-gradient(90deg,var(--primary),#a78bfa);
    transition:width 0.4s ease;width:0%;position:relative;overflow:hidden;
  }
  .progress-fill::after {
    content:'';position:absolute;inset:0;
    background:linear-gradient(90deg,transparent,rgba(255,255,255,0.3),transparent);
    animation:shimmer 1.5s infinite;
  }
  @keyframes shimmer { 0%{transform:translateX(-100%)} 100%{transform:translateX(100%)} }
  .progress-status { font-size:0.8rem;color:var(--text-muted); }

  /* RESULT */
  .result-card { display:none;background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);overflow:hidden;box-shadow:var(--shadow);animation:slideUp 0.4s ease; }
  .result-card.visible { display:block; }
  @keyframes slideUp { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }
  .result-success {
    padding:28px;display:flex;align-items:center;gap:20px;
    background:linear-gradient(135deg,var(--success-light),transparent);
    border-bottom:1px solid var(--border);
  }
  .result-icon { width:64px;height:64px;background:var(--success-light);border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:32px;flex-shrink:0;border:2px solid rgba(52,211,153,0.3); }
  .result-info { flex:1; }
  .result-title { font-size:1.1rem;font-weight:700;color:var(--success);margin-bottom:4px; }
  .result-filename { font-size:0.88rem;color:var(--text-muted); }
  .download-btn {
    padding:14px 28px;border-radius:12px;
    background:linear-gradient(135deg,var(--success),#059669);
    color:white;font-size:0.9rem;font-weight:700;border:none;cursor:pointer;
    transition:all var(--transition);box-shadow:0 6px 20px rgba(52,211,153,0.35);
    font-family:inherit;white-space:nowrap;display:flex;align-items:center;gap:8px;text-decoration:none;
  }
  .download-btn:hover { transform:translateY(-2px);box-shadow:0 10px 28px rgba(52,211,153,0.5); }
  .result-actions { padding:16px 28px;display:flex;gap:12px;justify-content:flex-end;flex-wrap:wrap; }

  /* ERROR */
  .error-card { display:none;background:var(--surface);border-radius:var(--radius);border:2px solid var(--error);padding:24px;box-shadow:var(--shadow);animation:slideUp 0.3s ease; }
  .error-card.visible { display:block; }
  .error-title { font-size:1rem;font-weight:700;color:var(--error);margin-bottom:8px; }
  .error-msg { font-size:0.88rem;color:var(--text-muted);line-height:1.6; }

  /* BUTTONS SECONDARY */
  .btn-secondary {
    padding:10px 20px;border-radius:10px;
    border:1px solid var(--border);background:var(--surface2);
    color:var(--text);cursor:pointer;font-size:0.88rem;font-weight:600;
    transition:all var(--transition);font-family:inherit;display:inline-flex;align-items:center;gap:8px;
  }
  .btn-secondary:hover { background:var(--primary-light);border-color:var(--primary);color:var(--primary); }

  /* FEATURES */
  .features-grid { display:grid;grid-template-columns:1fr 1fr;gap:16px; }
  .feature-card {
    background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);
    padding:20px;display:flex;align-items:flex-start;gap:14px;
    transition:all var(--transition);box-shadow:var(--shadow);
  }
  .feature-card:hover { transform:translateY(-2px);box-shadow:var(--shadow-lg); }
  .feature-emoji { font-size:28px;flex-shrink:0;margin-top:2px; }
  .feature-text h3 { font-size:0.95rem;font-weight:700;color:var(--text);margin-bottom:4px; }
  .feature-text p  { font-size:0.82rem;color:var(--text-muted);line-height:1.5; }

  /* FOOTER */
  footer { text-align:center;padding:16px;font-size:0.8rem;color:var(--text-muted); }

  /* RESPONSIVE */
  @media (max-width:600px) {
    .features-grid { grid-template-columns:1fr; }
    .drop-zone { padding:40px 20px; }
    .result-success { flex-direction:column;text-align:center; }
    .result-actions { justify-content:center; }
    .formats-bar { padding:12px 14px; }
    .file-convert-row { width:100%; }
  }
  @media (max-width:400px) {
    .header-actions .lang-toggle { display:none; }
  }

  body.dragging .drop-zone { border-color:var(--primary);background:var(--primary-light); }
  .hidden { display:none !important; }
  *,*::before,*::after { transition:background-color var(--transition),border-color var(--transition),box-shadow var(--transition); }
  .progress-fill,.spinner,.orb { transition:none; }
  .progress-fill { transition:width 0.4s ease; }
</style>
</head>
<body>

<div class="bg-orbs">
  <div class="orb orb-1"></div>
  <div class="orb orb-2"></div>
  <div class="orb orb-3"></div>
</div>

<div class="app">

  <!-- HEADER -->
  <header>
    <div class="logo">
      <div class="logo-icon">🔄</div>
      <div class="logo-text">
        <h1 id="app-title">محوّل الملفات الشامل</h1>
        <p id="app-subtitle">مستندات • صور • صوت • فيديو</p>
      </div>
    </div>
    <div class="header-actions">
      <button class="lang-toggle" onclick="toggleLang()" id="lang-btn">EN</button>
      <button class="btn-icon" onclick="toggleTheme()" id="theme-btn" title="Dark mode">🌙</button>
    </div>
  </header>

  <!-- FORMATS BAR -->
  <div class="formats-bar">
    <span class="formats-label" id="formats-label">الصيغ المدعومة:</span>
    <span class="badge badge-blue">📝 DOCX ⇄ PDF</span>
    <span class="badge badge-green">🖼 PNG ⇄ JPG ⇄ WEBP ⇄ GIF ⇄ BMP</span>
    <span class="badge badge-red">🎵 MP3 ⇄ MP4 ⇄ WAV ⇄ FLAC</span>
    <span class="badge badge-purple">🎬 AVI ⇄ MKV ⇄ WEBM ⇄ MOV</span>
  </div>

  <!-- UPLOAD CARD -->
  <div class="upload-card">
    <div class="drop-zone" id="dropZone">
      <input type="file" id="fileInput"
        accept=".pdf,.docx,.doc,.odt,.rtf,.txt,
                .png,.jpg,.jpeg,.gif,.bmp,.webp,.tiff,.tif,.avif,.ico,
                .mp3,.wav,.aac,.ogg,.flac,.opus,.m4a,.wma,
                .mp4,.avi,.mov,.mkv,.webm,.flv,.wmv,.3gp,.mpeg,.mpg"
        onchange="handleFile(this.files[0])">
      <div class="drop-icon">📂</div>
      <div class="drop-title" id="drop-title">اسحب الملف هنا أو انقر للاختيار</div>
      <div class="drop-subtitle" id="drop-subtitle">مستندات • صور • صوت • فيديو — حتى 2 جيجابايت</div>
      <div class="drop-cta" id="drop-cta">
        <span>📎</span>
        <span id="drop-cta-text">اختر ملفاً</span>
      </div>
    </div>

    <!-- File Preview -->
    <div class="file-preview" id="filePreview">
      <div class="file-icon-wrap" id="fileIconWrap">📄</div>
      <div class="file-meta">
        <div class="file-name" id="fileName">—</div>
        <div class="file-size" id="fileSize">—</div>
      </div>
      <div class="file-convert-row">
        <label class="target-label" id="target-label">تحويل إلى:</label>
        <select id="targetSelect" class="target-select"></select>
        <button class="convert-btn" id="convertBtn" onclick="startConvert()" disabled>
          <span>⚡</span>
          <span id="convert-btn-text">تحويل</span>
        </button>
        <button class="btn-clear" onclick="clearFile()" title="إزالة الملف">✕</button>
      </div>
    </div>

    <!-- Progress -->
    <div class="progress-section" id="progressSection">
      <div class="progress-header">
        <div class="progress-label">
          <div class="spinner"></div>
          <span id="progress-label-text">جارٍ التحويل…</span>
        </div>
        <span id="progress-pct" style="font-size:0.82rem;color:var(--text-muted);font-weight:600;">0%</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="progressFill"></div>
      </div>
      <div class="progress-status" id="progressStatus">جارٍ معالجة الملف، يرجى الانتظار…</div>
    </div>
  </div>

  <!-- RESULT -->
  <div class="result-card" id="resultCard">
    <div class="result-success">
      <div class="result-icon">✅</div>
      <div class="result-info">
        <div class="result-title" id="result-title">تم التحويل بنجاح!</div>
        <div class="result-filename" id="resultFilename">—</div>
      </div>
      <a class="download-btn" id="downloadBtn" href="#" onclick="downloadFile(event)">
        <span>⬇️</span>
        <span id="download-btn-text">تحميل</span>
      </a>
    </div>
    <div class="result-actions">
      <button class="btn-secondary" onclick="convertAnother()">
        <span>🔄</span>
        <span id="another-btn-text">تحويل ملف آخر</span>
      </button>
    </div>
  </div>

  <!-- ERROR -->
  <div class="error-card" id="errorCard">
    <div class="error-title">⚠️ <span id="error-title-text">حدث خطأ</span></div>
    <div class="error-msg" id="errorMsg">—</div>
    <button class="btn-secondary" onclick="clearFile()" style="margin-top:14px;">
      🔄 <span id="retry-text">حاول مجدداً</span>
    </button>
  </div>

  <!-- FEATURES -->
  <div class="features-grid">
    <div class="feature-card">
      <div class="feature-emoji">🇸🇦</div>
      <div class="feature-text">
        <h3 id="feat1-title">دعم العربية الكامل</h3>
        <p id="feat1-desc">تحويل صحيح للنصوص العربية مع حل مشكلة التنسيق والاتجاه</p>
      </div>
    </div>
    <div class="feature-card">
      <div class="feature-emoji">🖼</div>
      <div class="feature-text">
        <h3 id="feat2-title">تحويل الصور</h3>
        <p id="feat2-desc">PNG ↔ JPG ↔ WEBP ↔ GIF ↔ BMP ↔ TIFF بجودة عالية</p>
      </div>
    </div>
    <div class="feature-card">
      <div class="feature-emoji">🎵</div>
      <div class="feature-text">
        <h3 id="feat3-title">صوت وفيديو</h3>
        <p id="feat3-desc">MP3 ↔ MP4 ↔ WAV ↔ FLAC ↔ AVI ↔ MKV وأكثر</p>
      </div>
    </div>
    <div class="feature-card">
      <div class="feature-emoji">⚡</div>
      <div class="feature-text">
        <h3 id="feat4-title">سريع ومجاني</h3>
        <p id="feat4-desc">يدعم ملفات حتى 2 جيجابايت — يعمل على جميع الأجهزة</p>
      </div>
    </div>
  </div>

  <footer>
    <span id="footer-text">محوّل الملفات الشامل — يعمل محلياً • ملفاتك آمنة وخاصة</span>
  </footer>

</div>

<script>
  // ══════════════════════════════════════════
  //  جدول الصيغ المدعومة
  // ══════════════════════════════════════════
  const TARGETS = {
    // مستندات
    '.pdf':  ['.docx','.odt','.txt'],
    '.docx': ['.pdf','.odt','.rtf','.txt'],
    '.doc':  ['.pdf','.docx','.odt','.rtf','.txt'],
    '.odt':  ['.pdf','.docx','.rtf','.txt'],
    '.rtf':  ['.pdf','.docx','.odt','.txt'],
    '.txt':  ['.pdf','.docx'],
    // صور
    '.png':  ['.jpg','.webp','.gif','.bmp','.tiff'],
    '.jpg':  ['.png','.webp','.gif','.bmp','.tiff'],
    '.jpeg': ['.png','.webp','.gif','.bmp','.tiff'],
    '.gif':  ['.png','.jpg','.webp','.mp4'],
    '.bmp':  ['.png','.jpg','.webp','.tiff'],
    '.webp': ['.png','.jpg','.gif','.bmp','.tiff'],
    '.tiff': ['.png','.jpg','.webp','.bmp'],
    '.tif':  ['.png','.jpg','.webp','.bmp'],
    '.avif': ['.png','.jpg','.webp'],
    '.ico':  ['.png','.jpg'],
    // صوت
    '.mp3':  ['.mp4','.wav','.ogg','.flac','.aac','.opus'],
    '.wav':  ['.mp3','.mp4','.ogg','.flac','.aac'],
    '.aac':  ['.mp3','.wav','.ogg','.flac'],
    '.ogg':  ['.mp3','.wav','.flac','.aac'],
    '.flac': ['.mp3','.wav','.ogg','.aac'],
    '.opus': ['.mp3','.wav','.ogg'],
    '.m4a':  ['.mp3','.wav','.ogg','.flac','.aac'],
    '.wma':  ['.mp3','.wav','.ogg','.flac'],
    // فيديو
    '.mp4':  ['.mp3','.wav','.avi','.mov','.mkv','.webm'],
    '.avi':  ['.mp4','.mov','.mkv','.webm','.mp3'],
    '.mov':  ['.mp4','.avi','.mkv','.webm','.mp3'],
    '.mkv':  ['.mp4','.avi','.mov','.webm','.mp3'],
    '.webm': ['.mp4','.avi','.mkv','.mp3'],
    '.flv':  ['.mp4','.avi','.mkv','.mp3'],
    '.wmv':  ['.mp4','.avi','.mkv','.mp3'],
    '.3gp':  ['.mp4','.avi','.mp3'],
    '.mpeg': ['.mp4','.avi','.mkv','.mp3'],
    '.mpg':  ['.mp4','.avi','.mkv','.mp3'],
  };

  function getIconInfo(ext) {
    if (ext === '.pdf') return { icon:'📄', cls:'pdf' };
    if (['.docx','.doc','.odt','.rtf','.txt'].includes(ext)) return { icon:'📝', cls:'word' };
    if (['.png','.jpg','.jpeg','.gif','.bmp','.webp','.tiff','.tif','.avif','.ico'].includes(ext)) return { icon:'🖼', cls:'image' };
    if (['.mp3','.wav','.aac','.ogg','.flac','.opus','.m4a','.wma'].includes(ext)) return { icon:'🎵', cls:'audio' };
    return { icon:'🎬', cls:'video' };
  }

  // ══════════════════════════════════════════
  //  State
  // ══════════════════════════════════════════
  let currentFile  = null;
  let currentJobId = null;
  let pollInterval = null;
  let fakeProgress = 0;
  let isDark       = false;
  let isEnglish    = false;

  // ══════════════════════════════════════════
  //  النصوص (عربي / إنجليزي)
  // ══════════════════════════════════════════
  const strings = {
    ar: {
      appTitle:       'Converter Alpha',
      appSubtitle:    'مستندات • صور • صوت • فيديو',
      formatsLabel:   'الصيغ المدعومة:',
      dropTitle:      'اسحب الملف هنا أو انقر للاختيار',
      dropSubtitle:   'مستندات • صور • صوت • فيديو — حتى 2 جيجابايت',
      dropCta:        'اختر ملفاً',
      targetLabel:    'تحويل إلى:',
      convertBtn:     'تحويل',
      converting:     'جارٍ التحويل…',
      convStatus:     'جارٍ معالجة الملف، يرجى الانتظار…',
      resultTitle:    'تم التحويل بنجاح!',
      downloadBtn:    'تحميل',
      anotherBtn:     'تحويل ملف آخر',
      errorTitle:     'حدث خطأ',
      retryText:      'حاول مجدداً',
      feat1Title:     'دعم العربية الكامل',
      feat1Desc:      'تحويل صحيح للنصوص العربية مع حل مشكلة التنسيق والاتجاه',
      feat2Title:     'تحويل الصور',
      feat2Desc:      'PNG ↔ JPG ↔ WEBP ↔ GIF ↔ BMP ↔ TIFF بجودة عالية',
      feat3Title:     'صوت وفيديو',
      feat3Desc:      'MP3 ↔ MP4 ↔ WAV ↔ FLAC ↔ AVI ↔ MKV وأكثر',
      feat4Title:     'سريع ومجاني',
      feat4Desc:      'يدعم ملفات حتى 2 جيجابايت — يعمل على جميع الأجهزة',
      footerText:     'Converter Alpha — يعمل محلياً • ملفاتك آمنة وخاصة',
      langBtn:        'EN',
      unsupported:    'صيغة غير مدعومة',
      unsupportedMsg: 'الصيغة {ext} غير مدعومة',
      uploadFailed:   'فشل رفع الملف',
      netError:       'خطأ في الاتصال',
      timeout:        'انتهت المهلة',
      timeoutMsg:     'استغرق التحويل وقتاً طويلاً',
      convFailed:     'فشل التحويل',
      dlFailed:       'فشل التحميل',
    },
    en: {
      appTitle:       'Converter Alpha',
      appSubtitle:    'Documents • Images • Audio • Video',
      formatsLabel:   'Supported formats:',
      dropTitle:      'Drag file here or click to browse',
      dropSubtitle:   'Documents, images, audio, video — up to 2 GB',
      dropCta:        'Choose a file',
      targetLabel:    'Convert to:',
      convertBtn:     'Convert',
      converting:     'Converting…',
      convStatus:     'Processing your file, please wait…',
      resultTitle:    'Conversion Successful!',
      downloadBtn:    'Download',
      anotherBtn:     'Convert Another',
      errorTitle:     'Error',
      retryText:      'Try Again',
      feat1Title:     'Full Arabic Support',
      feat1Desc:      'Correct Arabic text conversion with RTL direction fix',
      feat2Title:     'Image Conversion',
      feat2Desc:      'PNG ↔ JPG ↔ WEBP ↔ GIF ↔ BMP ↔ TIFF with high quality',
      feat3Title:     'Audio & Video',
      feat3Desc:      'MP3 ↔ MP4 ↔ WAV ↔ FLAC ↔ AVI ↔ MKV and more',
      feat4Title:     'Fast & Free',
      feat4Desc:      'Supports files up to 2 GB — works on all devices',
      footerText:     'Converter Alpha — runs locally • your files are private',
      langBtn:        'عربي',
      unsupported:    'Unsupported format',
      unsupportedMsg: 'Format {ext} is not supported',
      uploadFailed:   'Upload failed',
      netError:       'Network error',
      timeout:        'Timeout',
      timeoutMsg:     'Conversion took too long',
      convFailed:     'Conversion failed',
      dlFailed:       'Download failed',
    }
  };

  function s() { return strings[isEnglish ? 'en' : 'ar']; }

  // ══════════════════════════════════════════
  //  Theme
  // ══════════════════════════════════════════
  function toggleTheme() {
    isDark = !isDark;
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : '');
    document.getElementById('theme-btn').textContent = isDark ? '☀️' : '🌙';
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }

  // ══════════════════════════════════════════
  //  Language
  // ══════════════════════════════════════════
  function toggleLang() {
    isEnglish = !isEnglish;
    applyLanguage();
    localStorage.setItem('lang', isEnglish ? 'en' : 'ar');
  }

  function applyLanguage() {
    const L = s();
    const root = document.getElementById('html-root');
    root.setAttribute('lang', isEnglish ? 'en' : 'ar');
    root.setAttribute('dir',  isEnglish ? 'ltr' : 'rtl');
    document.body.classList.toggle('lang-en', isEnglish);

    const set = (id, val) => { const el=document.getElementById(id); if(el) el.textContent=val; };
    set('app-title',           L.appTitle);
    set('app-subtitle',        L.appSubtitle);
    set('formats-label',       L.formatsLabel);
    set('drop-title',          L.dropTitle);
    set('drop-subtitle',       L.dropSubtitle);
    set('drop-cta-text',       L.dropCta);
    set('target-label',        L.targetLabel);
    set('convert-btn-text',    L.convertBtn);
    set('progress-label-text', L.converting);
    set('progressStatus',      L.convStatus);
    set('result-title',        L.resultTitle);
    set('download-btn-text',   L.downloadBtn);
    set('another-btn-text',    L.anotherBtn);
    set('error-title-text',    L.errorTitle);
    set('retry-text',          L.retryText);
    set('feat1-title',         L.feat1Title);
    set('feat1-desc',          L.feat1Desc);
    set('feat2-title',         L.feat2Title);
    set('feat2-desc',          L.feat2Desc);
    set('feat3-title',         L.feat3Title);
    set('feat3-desc',          L.feat3Desc);
    set('feat4-title',         L.feat4Title);
    set('feat4-desc',          L.feat4Desc);
    set('footer-text',         L.footerText);
    set('lang-btn',            L.langBtn);
  }

  // ══════════════════════════════════════════
  //  Drag & Drop
  // ══════════════════════════════════════════
  const dropZone = document.getElementById('dropZone');

  document.addEventListener('dragenter', e => { e.preventDefault(); document.body.classList.add('dragging'); });
  document.addEventListener('dragleave', e => { if (!e.relatedTarget || e.relatedTarget===document.body) document.body.classList.remove('dragging'); });
  document.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  document.addEventListener('drop', e => {
    e.preventDefault();
    document.body.classList.remove('dragging');
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // ══════════════════════════════════════════
  //  File Handling
  // ══════════════════════════════════════════
  function handleFile(file) {
    if (!file) return;
    const ext = '.' + file.name.split('.').pop().toLowerCase();

    if (!TARGETS[ext]) {
      showError(s().unsupported, s().unsupportedMsg.replace('{ext}', ext));
      return;
    }

    currentFile = file;
    hideError();
    hideResult();

    // File info
    document.getElementById('filePreview').classList.add('visible');
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatSize(file.size);

    // Icon
    const { icon, cls } = getIconInfo(ext);
    const iconWrap = document.getElementById('fileIconWrap');
    iconWrap.textContent = icon;
    iconWrap.className   = 'file-icon-wrap ' + cls;

    // Target dropdown
    const sel = document.getElementById('targetSelect');
    sel.innerHTML = '';
    TARGETS[ext].forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = t.toUpperCase().replace('.','');
      sel.appendChild(opt);
    });

    document.getElementById('convertBtn').disabled = false;
    document.getElementById('progressSection').classList.remove('visible');
  }

  function clearFile() {
    currentFile = null;
    document.getElementById('filePreview').classList.remove('visible');
    document.getElementById('progressSection').classList.remove('visible');
    document.getElementById('fileInput').value = '';
    document.getElementById('convertBtn').disabled = true;
    hideError();
    hideResult();
    stopPolling();
  }

  function formatSize(bytes) {
    if (bytes < 1024)       return bytes + ' B';
    if (bytes < 1048576)    return (bytes/1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes/1048576).toFixed(1) + ' MB';
    return (bytes/1073741824).toFixed(2) + ' GB';
  }

  // ══════════════════════════════════════════
  //  Conversion
  // ══════════════════════════════════════════
  async function startConvert() {
    if (!currentFile) return;
    const targetExt = document.getElementById('targetSelect').value;
    if (!targetExt) return;

    const btn = document.getElementById('convertBtn');
    btn.disabled = true;
    hideError();
    hideResult();
    document.getElementById('progressSection').classList.add('visible');
    startFakeProgress();

    const formData = new FormData();
    formData.append('file', currentFile);
    formData.append('target', targetExt);

    try {
      const res  = await fetch('/api/convert', { method:'POST', body:formData });
      const data = await res.json();

      if (!res.ok || data.error) {
        stopFakeProgress();
        document.getElementById('progressSection').classList.remove('visible');
        showError(s().uploadFailed, data.error || 'Unknown error');
        btn.disabled = false;
        return;
      }
      currentJobId = data.job_id;
      pollStatus();
    } catch (err) {
      stopFakeProgress();
      document.getElementById('progressSection').classList.remove('visible');
      showError(s().netError, err.message);
      btn.disabled = false;
    }
  }

  function pollStatus() {
    let attempts = 0;
    pollInterval = setInterval(async () => {
      attempts++;
      if (attempts > 720) {
        stopPolling();
        document.getElementById('progressSection').classList.remove('visible');
        showError(s().timeout, s().timeoutMsg);
        return;
      }
      try {
        const res  = await fetch('/api/status/' + currentJobId);
        const data = await res.json();

        // Real progress from ffmpeg
        if (data.progress && data.progress > fakeProgress) setProgress(Math.min(95, data.progress));

        if (data.status === 'done') {
          stopPolling();
          setProgress(100);
          setTimeout(() => {
            document.getElementById('progressSection').classList.remove('visible');
            showResult(data);
          }, 500);
        } else if (data.status === 'error') {
          stopPolling();
          document.getElementById('progressSection').classList.remove('visible');
          showError(s().convFailed, data.message || 'Unknown error');
          document.getElementById('convertBtn').disabled = false;
        }
      } catch(e) { /* keep polling */ }
    }, 1000);
  }

  function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
  }

  // ══════════════════════════════════════════
  //  Progress
  // ══════════════════════════════════════════
  function startFakeProgress() {
    fakeProgress = 0;
    setProgress(0);
    [[800,10],[2500,28],[6000,48],[12000,65],[25000,78],[50000,88],[90000,93]].forEach(([delay,val]) => {
      setTimeout(() => { if (fakeProgress < val) setProgress(val); }, delay);
    });
  }

  function stopFakeProgress() { fakeProgress = 0; }

  function setProgress(val) {
    fakeProgress = val;
    document.getElementById('progressFill').style.width = val + '%';
    document.getElementById('progress-pct').textContent = val + '%';
  }

  // ══════════════════════════════════════════
  //  Result / Error
  // ══════════════════════════════════════════
  function showResult(data) {
    document.getElementById('resultCard').classList.add('visible');
    document.getElementById('resultFilename').textContent = data.output_name || '';
    document.getElementById('convertBtn').disabled = false;
  }
  function hideResult() { document.getElementById('resultCard').classList.remove('visible'); }

  async function downloadFile(e) {
    e.preventDefault();
    if (!currentJobId) return;
    try {
      const response = await fetch('/api/download/' + currentJobId);
      if (!response.ok) throw new Error('Download failed');
      const blob     = await response.blob();
      const status   = await fetch('/api/status/' + currentJobId).then(r => r.json());
      const filename = status.output_name || 'converted_file';
      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setTimeout(() => fetch('/api/cleanup/' + currentJobId, { method:'DELETE' }), 3000);
    } catch(err) {
      alert(s().dlFailed + ': ' + err.message);
    }
  }

  function showError(title, msg) {
    document.getElementById('error-title-text').textContent = title;
    document.getElementById('errorMsg').textContent = msg;
    document.getElementById('errorCard').classList.add('visible');
  }
  function hideError() { document.getElementById('errorCard').classList.remove('visible'); }

  function convertAnother() {
    clearFile(); hideResult(); currentJobId = null;
    window.scrollTo({ top:0, behavior:'smooth' });
  }

  // ══════════════════════════════════════════
  //  Init
  // ══════════════════════════════════════════
  (function init() {
    if (localStorage.getItem('theme') === 'dark') { isDark = false; toggleTheme(); }
    if (localStorage.getItem('lang')  === 'en')   { isEnglish = false; toggleLang(); }
    else applyLanguage();
  })();
</script>
</body>
</html>
'''

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')


@app.route('/api/caps')
def caps():
    return jsonify({
        'soffice': bool(SOFFICE),
        'ffmpeg':  bool(FFMPEG),
        'pillow':  PILLOW,
        'targets': {k: v for k, v in TARGETS.items()},
    })


@app.route('/api/convert', methods=['POST'])
def api_convert():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    src_ext    = Path(file.filename).suffix.lower()
    target_ext = request.form.get('target', '').lower().strip()
    if not target_ext.startswith('.'):
        target_ext = '.' + target_ext

    if src_ext not in ALL_EXTS:
        return jsonify({'error': f'Unsupported source format: {src_ext}'}), 400
    if target_ext not in ALL_EXTS:
        return jsonify({'error': f'Unsupported target format: {target_ext}'}), 400
    if src_ext == target_ext:
        return jsonify({'error': 'Source and target formats are the same'}), 400

    job_id   = str(uuid.uuid4())
    jup      = UPLOAD_DIR / job_id;  jup.mkdir()
    jout     = OUTPUT_DIR / job_id;  jout.mkdir()
    src_path = jup / ('input' + src_ext)
    file.save(str(src_path))

    jobs[job_id] = {'status':'processing','progress':0,
                    'original_name':file.filename,'target_ext':target_ext}

    threading.Thread(target=do_conversion,
                     args=(job_id, src_path, file.filename, target_ext, jout),
                     daemon=True).start()

    return jsonify({'job_id': job_id, 'status': 'processing'})


@app.route('/api/status/<job_id>')
def api_status(job_id):
    j = jobs.get(job_id)
    if not j:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(j)


@app.route('/api/download/<job_id>')
def api_download(job_id):
    j = jobs.get(job_id)
    if not j or j.get('status') != 'done':
        abort(404)
    fp = j.get('file_path', '')
    if not fp or not Path(fp).exists():
        abort(404)
    mime, _ = mimetypes.guess_type(fp)
    return send_file(fp, as_attachment=True,
                     download_name=j['output_name'],
                     mimetype=mime or 'application/octet-stream')


@app.route('/api/cleanup/<job_id>', methods=['DELETE'])
def api_cleanup(job_id):
    jobs.pop(job_id, None)
    for d in [UPLOAD_DIR / job_id, OUTPUT_DIR / job_id]:
        shutil.rmtree(d, ignore_errors=True)
    return jsonify({'ok': True})


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 52)
    print("🔄  Converter Alpha")
    print("=" * 52)
    print(f"{'✅' if SOFFICE else '⚠️ '} LibreOffice : {SOFFICE or 'not found — brew install --cask libreoffice'}")
    print(f"{'✅' if FFMPEG  else '⚠️ '} ffmpeg      : {FFMPEG  or 'not found — brew install ffmpeg'}")
    print(f"{'✅' if PILLOW  else '⚠️ '} Pillow      : {'ok' if PILLOW else 'not found — pip3 install Pillow'}")
    print()
    print("🚀  http://localhost:8080")
    print("    Press Ctrl+C to stop\n")
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)