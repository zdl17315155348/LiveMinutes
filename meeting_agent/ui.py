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
        from .ui_theme import BG, INK, MUTED, BLUE, TEAL, FONT, Card, ActionButton, Waveform, Selection, SlimScrollbar, setup_theme
        setup_theme(root)
        root.title('LiveMinutes · 会议记录助手')
        root.geometry('1240x850')
        root.minsize(1040, 780)
        self.timer = tk.StringVar(value='00:00:00')
        self.session_state = tk.StringVar(value='准备开始')
        self.connection = tk.StringVar(value='等待开始')
        self.status = tk.StringVar(value='点击开始录音，将音频发送至豆包进行实时识别。')
        self.minutes_status = tk.StringVar(value='会议纪要将在录音结束后生成 · DeepSeek')
        self.metrics = tk.StringVar(value='')
        self.source_levels = tk.StringVar(value='线下模式只录麦克风')
        self.follow = tk.BooleanVar(value=True)
        self.elapsed_seconds = 0
        self.wave_target = 0
        self.capture_active = False
        self.animation_job = None
        self.poll_job = None
        header = tk.Frame(root, bg='white', padx=28, pady=14)
        header.pack(fill='x')
        tk.Label(header, text='▥', bg='white', fg=BLUE, font=(FONT, 25, 'bold')).pack(side='left', padx=(0, 12))
        brand = tk.Frame(header, bg='white')
        brand.pack(side='left')
        tk.Label(brand, text='LiveMinutes', bg='white', fg=INK, font=(FONT, 15, 'bold')).pack(anchor='w')
        tk.Label(brand, text='会议记录助手', bg='white', fg=MUTED, font=(FONT, 9)).pack(anchor='w')
        self.settings_button = ttk.Button(header, text='⚙  设置', command=self.open_settings)
        self.settings_button.pack(side='right')
        recording_controls = tk.Frame(root, bg='white', padx=24, pady=12)
        recording_controls.pack(side='bottom', fill='x')
        tk.Label(recording_controls, text='录音控制', bg='white', fg=MUTED,
                 font=(FONT, 10)).pack(side='left')
        self.stop_button = ActionButton(recording_controls, text='■  结束录音',
                                        command=self.stop_recording, fill='#DC4264',
                                        foreground='white', state='disabled')
        self.stop_button.pack(side='right', padx=(12, 0))
        self.record_button = ActionButton(recording_controls, text='●  开始录音',
                                          command=lambda: self.start(live=True),
                                          fill=BLUE, foreground='white')
        self.record_button.pack(side='right')
        workspace = tk.Frame(root, bg=BG, padx=24, pady=20)
        workspace.pack(fill='both', expand=True)
        workspace.columnconfigure(1, weight=1)
        workspace.rowconfigure(0, weight=1)
        sidebar = tk.Frame(workspace, bg=BG, width=310)
        sidebar.grid(row=0, column=0, sticky='ns', padx=(0, 20))
        sidebar.pack_propagate(False)
        side_canvas = tk.Canvas(sidebar, bg=BG, width=300, highlightthickness=0)
        side_scroll = SlimScrollbar(sidebar, command=side_canvas.yview)
        side_canvas.configure(yscrollcommand=side_scroll.set)
        side_canvas.pack(side='left', fill='both', expand=True)
        left = tk.Frame(side_canvas, bg=BG, width=300)
        side_window = side_canvas.create_window(0, 0, window=left, anchor='nw', width=300)
        def resize_sidebar(event=None):
            side_canvas.configure(scrollregion=side_canvas.bbox('all'))
            if left.winfo_reqheight() > side_canvas.winfo_height():
                side_scroll.pack(side='right', fill='y')
            else:
                side_scroll.pack_forget()
                side_canvas.yview_moveto(0)
        left.bind('<Configure>', resize_sidebar)
        side_canvas.bind('<Configure>', lambda e: (side_canvas.itemconfigure(side_window, width=e.width), resize_sidebar()))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        recorder = Card(left, color=BLUE, signature=True, height=210)
        recorder.grid(row=0, column=0, sticky='ew', pady=(0, 14))
        tk.Label(recorder.body, textvariable=self.session_state, bg=BLUE, fg='white', font=(FONT, 12)).pack(anchor='w')
        tk.Label(recorder.body, textvariable=self.timer, bg=BLUE, fg='white', font=('Segoe UI', 34, 'bold')).pack(anchor='w', pady=(8, 0))
        self.waveform = Waveform(recorder.body)
        self.waveform.pack(fill='x', pady=(0, 8))
        settings_card = Card(left, height=320, padding=20)
        settings_card.grid(row=1, column=0, sticky='ew')
        self.device_card = settings_card
        body = settings_card.body
        tk.Label(body, text='录音设置', bg='white', fg=INK, font=(FONT, 14, 'bold')).pack(anchor='w', pady=(0, 12))
        self.meeting_mode = tk.StringVar(value='线下会议（麦克风）')
        mode_row = tk.Frame(body, bg='#F2F3F8')
        mode_row.pack(fill='x', pady=(0, 12))
        self.mode_buttons = []
        for label, value in [('线下会议', '线下会议（麦克风）'), ('线上会议', '线上会议（麦克风＋系统声音）')]:
            button = Selection(mode_row, text=label, value=value, variable=self.meeting_mode,
                               command=self.change_meeting_mode, width=120)
            button.pack(side='left', fill='x', expand=True)
            self.mode_buttons.append(button)
        # Retain the controller's selection interface; the visible selector is segmented.
        self.mode_choice = ttk.Combobox(body, textvariable=self.meeting_mode, state='readonly')
        tk.Label(body, text='麦克风', bg='white', fg=MUTED, font=(FONT, 9)).pack(anchor='w', pady=(0, 4))
        try:
            from .microphone import devices
            self.microphones = devices()
        except Exception:
            self.microphones = [{'id': -1, 'name': '系统默认麦克风'}]
        self.mic_choice = ttk.Combobox(body, state='readonly', values=[d['name'] for d in self.microphones], width=22)
        self.mic_choice.current(0)
        self.mic_choice.pack(fill='x')
        self.level = ttk.Progressbar(body, maximum=60)
        self.level.pack(fill='x', pady=(14, 5))
        tk.Label(body, textvariable=self.source_levels, bg='white', fg=MUTED, font=(FONT, 8), wraplength=250, justify='left').pack(anchor='w')
        self.offline_microphones = list(self.microphones)
        self.online_ready = False
        self.loopbacks = [{'id': -1, 'name': '系统默认播放设备'}]
        self.system_row = tk.Frame(body, bg='white')
        tk.Label(self.system_row, text='系统声音', bg='white', fg=MUTED, font=(FONT, 9)).pack(anchor='w', pady=(10, 4))
        self.system_choice = ttk.Combobox(self.system_row, state='disabled', width=22, values=['系统默认播放设备'])
        self.system_choice.current(0)
        self.system_choice.pack(fill='x')
        self.echo_enabled = tk.BooleanVar(value=True)
        self.echo_checkbox = Selection(self.system_row, text='抑制外放回声', variable=self.echo_enabled, state='disabled', width=250)
        self.echo_checkbox.pack(anchor='w')
        self.auto_checkbox = Selection(body, text='结束后自动生成纪要', variable=self.auto_minutes, width=250)
        self.auto_checkbox.pack(anchor='w', pady=(10, 0))
        links = tk.Frame(left, bg=BG)
        links.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        self.import_button = ActionButton(links, text='↗  导入已有转写', command=self.import_transcript, fill=BG)
        self.import_button.pack(fill='x')
        ActionButton(links, text='▥  音频文件测试', command=self.open_tools, fill=BG).pack(fill='x')
        right = tk.Frame(workspace, bg=BG)
        right.grid(row=0, column=1, sticky='nsew')
        tk.Label(right, text='当前会议', bg=BG, fg=INK, font=(FONT, 26, 'bold')).pack(anchor='w')
        tk.Label(right, text='实时记录讨论，留住每个重点', bg=BG, fg=MUTED, font=(FONT, 11)).pack(anchor='w', pady=(3, 18))
        tab_row = tk.Frame(right, bg=BG)
        tab_row.pack(fill='x', pady=(0, 14))
        self.tab_buttons = []
        for index, title in enumerate(('实时转写', '会议纪要')):
            button = ActionButton(tab_row, text=title, command=lambda i=index: self.notebook.select(i), width=130)
            button.pack(side='left', padx=(0, 10))
            self.tab_buttons.append(button)
        tk.Label(tab_row, text='豆包语音识别', bg=BG, fg=BLUE, font=(FONT, 9)).pack(side='right', padx=16)
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill='both', expand=True)
        transcript_tab = tk.Frame(self.notebook, bg=BG)
        self.minutes_tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(transcript_tab, text='实时转写')
        self.notebook.add(self.minutes_tab, text='会议纪要')
        def update_tabs(event=None):
            selected = self.notebook.index(self.notebook.select())
            for index, button in enumerate(self.tab_buttons):
                button.fill = BLUE if index == selected else '#E6E6F3'
                button.foreground = 'white' if index == selected else MUTED
                button._draw()
        self.notebook.bind('<<NotebookTabChanged>>', update_tabs)
        for tab, title, attr in [(transcript_tab, '实时转写', 'transcript'), (self.minutes_tab, '会议纪要', 'minutes_text')]:
            card = Card(tab, signature=True, padding=22)
            card.pack(fill='both', expand=True)
            heading = tk.Frame(card.body, bg='white')
            heading.pack(fill='x', pady=(0, 16))
            tk.Label(heading, text=title, bg='white', fg=INK, font=(FONT, 15, 'bold')).pack(side='left')
            if attr == 'transcript':
                tk.Label(heading, textvariable=self.connection, bg='white', fg=TEAL, font=(FONT, 9)).pack(side='right', padx=(0, 16))
            else:
                tk.Label(heading, text='DeepSeek', bg='white', fg=BLUE, font=(FONT, 10)).pack(side='right', padx=(0, 16))
            tk.Frame(card.body, bg='#ECEEF5', height=1).pack(fill='x', pady=(0, 12))
            text_row = tk.Frame(card.body, bg='white')
            text_row.pack(fill='both', expand=True)
            widget = tk.Text(text_row, wrap='word', state='disabled', padx=6, pady=8,
                             bg='white', fg=INK, relief='flat', bd=0, highlightthickness=0,
                             font=(FONT, 12), spacing1=6, spacing3=12, height=6, width=1,
                             selectbackground='#DFDCFF', selectforeground=INK, insertbackground=BLUE)
            scrollbar = SlimScrollbar(text_row, command=widget.yview)
            widget.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            widget.pack(fill='both', expand=True)
            setattr(self, attr, widget)
            if attr == 'transcript':
                self.transcript.tag_configure('pending', foreground='#9298B3')
                Selection(card.body, text='跟随最新内容', variable=self.follow,
                          command=self.follow_latest, width=175).pack(anchor='e', pady=(8, 0))
            else:
                self.summary_button = ttk.Button(card.body, text='生成 / 重试纪要', command=self.generate_current, state='disabled')
                self.summary_button.pack(anchor='e', pady=(8, 0))
        note = tk.Frame(right, bg='#EAE8FC', padx=16, pady=12)
        note.pack(fill='x', pady=(12, 8))
        self.minutes_status_label = tk.Label(note, textvariable=self.minutes_status, bg='#EAE8FC', fg=BLUE,
                                             justify='left', anchor='w', wraplength=650, font=(FONT, 10))
        self.minutes_status_label.pack(fill='x')
        self.status_label = tk.Label(right, textvariable=self.status, bg=BG, fg=MUTED,
                                    justify='left', anchor='w', wraplength=650, font=(FONT, 9))
        self.status_label.pack(fill='x')
        right.bind('<Configure>', lambda e: [label.configure(wraplength=max(220, e.width-40))
                                             for label in (self.minutes_status_label, self.status_label)])
        self.tools = tk.Toplevel(root)
        self.tools.withdraw()
        self.tools.title('LiveMinutes · 音频文件测试')
        self.tools.geometry('720x520')
        self.tools.protocol('WM_DELETE_WINDOW', self.tools.withdraw)
        tool_frame = ttk.Frame(self.tools, padding=24)
        tool_frame.pack(fill='both', expand=True)
        ttk.Label(tool_frame, text='音频文件测试', font=(FONT, 17, 'bold')).pack(anchor='w', pady=(0, 14))
        self.backend_choice = ttk.Combobox(tool_frame, textvariable=self.backend, state='readonly', values=['云端 · 豆包二遍识别', '本地 · CPU 对照'])
        self.backend_choice.pack(anchor='w', pady=(0, 14))
        self.path = tk.StringVar(value=str(ROOT / 'data/models/streaming-paraformer/test_wavs/0.wav'))
        self.entry = ttk.Entry(tool_frame, textvariable=self.path)
        self.entry.pack(fill='x')
        row = ttk.Frame(tool_frame)
        row.pack(fill='x', pady=10)
        self.browse = ttk.Button(row, text='选择 WAV', command=self.choose)
        self.browse.pack(side='left')
        self.start_button = ttk.Button(row, text='测试所选音频文件', command=self.start)
        self.start_button.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(tool_frame, maximum=100)
        self.progress.pack(fill='x', pady=10)
        ttk.Label(tool_frame, textvariable=self.metrics, wraplength=640).pack(anchor='w')
        self.log = tk.Text(tool_frame, height=8, state='disabled', wrap='word', relief='flat', bg=BG, padx=10, pady=10)
        self.log.pack(fill='both', expand=True, pady=(12, 0))
        ttk.Label(tool_frame, text='云端测试会将音频发送至豆包并消耗额度。', foreground=MUTED).pack(anchor='w', pady=(10, 0))
        self._empty_hint()
        self.minutes_text.tag_configure('empty', foreground=MUTED)
        self.set_text(self.minutes_text, '专注讨论，纪要稍后就绪。\n\n结束录音后，将根据完整转写生成会议纪要。')
        self.minutes_text.tag_add('empty', '1.0', 'end')
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Destroy>', self._cleanup, add='+')
        self.poll_job = root.after(100, self.poll)
        self.animation_job = root.after(50, self.animate)

    def _cleanup(self, event):
        if event.widget == self.root:
            for job in (self.animation_job, self.poll_job):
                if job:
                    self.root.after_cancel(job)

    def _empty_hint(self):
        self.transcript.tag_configure('empty', foreground='#9298B3')
        self.set_text(self.transcript, '准备好，开始一场清晰的讨论。\n\n点击左侧“开始录音”，讲话内容将在这里持续显示。')
        self.transcript.tag_add('empty', '1.0', 'end')

    def follow_latest(self):
        if self.follow.get():
            self.transcript.see('end')

    def open_tools(self):
        self.tools.deiconify()
        self.tools.lift()

    def animate(self):
        busy = self.running or self.summary_running
        for button in self.mode_buttons:
            button.configure(state='disabled' if busy else 'normal')
        self.settings_button.configure(state='disabled' if busy else 'normal')
        stopping = self.running and self.stop.is_set()
        self.session_state.set('正在结束…' if stopping else ('正在录音' if self.capture_active and self.running else
                               ('正在转写' if self.running else ('正在生成纪要' if self.summary_running else '准备开始'))))
        stop_label = '■  结束录音并生成纪要' if self.auto_minutes.get() and getattr(self, 'is_live', False) else '■  结束录音并保存'
        self.stop_button.configure(text=stop_label)
        seconds = int(self.elapsed_seconds)
        self.timer.set(f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}')
        self.waveform.draw(self.wave_target if self.capture_active and self.running else 0, self.capture_active and self.running)
        if not self.closing:
            self.animation_job = self.root.after(50, self.animate)

    def choose(self):
        path = filedialog.askopenfilename(filetypes=[('PCM WAV', '*.wav')])
        if path:
            self.path.set(path)

    def open_settings(self):
        if self.running or self.summary_running:
            return
        from .settings import show_settings
        show_settings(self.root, lambda: self.minutes_status.set('API 配置已保存，可开始录音或重试生成纪要。'))

    def change_meeting_mode(self, event=None):
        if self.running or self.summary_running:
            return
        online = self.meeting_mode.get().startswith('线上')
        if online:
            try:
                from .online_audio import online_devices
                self.microphones, self.loopbacks = online_devices()
                self.system_choice.configure(values=[d['name'] for d in self.loopbacks], state='readonly')
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
        self.mic_choice.configure(values=[d['name'] for d in self.microphones])
        self.mic_choice.current(0)
        if online:
            self.system_row.pack(fill='x', before=self.auto_checkbox)
        else:
            self.system_row.pack_forget()
        self.device_card.configure(height=430 if online else 320)

    def set_text(self, widget, text, append=False):
        at_bottom = widget.yview()[1] >= .98
        widget.configure(state='normal')
        widget.tag_remove('empty', '1.0', 'end')
        if not append:
            previous = widget.get('1.0', 'end-1c')
            same = len(os.path.commonprefix([previous, text]))
            widget.delete(f'1.0+{same}c', 'end')
            widget.insert('end', text[same:])
        else:
            widget.insert('end', text)
        if widget == self.minutes_text:
            widget.tag_configure('heading', foreground='#3933D8', font=('Microsoft YaHei UI', 16, 'bold'), spacing1=12, spacing3=10)
            widget.tag_configure('subheading', foreground='#17262A', font=('Microsoft YaHei UI', 12, 'bold'), spacing1=10)
            for tag in ('heading', 'subheading'):
                widget.tag_remove(tag, '1.0', 'end')
            for number, line in enumerate(text.splitlines(), 1):
                if line.startswith('# '):
                    widget.tag_add('heading', f'{number}.0', f'{number}.end')
                elif line.startswith(('## ', '### ')):
                    widget.tag_add('subheading', f'{number}.0', f'{number}.end')
        if widget != self.transcript or (self.follow.get() and at_bottom):
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
        self.capture_active = False
        self.elapsed_seconds = 0
        self.wave_target = 0
        self.connection.set('正在连接…')
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
            self.minutes_status.set('请在右上角设置中填写 DeepSeek Key，再点“生成 / 重试纪要”；无需重新录音。')
            return
        self.notebook.select(self.minutes_tab)
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
                self.connection.set('●  识别已连接')
                self.status.set('识别服务已就绪，正在按真实时间送入音频…')
            elif kind == 'connecting':
                self.status.set('正在连接云端服务，麦克风尚未开始录音…')
            elif kind == 'recording':
                self.capture_active = True
                self.connection.set('●  识别已连接')
                self.status.set('录音中，请讲话；点击“结束并保存”停止。')
            elif kind == 'level':
                self.level['value'] = max(0, min(60, event['dbfs'] + 60))
                self.wave_target = max(0, min(1, (event['dbfs']+60)/60))
                self.elapsed_seconds = event.get('position_s', self.elapsed_seconds)
            elif kind == 'source_levels':
                self.source_levels.set(f"麦克风 {event['microphone_dbfs']:.0f} dBFS · 系统 {event['system_dbfs']:.0f} dBFS")
            elif kind == 'live_progress':
                self.elapsed_seconds = event['position_s']
                seconds = int(event['position_s'])
                self.status.set(f'录音中 · {seconds // 60:02d}:{seconds % 60:02d} · 点击“结束并保存”停止')
            elif kind == 'finishing':
                self.capture_active = False
                self.connection.set('等待最终确认…')
                self.status.set('音频已发送，正在等待云端最终确认…')
            elif kind == 'progress':
                self.elapsed_seconds = event['position_s']
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
                self.capture_active = False
                self.wave_target = 0
                self.connection.set('识别失败' if kind == 'error' else '转写已保存')
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
            if self.animation_job:
                self.root.after_cancel(self.animation_job)
            self.root.destroy()
            return
        self.poll_job = self.root.after(100, self.poll)

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
    app = Demo(window)
    from .settings import needs_setup
    if needs_setup():
        window.after(200, app.open_settings)
    window.mainloop()
