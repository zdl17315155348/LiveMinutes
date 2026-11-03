def split_text(text, limit=12000, overlap=200):
    if limit < 2 or not 0 <= overlap < limit:
        raise ValueError('无效的分段长度。')
    result = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            candidates = [text.rfind(separator, start + limit // 2, end) for separator in ('\n', '。', '！', '？')]
            boundary = max(candidates)
            if boundary >= 0:
                end = boundary + 1
        result.append(text[start:end])
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return result
