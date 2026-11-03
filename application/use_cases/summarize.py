from .text_chunks import split_text

def summarize(text, call, checkpoint, record_chunks):
    chunks = split_text(text.strip())
    record_chunks(len(chunks))
    if len(chunks) == 1:
        draft = call('正在生成会议纪要…', '请根据以下完整转写生成会议纪要草稿，清晰呈现核心内容、明确决定、行动事项与待确认内容。\n\n<会议转写>\n' + chunks[0] + '\n</会议转写>', 8192)
    else:
        notes = []
        for i, chunk in enumerate(chunks, 1):
            note = call(f'正在整理原文 {i}/{len(chunks)}…',
                        f'这是长会议的第{i}/{len(chunks)}片段，片段间可能重叠。请提取事实、议题、决定、待办与不确定内容，保留所有关键数字和否定词，标明来源片段编号；暂不写整场会议总结。尽量精炼。\n\n<转写片段>\n{chunk}\n</转写片段>', 4096)
            checkpoint(f'chunk_{i:03d}.md', note)
            notes.append(f'【原文片段{i}】\n{note}')
        combined = '\n\n'.join(notes)
        for depth in range(6):
            if len(combined) <= 20000:
                break
            groups = split_text(combined, limit=16000, overlap=0)
            summaries = []
            for i, group in enumerate(groups, 1):
                summary = call(f'正在合并分段要点，第{depth+1}轮 {i}/{len(groups)}…',
                               '以下是会议不同片段的提取结果。请压缩合并并去重，保留关键数字、否定、决定、待办及来源片段编号；不要添加事实，尽量控制在2000字以内。\n\n<提取结果>\n' + group + '\n</提取结果>', 4096)
                checkpoint(f'merge_{depth+1}_{i}.md', summary)
                summaries.append(summary)
            reduced = '\n\n'.join(summaries)
            if len(reduced) >= len(combined):
                raise RuntimeError('长会议要点未能有效压缩，分段结果已保留，未截断原文生成不完整纪要。')
            combined = reduced
        if len(combined) > 20000:
            raise RuntimeError('长会议要点超出合并范围，分段结果已保留。')
        draft = call('正在生成完整会议纪要…', '根据以下分段提取结果生成整场会议的中文纪要草稿，合并重复内容。区分讨论建议、明确决定、行动事项和待确认内容，保留来源片段编号。\n\n<分段要点>\n' + combined + '\n</分段要点>', 8192)
    return draft
