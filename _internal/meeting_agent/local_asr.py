"""Pace upstream WAV samples in 100 ms blocks and log partial ASR results."""
import json
from pathlib import Path
import time
import wave
import numpy as np
import sherpa_onnx

from .paths import ROOT

def create_recognizer():
    model = ROOT / 'data' / 'models' / 'streaming-paraformer'
    return sherpa_onnx.OnlineRecognizer.from_paraformer(
        tokens=str(model / 'tokens.txt'), encoder=str(model / 'encoder.int8.onnx'),
        decoder=str(model / 'decoder.int8.onnx'), num_threads=2,
        provider='cpu', enable_endpoint_detection=False)

def run(recognizer, path, on_event=None, stop_event=None):
    path = Path(path).resolve()
    with wave.open(str(path), 'rb') as f:
        if f.getsampwidth() != 2 or f.getnchannels() != 1 or f.getcomptype() != 'NONE':
            raise ValueError('请选择单声道、16位 PCM WAV 文件。')
        rate = f.getframerate()
        frame_count = f.getnframes()
    if not frame_count:
        raise ValueError('音频文件为空。')
    stream = recognizer.create_stream()
    block = int(rate * .1)
    events, costs, lags = [], [], []
    previous = ''
    start = time.perf_counter()
    def decode(audio_time, final=False):
        nonlocal previous
        t = time.perf_counter()
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        costs.append(time.perf_counter() - t)
        text = recognizer.get_result(stream)
        elapsed = time.perf_counter() - start
        if text != previous or final:
            event = {'elapsed_s': round(elapsed, 4), 'audio_supplied_s': round(audio_time, 4), 'text': text, 'final': final}
            events.append(event)
            if on_event:
                on_event({'kind': 'text', **event})
            print(f'[{path.name} {elapsed:.2f}s] {text}', flush=True)
            previous = text
    supplied = 0
    cancelled = False
    with wave.open(str(path), 'rb') as f:
        for offset in range(0, frame_count, block):
            end = min(offset + block, frame_count)
            target = end / rate
            delay = max(0, start + target - time.perf_counter())
            if stop_event is not None:
                if stop_event.wait(delay):
                    cancelled = True
                    break
            else:
                time.sleep(delay)
            samples = np.frombuffer(f.readframes(end - offset), dtype='<i2').astype(np.float32) / 32768
            t = time.perf_counter()
            stream.accept_waveform(rate, samples)
            costs.append(time.perf_counter() - t)
            supplied = end
            decode(target)
            lags.append(max(0, time.perf_counter() - start - target))
            if on_event:
                on_event({'kind': 'progress', 'position_s': target, 'duration_s': frame_count / rate})
    duration = supplied / rate
    stream.accept_waveform(rate, np.zeros(int(rate * .8), dtype=np.float32))
    stream.input_finished()
    decode(duration, final=True)
    nonempty = [e for e in events if e['text']]
    return {'sample': str(path), 'duration_s': duration, 'source_duration_s': frame_count / rate,
            'cancelled': cancelled,
            'first_text_from_stream_start_s': nonempty[0]['elapsed_s'] if nonempty else None,
            'partial_updates_before_audio_end': sum(bool(e['text']) and not e['final'] and e['audio_supplied_s'] < duration for e in events),
            'decode_and_feed_compute_s': sum(costs), 'compute_rtf': sum(costs)/duration if duration else None,
            'max_delivery_lag_s': max(lags, default=0),
            'final_text': previous, 'events': events}

def main():
    t = time.perf_counter()
    recognizer = create_recognizer()
    load = time.perf_counter() - t
    reports = [run(recognizer, p) for p in sorted((ROOT / 'data' / 'models' / 'streaming-paraformer' / 'test_wavs').glob('*.wav'))]
    output = ROOT / 'data' / 'test-output'
    output.mkdir(exist_ok=True)
    report = {'engine': 'sherpa-onnx', 'model': 'streaming-paraformer-bilingual-zh-en INT8',
              'provider': 'cpu', 'threads': 2, 'input_block_ms': 100,
              'load_s': load, 'tests': reports,
              'limitations': ['Short upstream examples, not a meeting accuracy benchmark.',
                              'First-text timing includes initial silence; it is not voice-onset latency.',
                              'RTF includes feed/decode and final decode, but excludes model loading and pacing sleep.',
                              'No long-duration, microphone, diarization or cloud summary test.']}
    (output / 'streaming_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({**report, 'tests': [{k:v for k,v in r.items() if k != 'events'} for r in reports]}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
