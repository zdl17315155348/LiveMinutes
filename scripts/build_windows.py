"""Build an allowlisted Windows portable distribution; excludes user data/keys."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
if sys.platform != 'win32':
    raise SystemExit('Build this Windows application on Windows.')
subprocess.run([sys.executable, str(ROOT / 'scripts/make_icons.py')], check=True)
command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
           '--name', 'LiveMinutes', '--paths', str(ROOT),
           '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build'),
           '--specpath', str(ROOT / 'build'),
           '--icon', str(ROOT / 'assets/liveminutes.ico'),
           '--add-data', str(ROOT / 'assets') + ';assets']
for module in ('domain', 'application', 'adapters', 'bootstrap', 'imageio_ffmpeg', 'pywebrtc_audio', 'pyaudiowpatch', 'soxr', 'sherpa_onnx'):
    command += ['--collect-all', module]
# Conda-backed Python keeps these native runtime dependencies outside DLLs/.
for name in ('ffi.dll', 'tcl86t.dll', 'tk86t.dll'):
    library = Path(sys.base_prefix) / 'Library' / 'bin' / name
    if library.is_file():
        command += ['--add-binary', str(library) + ';.']
command.append(str(ROOT / 'scripts/desktop_entry.py'))
subprocess.run(command, cwd=ROOT, check=True)
print('Built: ' + str(ROOT / 'dist/LiveMinutes/LiveMinutes.exe'))
