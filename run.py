#!/usr/bin/env python3
"""
Launcher for Converter Alpha
"""
import subprocess
import sys
import os

def check_deps():
    issues = []

    # LibreOffice
    lo_found = False
    for c in ['/Applications/LibreOffice.app/Contents/MacOS/soffice',
              'libreoffice', 'soffice',
              r'C:\Program Files\LibreOffice\program\soffice.exe']:
        try:
            r = subprocess.run([c, '--version'], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                print(f"✅ LibreOffice: {r.stdout.strip()}")
                lo_found = True
                break
        except Exception:
            continue
    if not lo_found:
        print("⚠️  LibreOffice not found — document conversion disabled")
        print("   macOS:   brew install --cask libreoffice")
        print("   Windows: https://www.libreoffice.org/download/download-libreoffice/")

    # ffmpeg
    ff_found = False
    for c in ['ffmpeg', '/usr/local/bin/ffmpeg', '/opt/homebrew/bin/ffmpeg',
              r'C:\ffmpeg\bin\ffmpeg.exe']:
        try:
            r = subprocess.run([c, '-version'], capture_output=True, timeout=10)
            if r.returncode == 0:
                print("✅ ffmpeg: found")
                ff_found = True
                break
        except Exception:
            continue
    if not ff_found:
        print("⚠️  ffmpeg not found — audio/video conversion disabled")
        print("   macOS:   brew install ffmpeg")
        print("   Windows: https://ffmpeg.org/download.html")

    # Python packages
    try:
        import flask
        print(f"✅ Flask {flask.__version__}")
    except ImportError:
        issues.append("❌ Flask not found — run: pip install flask")

    try:
        from PIL import Image
        print("✅ Pillow: found")
    except ImportError:
        issues.append("❌ Pillow not found — run: pip install Pillow")

    return issues


if __name__ == '__main__':
    print("=" * 52)
    print("🔄  Converter Alpha")
    print("=" * 52)

    issues = check_deps()

    if issues:
        print("\nCritical missing dependencies:")
        for i in issues:
            print(f"  {i}")
        sys.exit(1)

    print("\n🚀  Starting at http://localhost:8080")
    print("    Press Ctrl+C to stop\n")

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    from app import app
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)