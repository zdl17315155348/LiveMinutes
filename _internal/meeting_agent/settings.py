"""Local masked API key editor; no network requests and no secret logging."""
import tkinter as tk
from tkinter import ttk
import webbrowser

from dotenv import dotenv_values, set_key
from .paths import ROOT

def needs_setup():
    values = dotenv_values(ROOT / '.env', encoding='utf-8-sig')
    return not (values.get('VOLCENGINE_ASR_API_KEY') or '').strip()

def save_keys(asr_key, deepseek_key):
    keys = {'VOLCENGINE_ASR_API_KEY': asr_key.strip(), 'DEEPSEEK_API_KEY': deepseek_key.strip()}
    if not keys['VOLCENGINE_ASR_API_KEY']:
        raise ValueError('请填写豆包 API Key。')
    if any(any(character.isspace() for character in value) for value in keys.values()):
        raise ValueError('API Key 不能包含空格或换行。')
    path = ROOT / '.env'
    for name, value in keys.items():
        set_key(path, name, value, quote_mode='always', encoding='utf-8-sig')
    values = dotenv_values(path, encoding='utf-8-sig')
    for name, default in [('VOLCENGINE_ASR_RESOURCE_ID', 'volc.seedasr.sauc.duration'),
                          ('DEEPSEEK_MODEL', 'deepseek-flash')]:
        if not values.get(name):
            set_key(path, name, default, quote_mode='always', encoding='utf-8-sig')

def show_settings(parent, on_saved=None):
    dialog = tk.Toplevel(parent)
    dialog.title('LiveMinutes · API 设置')
    dialog.transient(parent)
    dialog.resizable(False, False)
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='填写自己的 API Key，即可开始使用。').pack(anchor='w', pady=(0, 12))
    values = dotenv_values(ROOT / '.env', encoding='utf-8-sig')
    fields = {}
    for label, name, url in [
        ('豆包 API Key（实时转写，必填）', 'VOLCENGINE_ASR_API_KEY', 'https://console.volcengine.com/speech/new/experience/asr'),
        ('DeepSeek API Key（自动纪要，可稍后填写）', 'DEEPSEEK_API_KEY', 'https://platform.deepseek.com/')]:
        ttk.Label(frame, text=label).pack(anchor='w')
        variable = tk.StringVar(value=values.get(name) or '')
        entry = ttk.Entry(frame, textvariable=variable, show='*', width=60)
        entry.pack(fill='x', pady=(4, 4))
        fields[name] = variable
        ttk.Button(frame, text='打开申请页面', command=lambda target=url: webbrowser.open(target)).pack(anchor='w', pady=(0, 12))
    ttk.Label(frame, text='密钥仅保存到本机项目目录的 .env，该文件已被 Git 忽略。').pack(anchor='w')
    status = tk.StringVar()
    ttk.Label(frame, textvariable=status, foreground='#b91c1c').pack(anchor='w', pady=8)
    def save():
        try:
            save_keys(fields['VOLCENGINE_ASR_API_KEY'].get(), fields['DEEPSEEK_API_KEY'].get())
            if on_saved:
                on_saved()
            dialog.destroy()
        except ValueError as error:
            status.set(str(error))
        except Exception:
            status.set('无法保存本机配置，请检查项目文件夹是否可写。')
    ttk.Button(frame, text='保存并返回', command=save).pack(anchor='e')
    dialog.grab_set()
    dialog.focus_set()
    return dialog
