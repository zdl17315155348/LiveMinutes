"""WASAPI dual capture, timestamp alignment and AEC3 before ASR mixing."""
from collections import deque
from contextlib import ExitStack
import math
from pathlib import Path
import queue
import threading
import time
import wave

import numpy as np

RATE = 16000
BLOCK = 3200

def online_devices():
    """Enumerate only; never open a recording stream here."""
    import pyaudiowpatch as pa
    with pa.PyAudio() as manager:
        microphones = [{'id': -1, 'name': '系统默认麦克风（WASAPI）'}]
        loopbacks = [{'id': -1, 'name': '系统默认播放设备'}]
        api = manager.get_host_api_info_by_type(pa.paWASAPI)
        for device in manager.get_device_info_generator():
            if device['hostApi'] != api['index']:
                continue
            if device.get('isLoopbackDevice'):
                loopbacks.append({'id': int(device['index']), 'name': device['name']})
            elif device['maxInputChannels'] > 0:
                microphones.append({'id': int(device['index']), 'name': device['name']})
        return microphones, loopbacks

def mono_16k(data, channels, native_rate):
    """Downmix in float, then apply a band-limited conversion at native block boundaries."""
    import soxr
    samples = np.frombuffer(data, dtype='<f4')
    if len(samples) % channels:
        raise ValueError('系统录音数据不是完整的声道帧。')
    mono = samples.reshape(-1, channels).mean(axis=1)
    if native_rate != RATE and len(mono):
        mono = soxr.resample(mono, native_rate, RATE, quality='HQ')
    return np.asarray(mono, dtype=np.float32)

class PacketResampler:
    """Continuous band-limited resampling, including filter delay and silent gaps."""
    def __init__(self, channels, native_rate):
        import soxr
        self.channels, self.native_rate = channels, native_rate
        self.resampler = soxr.ResampleStream(native_rate, RATE, 1, dtype='float32', quality='HQ')
        self.end = None
        self.finished = False

    def flush(self):
        if self.end is None or self.finished:
            return []
        tail = self.resampler.resample_chunk(np.empty(0, dtype=np.float32), last=True)
        self.finished = True
        return [(round(self.end * RATE) - len(tail), tail)] if len(tail) else []

    def feed(self, start_seconds, data):
        result = []
        if self.end is not None and start_seconds - self.end > .1:
            result.extend(self.flush())
        if self.finished:
            self.resampler.clear()
            self.finished = False
        raw = np.frombuffer(data, dtype='<f4')
        if len(raw) % self.channels:
            raise ValueError('系统音频声道数据不完整。')
        mono = raw.reshape(-1, self.channels).mean(axis=1)
        converted = self.resampler.resample_chunk(mono)
        self.end = start_seconds + len(mono) / self.native_rate
        position = round(self.end * RATE - self.resampler.delay()) - len(converted)
        if len(converted):
            result.append((position, converted))
        return result

class TimelineTrack:
    """Place independently clocked packets on one 16kHz recording timeline."""
    def __init__(self):
        self.packets = deque()
        self.consumed_until = 0
        self.late_frames = 0

    def put(self, start_frame, samples):
        start_frame = int(start_frame)
        trim = max(0, self.consumed_until - start_frame)
        self.late_frames += min(trim, len(samples))
        if trim < len(samples):
            self.packets.append((start_frame + trim, samples[trim:]))

    def render(self, start, count):
        end = start + count
        result = np.zeros(count, dtype=np.float32)
        retained = deque()
        for position, samples in self.packets:
            packet_end = position + len(samples)
            left, right = max(start, position), min(end, packet_end)
            if right > left:
                result[left-start:right-start] = samples[left-position:right-position]
            if packet_end > end:
                retained.append((position, samples))
        self.packets = retained
        self.consumed_until = end
        return result

def pcm16(samples):
    return np.round(np.clip(samples, -1, 32767 / 32768) * 32768).astype('<i2').tobytes()

def dbfs(samples):
    return 20 * math.log10(max(float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0, 1e-6))

class AudioMixer:
    def __init__(self, echo_cancellation=True):
        self.echo_cancellation = echo_cancellation
        self.processor = None
        if echo_cancellation:
            from pywebrtc_audio import AudioProcessor
            self.processor = AudioProcessor(sample_rate=RATE, echo_cancellation=True,
                                            noise_suppression=False, auto_gain_control=False,
                                            stream_delay_ms=0)

    def process(self, microphone, system):
        if len(microphone) != len(system):
            raise ValueError('双路音频长度不一致。')
        clean = self.processor.process(np.asarray(microphone, dtype=np.float32),
                                       np.asarray(system, dtype=np.float32)) if self.processor else microphone.copy()
        mixed = .7 * clean + .7 * system
        peak = float(np.max(np.abs(mixed))) if len(mixed) else 0
        if peak > .95:
            mixed = mixed * (.95 / peak)
        return np.asarray(clean, dtype=np.float32), np.asarray(mixed, dtype=np.float32)

class OnlineAudio:
    """Microphone-compatible source. No capture begins until start() is called."""
    input_kind = 'microphone_and_system'
    rate = RATE

    def __init__(self, device, path, stop_event, on_level=None, *, loopback_device=-1,
                 echo_cancellation=True, on_sources=None):
        self.device = device
        self.path = Path(path)
        self.stop_event = stop_event
        self.on_level = on_level
        self.loopback_device = loopback_device
        self.echo_cancellation = echo_cancellation
        self.on_sources = on_sources
        self.audio = queue.Queue(maxsize=50)
        self.incoming = queue.Queue(maxsize=400)
        self.ready = threading.Event()
        self.done = threading.Event()
        self.error = None
        self.thread = None
        self.frames = 0
        self.metadata = {'echo_cancellation': echo_cancellation, 'alignment_buffer_ms': 300,
                         'mix': '0.7 * cleaned microphone + 0.7 * system, peak limited'}

    def start(self):
        self.thread = threading.Thread(target=self.capture, daemon=True)
        self.thread.start()
        if not self.ready.wait(15):
            self.stop_event.set()
            raise RuntimeError('打开双路录音超时。')
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
            self.thread.join(8)
            if self.thread.is_alive():
                raise RuntimeError('双路音频设备尚未释放。')

    def capture(self):
        streams = []
        tracks = {'microphone': TimelineTrack(), 'system': TimelineTrack()}
        converters = {}
        try:
            import pyaudiowpatch as pa
            with pa.PyAudio() as manager, ExitStack() as stack:
                api = manager.get_host_api_info_by_type(pa.paWASAPI)
                mic_id = int(api['defaultInputDevice']) if self.device == -1 else self.device
                mic = manager.get_device_info_by_index(mic_id)
                system = manager.get_default_wasapi_loopback() if self.loopback_device == -1 else manager.get_device_info_by_index(self.loopback_device)
                if mic.get('isLoopbackDevice') or mic['maxInputChannels'] < 1 or mic['hostApi'] != api['index']:
                    raise ValueError('请选择WASAPI麦克风输入设备，不能把回环设备当作麦克风。')
                if not system.get('isLoopbackDevice'):
                    raise ValueError('所选播放设备不支持WASAPI回环录音。')
                self.metadata.update({'microphone': mic['name'], 'system': system['name'],
                                      'microphone_native_rate': int(mic['defaultSampleRate']),
                                      'system_native_rate': int(system['defaultSampleRate'])})
                mixer = AudioMixer(self.echo_cancellation)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                writers = {}
                for name, filename in [('mixed', self.path.name), ('microphone', 'microphone_raw.wav'),
                                       ('system', 'system.wav'), ('clean', 'microphone_clean.wav')]:
                    writer = stack.enter_context(wave.open(str(self.path.parent / filename), 'wb'))
                    writer.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                    writers[name] = writer
                clock_offsets = {}
                accepting = threading.Event()
                accepting.set()
                def callback_for(name, info):
                    native_rate = int(info['defaultSampleRate'])
                    channels = min(2, int(info['maxInputChannels']))
                    def callback(data, frame_count, timing, status):
                        if not accepting.is_set():
                            return (None, pa.paComplete)
                        if status:
                            self.error = RuntimeError(f'{name}音频设备报告溢出或中断（{status}），已停止并保留录音。')
                            self.stop_event.set()
                            return (None, pa.paAbort)
                        now = time.perf_counter()
                        current = timing.get('current_time', 0)
                        adc = timing.get('input_buffer_adc_time', 0)
                        if current and adc:
                            offset = clock_offsets.setdefault(name, now - current)
                            start_time = adc + offset
                        else:
                            start_time = now - frame_count / native_rate
                        try:
                            self.incoming.put_nowait((name, start_time, data, channels, native_rate))
                        except queue.Full:
                            self.error = RuntimeError('双路音频处理积压，已停止录音并保留已保存的数据。')
                            self.stop_event.set()
                            return (None, pa.paAbort)
                        return (None, pa.paContinue)
                    return callback, channels, native_rate
                for name, info in [('microphone', mic), ('system', system)]:
                    callback, channels, rate = callback_for(name, info)
                    stream = manager.open(format=pa.paFloat32, channels=channels, rate=rate,
                                          input=True, input_device_index=int(info['index']),
                                          frames_per_buffer=max(1, rate // 50), stream_callback=callback, start=False)
                    streams.append(stream)
                    stack.callback(stream.close)
                epoch = time.perf_counter()
                for stream in streams:
                    stream.start_stream()
                self.ready.set()
                def ingest(item):
                    name, started, data, channels, rate = item
                    if name not in converters:
                        converters[name] = PacketResampler(channels, rate)
                    for position, values in converters[name].feed(started - epoch, data):
                        tracks[name].put(position, values)
                def drain():
                    while True:
                        try:
                            ingest(self.incoming.get_nowait())
                        except queue.Empty:
                            break
                def save(count):
                    microphone = tracks['microphone'].render(self.frames, count)
                    reference = tracks['system'].render(self.frames, count)
                    # AEC runs on complete 10ms frames; preserve the exact final file length.
                    padding = (-count) % 160
                    clean, mixed = mixer.process(np.pad(microphone, (0, padding)), np.pad(reference, (0, padding)))
                    clean, mixed = clean[:count], mixed[:count]
                    for name, values in [('microphone', microphone), ('system', reference), ('clean', clean), ('mixed', mixed)]:
                        writers[name].writeframes(pcm16(values))
                    self.frames += count
                    if not self.error:
                        try:
                            self.audio.put_nowait(pcm16(mixed))
                        except queue.Full:
                            self.error = RuntimeError('云端发送积压超过10秒，已停止双路录音并保留本机数据。')
                            self.stop_event.set()
                    if self.on_level:
                        self.on_level(dbfs(mixed), self.frames / RATE)
                    if self.on_sources:
                        self.on_sources({'kind': 'source_levels', 'microphone_dbfs': dbfs(microphone), 'system_dbfs': dbfs(reference)})
                try:
                    while not self.stop_event.is_set():
                        try:
                            ingest(self.incoming.get(timeout=.01))
                        except queue.Empty:
                            pass
                        # Drain both callbacks before rendering; no stream may advance the other.
                        drain()
                        # Loopback may stop delivering callbacks while the speaker is silent.
                        for name, converter in converters.items():
                            if converter.end is not None and time.perf_counter() - epoch - converter.end > .15:
                                for position, values in converter.flush():
                                    tracks[name].put(position, values)
                        available = int(max(0, time.perf_counter() - epoch - .3) * RATE)
                        while self.frames + BLOCK <= available and not self.stop_event.is_set():
                            save(BLOCK)
                        if not all(stream.is_active() for stream in streams) and not self.stop_event.is_set():
                            raise RuntimeError('音频设备已断开，请重新选择设备后开始；已保存的数据会保留。')
                finally:
                    stopped_at = time.perf_counter()
                    for stream in streams:
                        if stream.is_active():
                            stream.stop_stream()
                    accepting.clear()
                    drain()
                    for name, converter in converters.items():
                        for position, values in converter.flush():
                            tracks[name].put(position, values)
                    final_frames = max(self.frames, round((stopped_at - epoch) * RATE))
                    while self.frames < final_frames:
                        save(min(BLOCK, final_frames - self.frames))
                    self.metadata['late_frames'] = {name: track.late_frames for name, track in tracks.items()}
        except Exception as error:
            self.error = error if isinstance(error, (RuntimeError, ValueError)) else RuntimeError('无法打开双路音频设备：' + str(error))
            self.stop_event.set()
        finally:
            self.ready.set()
            self.done.set()
