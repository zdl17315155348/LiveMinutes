"""Grounded DeepSeek minutes with long-transcript reduction and retry checkpoints."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
import uuid

from dotenv import dotenv_values
from bootstrap.paths import ROOT, MINUTES_DIR

ENDPOINT = 'https://api.deepseek.com/chat/completions'
PROMPT_VERSION = 'minutes-v1'
from application.use_cases.prompts import SYSTEM

def configuration():
    values = dotenv_values(ROOT / '.env', encoding='utf-8-sig')
    key = (os.environ.get('DEEPSEEK_API_KEY') or values.get('DEEPSEEK_API_KEY') or '').strip()
    model = (os.environ.get('DEEPSEEK_MODEL') or values.get('DEEPSEEK_MODEL') or 'deepseek-flash').strip()
    if not key:
        raise ValueError('请先在项目 .env 中填写 DEEPSEEK_API_KEY，保存后点击“生成/重试纪要”。')
    return key, model

def is_configured():
    try:
        configuration()
        return True
    except ValueError:
        return False

from application.use_cases.text_chunks import split_text

from adapters.models.deepseek_http import request_completion

def atomic_text(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)

def save_minutes(text):
    """Publish all final minutes together, using Shanghai time and unique names."""
    MINUTES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone(timedelta(hours=8)))
    for offset in range(86400):
        # Windows forbids ASCII ':', so use the full-width colon U+FF1A.
        name = (timestamp + timedelta(seconds=offset)).strftime('%Y%m%dat%H%M%S.md')
        path = MINUTES_DIR / name
        try:
            file = path.open('x', encoding='utf-8')
        except FileExistsError:
            continue
        try:
            with file:
                file.write(text)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path
    raise RuntimeError('无法分配唯一的纪要文件名。')

def load_transcript(path):
    path = Path(path).resolve()
    if path.name.startswith('.env') or path.suffix.lower() not in ('.txt', '.md', '.json'):
        raise ValueError('请选择转写 TXT、Markdown 或识别报告 JSON。')
    if path.suffix.lower() == '.json':
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        text = value.get('final_text') if isinstance(value, dict) else None
    else:
        text = path.read_text(encoding='utf-8-sig')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('所选文件没有有效转写文字，暂不生成纪要。')
    return text.strip()

def generate_minutes(text, output_dir, on_progress=None, stop_event=None, client_factory=None):
    if not text or not text.strip():
        raise ValueError('没有有效转写文字，暂不生成纪要。')
    key, model = configuration()
    from adapters.models.deepseek import DeepSeekClient
    client = (client_factory or DeepSeekClient)(key, model, request_completion)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / 'minutes_runs' / (time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
    run_dir.mkdir(parents=True)
    cache = output_dir / '.minutes_cache'
    cache.mkdir(exist_ok=True)
    stop = stop_event or threading.Event()
    metadata = {'model': model, 'prompt_version': PROMPT_VERSION, 'completed': False,
                'transcript_sha256': hashlib.sha256(text.encode()).hexdigest(), 'calls': [],
                'run_directory': str(run_dir)}
    def notify(message):
        if on_progress:
            on_progress(message)
    def call(stage, prompt, max_tokens):
        if stop.is_set():
            raise RuntimeError('纪要生成已停止；已完成的分段结果已保留，可稍后重试。')
        digest = hashlib.sha256((PROMPT_VERSION + model + SYSTEM + prompt + str(max_tokens)).encode()).hexdigest()
        checkpoint = cache / (digest + '.json')
        if checkpoint.is_file():
            try:
                stored = json.loads(checkpoint.read_text(encoding='utf-8'))
                if isinstance(stored.get('text'), str) and stored['text'].strip():
                    metadata['calls'].append({'stage': stage, 'cached': True})
                    return stored['text']
            except (ValueError, OSError):
                pass
        notify(stage)
        answer, usage = client.complete(prompt, max_tokens)
        atomic_text(checkpoint, json.dumps({'text': answer}, ensure_ascii=False))
        metadata['calls'].append({'stage': stage, 'cached': False, 'usage': usage})
        return answer
    try:
        from application.use_cases.summarize import summarize
        draft = summarize(text, call, lambda name, value: atomic_text(run_dir / name, value),
                          lambda count: metadata.update(source_chunks=count))
        atomic_text(run_dir / 'minutes.md', draft)
        # Publish only after every stage succeeds; preserve all previously exported files.
        minutes_path = save_minutes(draft)
        metadata['completed'] = True
        metadata['minutes_path'] = str(minutes_path)
        notify('会议纪要已保存。')
    except Exception as error:
        message = str(error).replace(key, '[REDACTED]')[:500]
        metadata['error'] = message
        raise RuntimeError(message + '；生成记录：' + str(run_dir)) from None
    finally:
        atomic_text(run_dir / 'generation.json', json.dumps(metadata, ensure_ascii=False, indent=2))
    return {'text': draft, 'path': metadata['minutes_path'], 'metadata': metadata}

def generate_from_file(path, on_progress=None, stop_event=None):
    path = Path(path).resolve()
    text = load_transcript(path)
    return generate_minutes(text, path.parent, on_progress, stop_event)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('transcript', type=Path)
    args = parser.parse_args()
    try:
        result = generate_from_file(args.transcript, print)
        print('纪要已保存：' + result['path'])
    except Exception as error:
        print(str(error))
        raise SystemExit(1)
