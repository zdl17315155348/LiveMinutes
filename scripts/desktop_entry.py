"""Frozen GUI entry point; never bundles the developer's environment file."""
import ctypes
import json
import runpy
import sys
from pathlib import Path

if __name__ == '__main__':
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LiveMinutes.Desktop')
    if '--self-check' in sys.argv:
        # Offline packaging smoke test, including native audio/codec libraries.
        import numpy, websockets, dotenv, soxr, pyaudiowpatch, pywebrtc_audio
        import sherpa_onnx
        import imageio_ffmpeg
        import tkinter as tk
        from paths import ROOT, ASSETS_DIR
        from ui import Demo
        root = tk.Tk()
        root.withdraw()
        app = Demo(root)
        root.update()
        root.destroy()
        report = {'ok': True, 'root': str(ROOT),
                  'icon': (ASSETS_DIR / 'liveminutes.ico').is_file(),
                  'ffmpeg': Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file()}
        (ROOT / 'self-check.json').write_text(json.dumps(report), encoding='utf-8')
    else:
        runpy.run_module('ui', run_name='__main__')
