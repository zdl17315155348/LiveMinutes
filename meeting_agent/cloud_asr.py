"""Doubao ASR 2.0: paced WAV input, two-pass recognition, safe local reports."""
import argparse
import asyncio
import gzip
import json
import os
from pathlib import Path
import struct
import threading
import time
import uuid
import wave

from dotenv import dotenv_values
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from .paths import ROOT
ENDPOINT = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async'
DOCUMENTATION = 'https://docs.volcengine.com/docs/doubao-voice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh'

def configuration():
    values = dotenv_values(ROOT / '.env', encoding='utf-8-sig')
    key = os.environ.get('VOLCENGINE_ASR_API_KEY') or values.get('VOLCENGINE_ASR_API_KEY', '')
    resource = os.environ.get('VOLCENGINE_ASR_RESOURCE_ID') or values.get('VOLCENGINE_ASR_RESOURCE_ID') or 'volc.seedasr.sauc.duration'
    if not key or not key.strip():
        raise ValueError('请在项目 .env 中填写 VOLCENGINE_ASR_API_KEY。')
    return key.strip(), resource.strip()

def safe_error(error, key=''):
    # Never expose HTTP headers, raw handshake objects or tracebacks to UI/logs.
    if isinstance(error, InvalidStatus):
        status = error.response.status_code
        hints = {401: 'API Key 无效或鉴权失败', 403: '服务权限、资源类型或额度不匹配', 429: '请求超过并发或额度限制'}
        return f"云端连接失败 HTTP {status}：{hints.get(status, '请检查服务状态和网络')}"
    if isinstance(error, (OSError, TimeoutError)):
        return f'云端网络连接失败或等待超时（{type(error).__name__}），请检查网络后重试。'
    message = str(error)
    if key:
        message = message.replace(key, '[REDACTED]')
    return message[:500]

def packet(message_type, payload, final=False, is_json=False):
    compressed = gzip.compress(payload)
    header = bytes([0x11, (message_type << 4) | (2 if final else 0), (0x10 if is_json else 0) | 1, 0])
    return header + struct.pack('>I', len(compressed)) + compressed

def parse_packet(data):
    if not isinstance(data, bytes) or len(data) < 8:
        raise ValueError('云端返回了无效的二进制数据包。')
    offset = (data[0] & 15) * 4
    kind, flags = data[1] >> 4, data[1] & 15
    serialization, compression = data[2] >> 4, data[2] & 15
    if data[0] >> 4 != 1 or offset < 4 or offset > len(data):
        raise ValueError('不支持的云端协议头。')
    sequence = None
    if kind == 15:
        if len(data) < offset + 8:
            raise ValueError('云端错误包不完整。')
        code = struct.unpack_from('>I', data, offset)[0]
        offset += 4
    elif kind == 9:
        code = None
        if flags & 1:
            if len(data) < offset + 4:
                raise ValueError('云端序号不完整。')
            sequence = struct.unpack_from('>i', data, offset)[0]
            offset += 4
    else:
        raise ValueError(f'不支持的云端消息类型：{kind}')
    if len(data) < offset + 4:
        raise ValueError('云端数据长度缺失。')
    size = struct.unpack_from('>I', data, offset)[0]
    body = data[offset + 4:]
    if size != len(body):
        raise ValueError('云端数据包长度不匹配。')
    if compression == 1:
        body = gzip.decompress(body)
    elif compression != 0:
        raise ValueError('不支持的云端压缩格式。')
    if code is not None:
        # Error body may contain request content. Keep only the code in public logs.
        raise RuntimeError(f'云端识别返回错误码 {code}，请核对服务权限、额度和音频格式。')
    if serialization != 1:
        raise ValueError('云端响应不是 JSON 格式。')
    return json.loads(body), bool(flags & 2) or (sequence is not None and sequence < 0)

def recognition_snapshot(body):
    result = body.get('result') or {}
    if isinstance(result, list):
        result = result[0] if result else {}
    utterances = result.get('utterances') or []
    return result.get('text', ''), [
        {k: utterance.get(k) for k in ('text', 'start_time', 'end_time', 'definite')}
        for utterance in utterances
    ]

async def recognize(path, on_event=None, stop_event=None):
    key, resource = configuration()
    path = Path(path).resolve()
    with wave.open(str(path), 'rb') as f:
        if f.getnchannels() != 1 or f.getsampwidth() != 2 or f.getframerate() != 16000 or f.getcomptype() != 'NONE':
            raise ValueError('云端测试请选择 16kHz、单声道、16位 PCM WAV。')
        frames = f.getnframes()
    if not frames:
        raise ValueError('音频文件为空。')
    stop_event = stop_event or threading.Event()
    events, previous = [], None
    supplied = 0
    cancelled = False
    audio_start = None
    last_send = None
    transcript = ''
    utterances = []
    completed = False
    report = {'engine': 'Doubao streaming ASR 2.0', 'resource_id': resource, 'endpoint': ENDPOINT,
              'sample': str(path), 'source_duration_s': frames / 16000,
              'input_block_ms': 200, 'two_pass': True, 'punctuation': True,
              'number_normalization': True, 'events': events}
    def emit(event):
        if on_event:
            on_event(event)
    async def send_audio(ws):
        nonlocal supplied, cancelled, audio_start, last_send
        audio_start = time.perf_counter()
        emit({'kind': 'ready'})
        with wave.open(str(path), 'rb') as f:
            while supplied < frames:
                if stop_event.is_set():
                    cancelled = True
                    break
                count = min(3200, frames - supplied)
                target = (supplied + count) / 16000
                await asyncio.sleep(max(0, audio_start + target - time.perf_counter()))
                if stop_event.is_set():
                    cancelled = True
                    break
                data = f.readframes(count)
                supplied += count
                # An explicit empty terminal packet is sent below, including on stop.
                await ws.send(packet(2, data))
                emit({'kind': 'progress', 'position_s': supplied / 16000, 'duration_s': frames / 16000})
        await ws.send(packet(2, b'', final=True))
        last_send = time.perf_counter()
        emit({'kind': 'finishing'})
    async def receive(ws):
        nonlocal previous, transcript, utterances, completed
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            body, final = parse_packet(raw)
            text, segments = recognition_snapshot(body)
            elapsed = time.perf_counter() - audio_start if audio_start else 0
            identity = (text, json.dumps(segments, ensure_ascii=False))
            if identity != previous or final:
                # Empty acknowledgments must not erase previously recognized text.
                if text or segments:
                    transcript, utterances = text, segments
                    previous = identity
                    event = {'elapsed_s': round(elapsed, 4), 'audio_supplied_s': supplied / 16000,
                             'text': text, 'utterances': segments, 'final': final}
                    events.append(event)
                    emit({'kind': 'text', **event})
            if final:
                completed = True
                return
    headers = {'X-Api-Key': key, 'X-Api-Resource-Id': resource,
               'X-Api-Connect-Id': str(uuid.uuid4()), 'X-Api-Request-Id': str(uuid.uuid4())}
    parameters = {'user': {'uid': 'meeting-assistant-local'},
                  'audio': {'format': 'pcm', 'codec': 'raw', 'rate': 16000, 'bits': 16, 'channel': 1},
                  'request': {'model_name': 'bigmodel', 'enable_nonstream': True,
                              'enable_punc': True, 'enable_itn': True, 'enable_ddc': False,
                              'enable_accelerate_text': False, 'show_utterances': True,
                              'result_type': 'full'}}
    connected = time.perf_counter()
    try:
        async with connect(ENDPOINT, additional_headers=headers, open_timeout=20,
                           close_timeout=5, max_size=8 * 1024 * 1024, proxy=None) as ws:
            report['connect_s'] = time.perf_counter() - connected
            report['server_log_id'] = ws.response.headers.get('X-Tt-Logid', '')
            await ws.send(packet(1, json.dumps(parameters).encode('utf-8'), is_json=True))
            tasks = [asyncio.create_task(send_audio(ws)), asyncio.create_task(receive(ws))]
            try:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=frames / 16000 + 60)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        if not completed:
            raise RuntimeError('连接结束但未收到最终确认，请重试。')
    except Exception as error:
        report['error'] = safe_error(error, key)
    finally:
        elapsed = time.perf_counter() - audio_start if audio_start else 0
        nonempty = [e for e in events if e['text']]
        report.update({'completed': completed, 'cancelled': cancelled, 'duration_s': supplied / 16000,
                       'elapsed_s': elapsed, 'final_text': transcript, 'utterances': utterances,
                       'first_text_from_stream_start_s': nonempty[0]['elapsed_s'] if nonempty else None,
                       'partial_updates_before_audio_end': sum(bool(e['text']) and not e['final'] and e['audio_supplied_s'] < frames / 16000 for e in events),
                       'finalization_wait_s': time.perf_counter() - last_send if last_send else None})
        output = ROOT / 'data' / 'test-output'
        output.mkdir(exist_ok=True)
        name = output / ('cloud_' + time.strftime('%Y%m%d_%H%M%S') + f'_{time.time_ns() % 1000000000:09d}')
        name.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        name.with_suffix('.txt').write_text(transcript, encoding='utf-8')
        report['report_path'] = str(name.with_suffix('.json'))
    if 'error' in report:
        raise RuntimeError(report['error'] + '；本机报告：' + report['report_path'])
    return report

def run_cloud(path, on_event=None, stop_event=None):
    return asyncio.run(recognize(path, on_event, stop_event))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('wav', type=Path)
    args = parser.parse_args()
    def event(value):
        if value['kind'] == 'text':
            print(f"[{value['elapsed_s']:.2f}s] {value['text']}", flush=True)
    try:
        result = run_cloud(args.wav, event)
    except Exception as error:
        print(safe_error(error), flush=True)
        raise SystemExit(1)
    print(json.dumps({k:v for k,v in result.items() if k not in ('events', 'utterances')}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
