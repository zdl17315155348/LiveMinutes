"""First-run setup using only Python's standard library; never reads API keys."""
import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent
MODULES = 'import numpy, sherpa_onnx, websockets, dotenv, pyaudiowpatch, pywebrtc_audio, soxr, tkinter'

def setup(check_only=False):
    if sys.platform != 'win32':
        raise RuntimeError('桌面录音启动器需要 Windows；Ubuntu 请参考 README 手动准备开发环境。')
    if not (3, 11) <= sys.version_info[:2] < (3, 15) or platform.architecture()[0] != '64bit':
        raise RuntimeError('请安装64位 Python 3.11～3.14，推荐 Python 3.11。')
    python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not python.is_file():
        if check_only:
            raise RuntimeError('尚未创建项目运行环境。')
        print('首次运行：正在创建独立运行环境…', flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    requirements = ROOT / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = ROOT / '.venv' / '.liveminutes-requirements'
    probe = subprocess.run([str(python), '-c', MODULES], capture_output=True)
    installed = probe.returncode == 0
    needs_install = not installed or not marker.is_file() or marker.read_text().strip() != fingerprint
    if check_only:
        if not installed:
            raise RuntimeError('依赖检查失败，请正常运行启动器以安装依赖。')
        print('PASS: Python、项目运行环境、依赖和 Tk 可用；未联网、未录音。')
        return
    if needs_install:
        print('正在安装或更新依赖，首次运行需要联网，请稍候…', flush=True)
        result = subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], cwd=ROOT)
        if result.returncode:
            raise RuntimeError('依赖下载或安装失败。请检查网络，再双击启动；已下载内容会尽量复用。')
        if subprocess.run([str(python), '-c', MODULES], capture_output=True).returncode:
            raise RuntimeError('依赖仍不可用，请确认 Python 包含 Tcl/Tk 并检查安装结果。')
        marker.write_text(fingerprint, encoding='ascii')
    env_path = ROOT / '.env'
    if not env_path.exists():
        shutil.copyfile(ROOT / '.env.example', env_path)
    print('正在启动 LiveMinutes…', flush=True)
    result = subprocess.run([str(python), '-m', 'meeting_agent.ui'], cwd=ROOT)
    if result.returncode:
        raise RuntimeError('程序退出异常，请查看上方错误信息。')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Check current environment without installation or UI')
    args = parser.parse_args()
    try:
        setup(args.check)
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
