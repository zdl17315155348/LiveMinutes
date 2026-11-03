"""Bounded, continuous Windows WinMM capture, with incremental WAV backup."""
import ctypes as c
from ctypes import wintypes as w
import math
from pathlib import Path
import queue
import struct
import threading
import time
import wave

class Caps(c.Structure):
    _fields_ = [('mid', w.WORD), ('pid', w.WORD), ('version', w.DWORD),
                ('name', w.WCHAR * 32), ('formats', w.DWORD),
                ('channels', w.WORD), ('reserved', w.WORD)]

class Format(c.Structure):
    _fields_ = [('tag', w.WORD), ('channels', w.WORD), ('rate', w.DWORD),
                ('bytes_per_sec', w.DWORD), ('align', w.WORD),
                ('bits', w.WORD), ('extra', w.WORD)]

class Header(c.Structure):
    _fields_ = [('data', c.c_void_p), ('length', w.DWORD), ('recorded', w.DWORD),
                ('user', c.c_size_t), ('flags', w.DWORD), ('loops', w.DWORD),
                ('next', c.c_void_p), ('reserved', c.c_size_t)]

def winmm():
    api = c.WinDLL('winmm')
    api.waveInOpen.argtypes = [c.POINTER(c.c_void_p), c.c_uint, c.POINTER(Format), c.c_size_t, c.c_size_t, w.DWORD]
    api.waveInGetDevCapsW.argtypes = [c.c_size_t, c.POINTER(Caps), c.c_uint]
    for name in ['waveInPrepareHeader', 'waveInUnprepareHeader', 'waveInAddBuffer']:
        getattr(api, name).argtypes = [c.c_void_p, c.POINTER(Header), c.c_uint]
    for name in ['waveInStart', 'waveInStop', 'waveInReset', 'waveInClose']:
        getattr(api, name).argtypes = [c.c_void_p]
    return api

def check(api, code):
    if code:
        message = c.create_unicode_buffer(256)
        api.waveInGetErrorTextW(code, message, 256)
        raise RuntimeError(f'麦克风错误 {code}：{message.value}。请检查 Windows 麦克风权限及设备连接。')

def devices():
    api = winmm()
    result = [{'id': -1, 'name': '系统默认麦克风'}]
    for index in range(api.waveInGetNumDevs()):
        caps = Caps()
        check(api, api.waveInGetDevCapsW(index, c.byref(caps), c.sizeof(caps)))
        result.append({'id': index, 'name': caps.name})
    return result

class Microphone:
    rate = 16000
    block_frames = 3200

    def __init__(self, device, path, stop_event, on_level=None):
        self.device = device
        self.path = Path(path)
        self.stop_event = stop_event
        self.on_level = on_level
        self.audio = queue.Queue(maxsize=50)  # At most 10 seconds; never silently drop audio.
        self.done = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.frames = 0
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.capture, daemon=True)
        self.thread.start()
        if not self.ready.wait(10):
            self.stop_event.set()
            raise RuntimeError('打开麦克风超时。')
        if self.error:
            raise self.error

    def read(self):
        while True:
            if self.error:
                raise self.error
            try:
                return self.audio.get(timeout=.1)
            except queue.Empty:
                if self.done.is_set():
                    return None

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(5)
            if self.thread.is_alive():
                raise RuntimeError('麦克风尚未释放，请关闭窗口后检查设备。')

    def capture(self):
        api = winmm()
        handle = c.c_void_p()
        prepared = []
        try:
            fmt = Format(1, 1, self.rate, self.rate * 2, 2, 16, 0)
            check(api, api.waveInOpen(c.byref(handle), self.device & 0xFFFFFFFF, c.byref(fmt), 0, 0, 0))
            buffers = [c.create_string_buffer(self.block_frames * 2) for _ in range(8)]
            headers = [Header(c.cast(buffer, c.c_void_p), len(buffer), 0, 0, 0, 0, None, 0) for buffer in buffers]
            for header in headers:
                check(api, api.waveInPrepareHeader(handle, c.byref(header), c.sizeof(header)))
                prepared.append(header)
                check(api, api.waveInAddBuffer(handle, c.byref(header), c.sizeof(header)))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(self.path), 'wb') as output:
                output.setparams((1, 2, self.rate, 0, 'NONE', 'not compressed'))
                check(api, api.waveInStart(handle))
                self.ready.set()
                index = 0
                while not self.stop_event.is_set():
                    header = headers[index]
                    if not header.flags & 1:
                        time.sleep(.01)
                        continue
                    self.save_chunk(buffers[index].raw[:header.recorded], output)
                    header.recorded = 0
                    check(api, api.waveInAddBuffer(handle, c.byref(header), c.sizeof(header)))
                    index = (index + 1) % len(headers)
                # Reset returns every pending header, including the final partial buffer.
                check(api, api.waveInStop(handle))
                check(api, api.waveInReset(handle))
                for step in range(len(headers)):
                    current = (index + step) % len(headers)
                    header = headers[current]
                    if header.recorded:
                        self.save_chunk(buffers[current].raw[:header.recorded], output)
        except Exception as error:
            self.error = error
        finally:
            if handle.value:
                api.waveInReset(handle)
                for header in prepared:
                    api.waveInUnprepareHeader(handle, c.byref(header), c.sizeof(header))
                api.waveInClose(handle)
            self.ready.set()
            self.done.set()

    def save_chunk(self, data, output):
        if not data:
            return
        output.writeframes(data)  # Updates WAV length after every chunk, not only on close.
        self.frames += len(data) // 2
        if self.error:
            return  # Continue flushing returned driver buffers to disk after a send backlog.
        try:
            self.audio.put_nowait(data)
        except queue.Full:
            self.error = RuntimeError('网络发送积压超过10秒，已停止录音；本机音频已保存，请稍后重试。')
            self.stop_event.set()
            return
        if self.on_level:
            samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
            rms = math.sqrt(sum(x*x for x in samples) / max(1, len(samples)))
            self.on_level(20 * math.log10(max(rms, 1) / 32768), self.frames / self.rate)
