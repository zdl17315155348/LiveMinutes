"""Microphone -> official Doubao bidirectional WebSocket -> persisted transcript."""
import argparse
import asyncio
from collections import deque
import json
from pathlib import Path
import threading
import time
import uuid

from websockets.asyncio.client import connect
from .cloud_asr import ROOT, ENDPOINT, DOCUMENTATION, configuration, packet, parse_packet, recognition_snapshot, safe_error
from .microphone import Microphone

async def recognize_microphone(device=-1, on_event=None, stop_event=None, source_factory=Microphone):
    key, resource = configuration()
    stop = stop_event or threading.Event()
    directory = ROOT / 'data' / 'recordings' / (time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    wav_path = directory / 'audio.wav'
    transcript = ''
    segments = []
    events = deque(maxlen=64)
    sent_frames = 0
    received_final = False
    final_sent = False
    started = None
    final_send_time = None
    first_text = None
    update_count = 0
    report = {'engine': 'Doubao ASR 2.0', 'resource_id': resource, 'endpoint': ENDPOINT,
              'documentation': DOCUMENTATION, 'input': 'microphone', 'device_id': device,
              'audio_path': str(wav_path), 'two_pass': True, 'punctuation': True}
    def emit(event):
        if on_event:
            on_event(event)
    microphone = source_factory(device, wav_path, stop,
                                lambda level, seconds: emit({'kind': 'level', 'dbfs': level, 'position_s': seconds}))
    report['input'] = getattr(microphone, 'input_kind', 'microphone')
    journal = (directory / 'transcript_updates.jsonl').open('w', encoding='utf-8')
    def journal_update(text, utterances, final, elapsed):
        nonlocal transcript, segments, first_text, update_count
        # Store only the changed suffix, so long meetings do not repeatedly write the full transcript.
        previous = transcript
        prefix = 0
        for a, b in zip(previous, text):
            if a != b:
                break
            prefix += 1
        journal.write(json.dumps({'elapsed_s': elapsed, 'replace_from': prefix, 'text': text[prefix:],
                                  'final': final}, ensure_ascii=False) + '\n')
        journal.flush()
        transcript, segments = text, utterances
        if text and first_text is None:
            first_text = elapsed
        update_count += 1
        event = {'kind': 'text', 'text': text, 'utterances': utterances,
                 'elapsed_s': round(elapsed, 3), 'audio_supplied_s': sent_frames / 16000, 'final': final}
        events.append({'elapsed_s': round(elapsed, 3), 'replace_from': prefix, 'text': text[prefix:], 'final': final})
        emit(event)
    async def sender(ws):
        nonlocal sent_frames, started, final_sent, final_send_time
        if stop.is_set():
            raise RuntimeError('已在录音开始前取消。')
        await asyncio.to_thread(microphone.start)
        started = time.perf_counter()
        emit({'kind': 'recording', 'directory': str(directory)})
        while True:
            data = await asyncio.to_thread(microphone.read)
            if data is None:
                break
            await asyncio.wait_for(ws.send(packet(2, data)), timeout=10)
            sent_frames += len(data) // 2
            emit({'kind': 'live_progress', 'position_s': sent_frames / 16000})
        await ws.send(packet(2, b'', final=True))
        final_sent = True
        final_send_time = time.perf_counter()
        emit({'kind': 'finishing'})
    async def receiver(ws):
        nonlocal received_final
        last_identity = None
        # A quiet room may produce no new result for >30s. Poll so silence doesn't end recording.
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1)
            except asyncio.TimeoutError:
                if final_send_time and time.perf_counter() - final_send_time > 30:
                    raise TimeoutError('等待最终识别结果超时。')
                continue
            body, final = parse_packet(raw)
            text, utterances = recognition_snapshot(body)
            if body.get('code') not in (None, 0, 1000, 20000000):
                raise RuntimeError(f"云端识别状态码 {body['code']}")
            identity = (text, json.dumps(utterances, ensure_ascii=False))
            if (text or utterances) and (identity != last_identity or final):
                journal_update(text, utterances, final, time.perf_counter() - started if started else 0)
                last_identity = identity
            if final:
                if not final_sent:
                    raise RuntimeError('服务在录音结束前终止连接，已保留本机录音和转写。')
                received_final = True
                return
    headers = {'X-Api-Key': key, 'X-Api-Resource-Id': resource,
               'X-Api-Request-Id': str(uuid.uuid4()), 'X-Api-Connect-Id': str(uuid.uuid4())}
    parameters = {'audio': {'format': 'pcm', 'codec': 'raw', 'rate': 16000, 'bits': 16, 'channel': 1},
                  'request': {'model_name': 'bigmodel', 'enable_nonstream': True,
                              'enable_punc': True, 'enable_itn': True, 'enable_ddc': False,
                              'enable_accelerate_text': False, 'show_utterances': True, 'result_type': 'full'}}
    try:
        emit({'kind': 'connecting'})
        async with connect(ENDPOINT, additional_headers=headers, open_timeout=20, close_timeout=5,
                           max_size=8 * 1024 * 1024, proxy=None) as ws:
            report['server_log_id'] = ws.response.headers.get('X-Tt-Logid', '')
            await ws.send(packet(1, json.dumps(parameters).encode(), is_json=True))
            tasks = [asyncio.create_task(sender(ws)), asyncio.create_task(receiver(ws))]
            try:
                await asyncio.gather(*tasks)
            finally:
                stop.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as error:
        report['error'] = safe_error(error, key)
    finally:
        stop.set()
        try:
            await asyncio.to_thread(microphone.close)
        except Exception as error:
            report.setdefault('error', safe_error(error, key))
        journal.close()
        report.update({'completed': received_final and 'error' not in report,
                       'duration_s': sent_frames / 16000, 'recorded_duration_s': microphone.frames / 16000,
                       'final_text': transcript, 'utterances': segments, 'recent_updates': list(events),
                       'first_text_from_stream_start_s': first_text, 'updates': update_count,
                       'finalization_wait_s': time.perf_counter() - final_send_time if final_send_time else None})
        if hasattr(microphone, 'metadata'):
            report['audio_sources'] = microphone.metadata
        (directory / 'transcript.txt').write_text(transcript, encoding='utf-8')
        report['report_path'] = str(directory / 'report.json')
        (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if 'error' in report:
        raise RuntimeError(report['error'] + '；数据已保存到：' + str(directory))
    return report

def run_microphone(device=-1, on_event=None, stop_event=None):
    return asyncio.run(recognize_microphone(device, on_event, stop_event))

def run_online(device=-1, loopback_device=-1, on_event=None, stop_event=None, echo_cancellation=True):
    from .online_audio import OnlineAudio
    def factory(device, path, stop, on_level):
        return OnlineAudio(device, path, stop, on_level, loopback_device=loopback_device,
                           echo_cancellation=echo_cancellation, on_sources=on_event)
    return asyncio.run(recognize_microphone(device, on_event, stop_event, source_factory=factory))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', type=int, default=-1)
    parser.add_argument('--seconds', type=float, default=10)
    args = parser.parse_args()
    stop = threading.Event()
    timer = None
    def event(value):
        global timer
        if value['kind'] == 'recording':
            print('RECORDING', flush=True)
            timer = threading.Timer(args.seconds, stop.set)
            timer.start()
        elif value['kind'] == 'text':
            print(value['text'], flush=True)
    try:
        result = run_microphone(args.device, event, stop)
        print(json.dumps({k: result[k] for k in ('completed', 'duration_s', 'recorded_duration_s', 'updates', 'report_path')}, ensure_ascii=False), flush=True)
    except Exception as error:
        print(safe_error(error), flush=True)
        raise SystemExit(1)
    finally:
        if timer:
            timer.cancel()
