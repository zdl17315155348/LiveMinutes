"""Download only INT8 streaming model files and upstream sample audio."""
from pathlib import Path
import urllib.request
import json

root = Path(__file__).resolve().parent.parent / 'data' / 'models' / 'streaming-paraformer'
root.mkdir(parents=True, exist_ok=True)
base = 'https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/main/'
files = ['encoder.int8.onnx', 'decoder.int8.onnx', 'tokens.txt', 'test_wavs/0.wav', 'test_wavs/1.wav', 'test_wavs/8k.wav']
for name in files:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        continue
    print('Downloading ' + name, flush=True)
    temporary = path.with_suffix(path.suffix + '.part')
    urllib.request.urlretrieve(base + name, temporary)
    temporary.replace(path)
    print(f'Saved {path.stat().st_size} bytes', flush=True)
(root / 'sources.json').write_text(json.dumps({'repository': base.split('/resolve/')[0], 'files': files}, indent=2), encoding='utf-8')
