"""Local Windows UI for observing paced streaming recognition of WAV files."""
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from .paths import ROOT

class Demo:
    def __init__(self, root, backend='cloud', auto_minutes=True):
        self.root = root
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.running = False
        self.closing = False
        self.recognizer = None
        self.summary_running = False
        self.summary_stop = threading.Event()
        self.latest_text = ''
        self.latest_output = None
        self.auto_minutes = tk.BooleanVar(value=auto_minutes)
        self.backend = tk.StringVar(value='云端 · 豆包二遍识别' if backend == 'cloud' else '本地 · CPU 对照')
        root.title('会议助手 · 实时录音转写')
        root.geometry('980x820')
        root.minsize(760, 540)
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='实时录音转写', font=('Microsoft YaHei UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='选择麦克风开始录音，讲话时持续转写；结束后保存录音和文字。').pack(anchor='w', pady=(5, 10))
        mode_row = ttk.Frame(frame)
        mode_row.pack(fill='x', pady=(0, 8))
        ttk.Label(mode_row, text='会议模式：').pack(side='left')
        self.meeting_mode = tk.StringVar(value='线下会议（麦克风）')
        self.mode_choice = ttk.Combobox(mode_row, state='readonly', textvariable=self.meeting_mode,
                                       values=['线下会议（麦克风）', '线上会议（麦克风＋系统声音）'], width=36)
        self.mode_choice.pack(side='left')
        self.mode_choice.bind('<<ComboboxSelected>>', self.change_meeting_mode)
        self.echo_enabled = tk.BooleanVar(value=True)
        self.echo_checkbox = ttk.Checkbutton(mode_row, text='抑制外放回声', variable=self.echo_enabled, state='disabled')
        self.echo_checkbox.pack(side='left', padx=10)
        mic_row = ttk.Frame(frame)
        mic_row.pack(fill='x', pady=(0, 10))
        ttk.Label(mic_row, text='麦克风：').pack(side='left')
        try:
            from .microphone import devices
            self.microphones = devices()
        except Exception:
            self.microphones = [{'id': -1, 'name': '系统默认麦克风'}]
        self.mic_choice = ttk.Combobox(mic_row, state='readonly',
                                     values=[f"{d['id']} · {d['name']}" for d in self.microphones], width=40)
        self.mic_choice.current(0)
        self.mic_choice.pack(side='left')
        ttk.Label(mic_row, text='  输入音量：').pack(side='left')
        self.level = ttk.Progressbar(mic_row, maximum=60, length=100)
        self.level.pack(side='left')
        self.offline_microphones = list(self.microphones)
        self.online_ready = False
        self.loopbacks = [{'id': -1, 'name': '系统默认播放设备'}]
        system_row = ttk.Frame(frame)
        system_row.pack(fill='x', pady=(0, 8))
        ttk.Label(system_row, text='系统声音：').pack(side='left')
        self.system_choice = ttk.Combobox(system_row, state='disabled', width=40,
                                        values=['-1 · 系统默认播放设备'])
        self.system_choice.current(0)
        self.system_choice.pack(side='left')
        self.source_levels = tk.StringVar(value='线下模式只录麦克风')
        ttk.Label(system_row, textvariable=self.source_levels).pack(side='left', padx=8)
        self.backend_choice = ttk.Combobox(frame, textvariable=self.backend, state='readonly',
                                          values=['云端 · 豆包二遍识别', '本地 · CPU 对照'])
        self.backend_choice.pack(anchor='w', pady=(0, 10))
        self.path = tk.StringVar(value=str(ROOT / 'data/models/streaming-paraformer/test_wavs/0.wav'))
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.entry = ttk.Entry(row, textvariable=self.path)
        self.entry.pack(side='left', fill='x', expand=True)
        self.browse = ttk.Button(row, text='选择 WAV', command=self.choose)
        self.browse.pack(side='left', padx=(8, 0))
        controls = ttk.Frame(frame)
        controls.pack(fill='x', pady=12)
        self.record_button = ttk.Button(controls, text='开始录音（云端）', command=lambda: self.start(live=True))
        self.record_button.pack(side='left', padx=(0, 12))
        self.start_button = ttk.Button(controls, text='测试所选音频文件', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(controls, text='结束并保存', command=self.stop_recording, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        summary_controls = ttk.Frame(frame)
        summary_controls.pack(fill='x', pady=(0, 8))
        self.auto_checkbox = ttk.Checkbutton(summary_controls, text='结束录音后自动生成纪要（文字发送至 DeepSeek）', variable=self.auto_minutes)
        self.auto_checkbox.pack(side='left')
        self.summary_button = ttk.Button(summary_controls, text='生成/重试纪要', command=self.generate_current, state='disabled')
        self.summary_button.pack(side='left', padx=8)
        self.import_button = ttk.Button(summary_controls, text='从已有转写生成', command=self.import_transcript)
        self.import_button.pack(side='left')
        self.status = tk.StringVar(value='云端识别会将录音发送至火山引擎并消耗额度。点击“开始录音”后才会打开麦克风。')
        ttk.Label(frame, textvariable=self.status, wraplength=870).pack(anchor='w')
        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.pack(fill='x', pady=10)
        self.minutes_status = tk.StringVar(value='纪要使用 DeepSeek；请在 .env 中配置 DEEPSEEK_API_KEY。')
        ttk.Label(frame, textvariable=self.minutes_status, wraplength=900).pack(anchor='w', pady=(0, 6))
        self.notebook = ttk.Notebook(frame)
        self.notebook.pack(fill='both', expand=True)
        transcript_tab = ttk.Frame(self.notebook, padding=8)
        self.minutes_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(transcript_tab, text='实时转写')
        self.notebook.add(self.minutes_tab, text='会议纪要')
        self.minutes_text = tk.Text(self.minutes_tab, wrap='word', state='disabled', padx=12, pady=12)
        self.minutes_text.pack(fill='both', expand=True)
        ttk.Label(transcript_tab, text='实时文字（灰色为待确认内容）').pack(anchor='w')
        self.transcript = tk.Text(transcript_tab, wrap='word', height=8, state='disabled', padx=12, pady=12)
        self.transcript.tag_configure('pending', foreground='#64748b')
        self.transcript.pack(fill='both', expand=True, pady=(5, 12))
        ttk.Label(transcript_tab, text='更新记录').pack(anchor='w')
        self.log = tk.Text(transcript_tab, wrap='word', height=5, state='disabled', padx=10, pady=8)
        self.log.pack(fill='both', expand=True, pady=5)
        self.metrics = tk.StringVar(value='短样本仅验证流式链路；准确率和两小时稳定性仍需单独验证。')
        ttk.Label(frame, textvariable=self.metrics, wraplength=870).pack(anchor='w', pady=(8, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def choose(self):
        path = filedialog.askopenfilename(filetypes=[('PCM WAV', '*.wav')])
        if path:
            self.path.set(path)

    def change_meeting_mode(self, event=None):
        if self.running or self.summary_running:
            return
        online = self.meeting_mode.get().startswith('线上')
        if online:
            try:
                from .online_audio import online_devices
                self.microphones, self.loopbacks = online_devices()
                self.system_choice.configure(values=[f"{d['id']} · {d['name']}" for d in self.loopbacks], state='readonly')
                self.system_choice.current(0)
                self.echo_checkbox.configure(state='normal')
                self.online_ready = True
                self.source_levels.set('将采集所选播放设备的全部声音')
                self.status.set('线上模式：播放设备要与会议软件一致；更换耳机或播放设备后请结束录音、重新选择。')
            except Exception as error:
                self.online_ready = False
                self.status.set('无法启用线上模式：' + str(error))
                self.meeting_mode.set('线下会议（麦克风）')
                online = False
        if not online:
            self.microphones = list(self.offline_microphones)
            self.system_choice.configure(state='disabled')
            self.echo_checkbox.configure(state='disabled')
            self.source_levels.set('线下模式只录麦克风')
        self.mic_choice.configure(values=[f"{d['id']} · {d['name']}" for d in self.microphones])
        self.mic_choice.current(0)

    def set_text(self, widget, text, append=False):
        widget.configure(state='normal')
        if not append:
            previous = widget.get('1.0', 'end-1c')
            same = len(os.path.commonprefix([previous, text]))
            widget.delete(f'1.0+{same}c', 'end')
            widget.insert('end', text[same:])
        else:
            widget.insert('end', text)
        widget.see('end')
        widget.configure(state='disabled')

    def stop_recording(self):
        self.stop.set()
        self.stop_button.configure(state='disabled')
        self.status.set('正在停止采集并处理最后一段音频…')

    def start(self, live=False):
        if self.running or self.summary_running:
            return
        path = Path(self.path.get()).expanduser()
        if not live and not path.is_file():
            self.status.set('找不到音频文件，请重新选择。')
            return
        if live and self.meeting_mode.get().startswith('线上') and not self.online_ready:
            self.change_meeting_mode()
            if not self.online_ready:
                return
        self.running = True
        self.is_live = live
        self.is_online = live and self.meeting_mode.get().startswith('线上')
        self.selected_loopback = self.loopbacks[max(0, self.system_choice.current())]['id']
        self.selected_echo = self.echo_enabled.get()
        self.latest_text = ''
        self.latest_output = None
        self.summary_button.configure(state='disabled')
        self.import_button.configure(state='disabled')
        self.minutes_status.set('转写保存后可生成纪要。')
        self.set_text(self.minutes_text, '')
        self.notebook.select(0)
        self.selected_device = self.microphones[max(0, self.mic_choice.current())]['id']
        self.stop.clear()
        for widget in [self.start_button, self.record_button, self.browse, self.entry, self.mic_choice, self.mode_choice, self.system_choice, self.echo_checkbox]:
            widget.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.set_text(self.transcript, '')
        self.set_text(self.log, '')
        self.progress['value'] = 0
        self.selected_backend = 'cloud' if live or self.backend.get().startswith('云端') else 'local'
        if live:
            self.backend.set('云端 · 豆包二遍识别')
        self.backend_choice.configure(state='disabled')
        self.status.set('正在连接云端识别服务…' if self.selected_backend == 'cloud' else '正在加载 CPU 模型…')
        self.metrics.set('准备中…')
        threading.Thread(target=self.work, args=(path,), daemon=True).start()

    def work(self, path):
        try:
            if self.is_live:
                if self.is_online:
                    from .live_asr import run_online
                    report = run_online(self.selected_device, self.selected_loopback, self.events.put,
                                        self.stop, echo_cancellation=self.selected_echo)
                else:
                    from .live_asr import run_microphone
                    report = run_microphone(self.selected_device, self.events.put, self.stop)
                self.events.put({'kind': 'done', 'report': report, 'path': report['report_path']})
                return
            if self.selected_backend == 'cloud':
                from .cloud_asr import run_cloud
                report = run_cloud(path, self.events.put, self.stop)
                self.events.put({'kind': 'done', 'report': report, 'path': report['report_path']})
                return
            from .local_asr import create_recognizer, run
            if self.recognizer is None:
                self.recognizer = create_recognizer()
            self.events.put({'kind': 'ready'})
            report = run(self.recognizer, path, self.events.put, self.stop)
            output = ROOT / 'data' / 'test-output'
            output.mkdir(exist_ok=True)
            name = output / ('demo_' + time.strftime('%Y%m%d_%H%M%S') + f'_{time.time_ns() % 1000000000:09d}')
            name.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            name.with_suffix('.txt').write_text(report['final_text'], encoding='utf-8')
            self.events.put({'kind': 'done', 'report': report, 'path': str(name.with_suffix('.json'))})
        except Exception as error:
            from .cloud_asr import safe_error
            self.events.put({'kind': 'error', 'message': safe_error(error)})

    def import_transcript(self):
        if self.running or self.summary_running:
            return
        path = filedialog.askopenfilename(title='选择已有转写', initialdir=ROOT / 'data',
                                          filetypes=[('转写文字或报告', '*.txt *.md *.json')])
        if not path:
            return
        try:
            from .minutes import load_transcript
            self.latest_text = load_transcript(path)
            self.latest_output = Path(path).resolve().parent
            self.set_text(self.transcript, self.latest_text)
            self.summary_button.configure(state='normal')
            self.generate_current()
        except Exception as error:
            self.minutes_status.set(str(error))

    def generate_current(self):
        if self.running or self.summary_running or not self.latest_text.strip():
            return
        from .minutes import is_configured
        if not is_configured():
            self.minutes_status.set('请在 .env 填写 DEEPSEEK_API_KEY 并保存，再点“生成/重试纪要”；无需重新录音。')
            return
        self.summary_running = True
        self.summary_stop.clear()
        self.minutes_status.set('正在调用 DeepSeek 生成纪要，原始转写已保存…')
        for widget in [self.summary_button, self.import_button, self.record_button, self.start_button]:
            widget.configure(state='disabled')
        for widget in [self.mode_choice, self.mic_choice, self.system_choice, self.echo_checkbox]:
            widget.configure(state='disabled')
        self.auto_checkbox.configure(state='disabled')
        text, output = self.latest_text, self.latest_output
        def work():
            from .minutes import generate_minutes
            try:
                result = generate_minutes(text, output,
                                          lambda message: self.events.put({'kind': 'minutes_progress', 'message': message}),
                                          self.summary_stop)
                self.events.put({'kind': 'minutes_done', 'result': result})
            except Exception as error:
                self.events.put({'kind': 'minutes_error', 'message': str(error)})
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event['kind']
            if kind == 'minutes_progress':
                self.minutes_status.set(event['message'])
            elif kind in ('minutes_done', 'minutes_error'):
                self.summary_running = False
                for widget in [self.summary_button, self.import_button, self.record_button, self.start_button, self.auto_checkbox]:
                    widget.configure(state='normal')
                self.mode_choice.configure(state='readonly')
                self.mic_choice.configure(state='readonly')
                online = self.meeting_mode.get().startswith('线上')
                self.system_choice.configure(state='readonly' if online else 'disabled')
                self.echo_checkbox.configure(state='normal' if online else 'disabled')
                if kind == 'minutes_done':
                    result = event['result']
                    self.set_text(self.minutes_text, result['text'])
                    self.minutes_status.set('纪要草稿已保存：' + result['path'])
                    self.notebook.select(self.minutes_tab)
                else:
                    self.minutes_status.set('纪要未生成：' + event['message'] + '；可点击“生成/重试纪要”，无需重新录音。')
            elif kind == 'ready':
                self.status.set('识别服务已就绪，正在按真实时间送入音频…')
            elif kind == 'connecting':
                self.status.set('正在连接云端服务，麦克风尚未开始录音…')
            elif kind == 'recording':
                self.status.set('录音中，请讲话；点击“结束并保存”停止。')
            elif kind == 'level':
                self.level['value'] = max(0, min(60, event['dbfs'] + 60))
            elif kind == 'source_levels':
                self.source_levels.set(f"麦克风 {event['microphone_dbfs']:.0f} dBFS · 系统 {event['system_dbfs']:.0f} dBFS")
            elif kind == 'live_progress':
                seconds = int(event['position_s'])
                self.status.set(f'录音中 · {seconds // 60:02d}:{seconds % 60:02d} · 点击“结束并保存”停止')
            elif kind == 'finishing':
                self.status.set('音频已发送，正在等待云端最终确认…')
            elif kind == 'progress':
                self.progress['value'] = 100 * event['position_s'] / event['duration_s']
                self.status.set(f"已输入 {event['position_s']:.1f} / {event['duration_s']:.1f} 秒")
            elif kind == 'text':
                self.set_text(self.transcript, event['text'])
                # Only the unconfirmed tail is gray; preserve unchanged characters.
                self.transcript.tag_remove('pending', '1.0', 'end')
                if self.selected_backend == 'cloud' and not event['final']:
                    cursor = 0
                    for segment in event.get('utterances', []):
                        if not segment.get('definite'):
                            break
                        text = segment.get('text') or ''
                        index = event['text'].find(text, cursor)
                        if index < 0:
                            break
                        cursor = index + len(text)
                    self.transcript.tag_add('pending', f'1.0+{cursor}c', 'end')
                tag = '结束结果' if event['final'] else '中间结果'
                self.set_text(self.log, f"{event['elapsed_s']:.2f}s · {tag} · {event['text'][-160:]}\n", append=True)
                self.log.configure(state='normal')
                if int(self.log.index('end-1c').split('.')[0]) > 150:
                    self.log.delete('1.0', '50.0')
                self.log.configure(state='disabled')
            elif kind in ('done', 'error'):
                self.running = False
                for widget in [self.start_button, self.record_button, self.browse, self.entry]:
                    widget.configure(state='normal')
                self.stop_button.configure(state='disabled')
                self.backend_choice.configure(state='readonly')
                self.mic_choice.configure(state='readonly')
                self.mode_choice.configure(state='readonly')
                online = self.meeting_mode.get().startswith('线上')
                self.system_choice.configure(state='readonly' if online else 'disabled')
                self.echo_checkbox.configure(state='normal' if online else 'disabled')
                self.level['value'] = 0
                self.import_button.configure(state='normal')
                if kind == 'error':
                    self.status.set('测试失败：' + event['message'])
                    self.metrics.set('请检查网络、服务额度、.env 配置和音频格式。')
                else:
                    report = event['report']
                    label = '录音已保存；' if self.is_live else ('已停止；' if report.get('cancelled') else '测试完成；')
                    self.status.set(label + '报告：' + event['path'])
                    first = report['first_text_from_stream_start_s']
                    if 'compute_rtf' in report:
                        detail = f"计算 RTF：{report['compute_rtf']:.3f}" if report['compute_rtf'] is not None else '计算 RTF：无'
                    else:
                        wait = report.get('finalization_wait_s')
                        detail = f'最终确认等待：{wait:.2f}s' if wait is not None else '最终确认等待：无'
                    count = report.get('updates', report.get('partial_updates_before_audio_end', 0))
                    self.metrics.set(f"首字：{f'{first:.2f}s' if first is not None else '无'}（从输入开始计）  |  {detail}  |  结果更新：{count} 次")
                    self.latest_text = report.get('final_text', self.transcript.get('1.0', 'end').strip())
                    self.latest_output = Path(event['path']).resolve().parent
                    if self.latest_text.strip():
                        self.summary_button.configure(state='normal')
                        if self.is_live and self.auto_minutes.get() and not self.closing and report.get('completed', True):
                            self.generate_current()
                        else:
                            self.minutes_status.set('转写已保存，可点击“生成/重试纪要”。')
                    else:
                        self.minutes_status.set('没有有效转写文字，已跳过纪要生成。')
        if self.closing and not self.running and not self.summary_running:
            self.root.destroy()
            return
        self.root.after(100, self.poll)

    def close(self):
        self.closing = True
        self.stop.set()
        self.summary_stop.set()
        if self.summary_running:
            self.minutes_status.set('正在结束当前 DeepSeek 请求并保存已完成结果…')
        if self.running:
            self.status.set('正在结束识别并保存结果…')

if __name__ == '__main__':
    window = tk.Tk()
    Demo(window)
    window.mainloop()
