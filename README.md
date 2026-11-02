# LiveMinutes

Windows 会议助手：豆包实时转写，DeepSeek 生成会议纪要。

## 功能

- 线下麦克风录音、线上麦克风与系统声音双路录音。
- 实时转写、标点恢复、回声抑制。
- 自动生成纪要，支持失败重试和导入已有转写。

## 使用

需要 Windows 10/11 64 位和网络连接。

```powershell
git clone https://github.com/zdl17315155348/LiveMinutes.git
cd LiveMinutes
```

1. 双击根目录 `LiveMinutes.exe`，无需安装 Python；请保留 `_internal` 文件夹。
2. 在“设置”填写自己的 API Key：
   - [豆包控制台](https://console.volcengine.com/speech/new/experience/asr)：开通流式语音识别，获取 API Key。
   - [DeepSeek 开放平台](https://platform.deepseek.com/)：获取 API Key。
3. 选择会议模式和麦克风，点击“开始录音”，结束时点击“结束录音并生成会议纪要”。

已有录音：点击“导入音频生成纪要”，支持 M4A、WAV、MP3 等格式。当前转写耗时接近音频时长。

源码启动也可双击 `start_meeting.bat`，需要安装 64 位 Python 3.11，首次自动安装依赖。

音频发送至豆包、文字发送至 DeepSeek，按账号额度计费。线上模式会录入所选播放设备上的全部声音。

## 输出

- 录音和转写：`data/recordings/`
- 会议纪要：`data/minutes/`，如 `20261102at143005.md`。
