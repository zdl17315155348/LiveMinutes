import json
import urllib.error
import urllib.request
from application.use_cases.prompts import SYSTEM
ENDPOINT = 'https://api.deepseek.com/chat/completions'

def request_completion(key, model, prompt, max_tokens=8192):
    body = {'model': model, 'messages': [{'role': 'system', 'content': SYSTEM},
                                         {'role': 'user', 'content': prompt}],
            'thinking': {'type': 'disabled'}, 'temperature': .2,
            'max_tokens': max_tokens, 'stream': False}
    request = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode('utf-8'), method='POST',
                                     headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        hints = {400: '请求参数或模型配置不受支持', 401: 'API Key 无效', 402: 'DeepSeek 余额不足',
                 403: '账号或服务权限不足', 429: '请求频率超限', 500: '服务内部错误', 503: '服务暂时繁忙'}
        raise RuntimeError(f"DeepSeek HTTP {error.code}：{hints.get(error.code, '调用失败')}，可稍后手动重试。") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise RuntimeError('DeepSeek 网络连接失败或等待超时，请检查网络后手动重试。') from None
    except (ValueError, UnicodeError):
        raise RuntimeError('DeepSeek 响应不是有效 JSON，原转写已保留。') from None
    try:
        choice = data['choices'][0]
        text = choice['message']['content']
        if choice.get('finish_reason') != 'stop':
            raise RuntimeError('DeepSeek 输出未正常完成（可能达到输出长度限制），本次结果未作为最终纪要保存。')
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError('DeepSeek 返回空纪要，请手动重试。')
        return text.strip(), data.get('usage') or {}
    except (KeyError, IndexError, TypeError):
        raise RuntimeError('DeepSeek 响应缺少有效的纪要内容。') from None
