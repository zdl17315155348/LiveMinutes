"""Convert imported audio to the PCM format required by streaming recognition."""
from pathlib import Path
import shutil
import subprocess
import uuid
import wave

from .paths import RECORDINGS_DIR


def prepare_audio(source, stop):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError('找不到所选音频文件。')
    if source.suffix.lower() == '.wav':
        try:
            with wave.open(str(source), 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000):
                    return source
        except (wave.Error, EOFError):
            pass
    if stop.is_set():
        raise RuntimeError('已取消音频导入。')
    try:
        import imageio_ffmpeg
        executable = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as error:
        executable = shutil.which('ffmpeg')
        if not executable:
            raise RuntimeError('缺少音频转换组件，请重新运行 start_meeting.bat 安装依赖。') from error
    directory = RECORDINGS_DIR / ('import_' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    target = directory / 'audio.wav'
    process = subprocess.Popen(
        [executable, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
         '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(target)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        while process.poll() is None:
            if stop.wait(.1):
                raise RuntimeError('已取消音频导入。')
        if stop.is_set():
            raise RuntimeError('已取消音频导入。')
        if process.returncode:
            raise RuntimeError('音频转换失败，请检查文件是否损坏、加密或格式不受支持。')
        with wave.open(str(target), 'rb') as audio:
            if audio.getnframes() == 0:
                raise RuntimeError('所选文件没有有效音频。')
        return target
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        target.unlink(missing_ok=True)
        raise
