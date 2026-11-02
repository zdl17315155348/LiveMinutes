# LiveMinutes

Windows 会议助手：豆包实时转写，DeepSeek 生成会议纪要。

## 功能

- 线下麦克风录音、线上麦克风与系统声音双路录音。
- 实时转写、标点恢复、回声抑制。
- 自动生成纪要，支持失败重试和导入已有转写。

## 使用

便携版：解压完整的 `LiveMinutes-Windows.zip`，双击 `LiveMinutes.exe`，无需安装 Python。首次在“设置”填写 API Key。请保留同目录的 `_internal` 文件夹；纪要输出到 exe 所在目录的 `data/minutes/`。

源码运行：

需要 Windows 10/11、[64位 Python 3.11](https://www.python.org/downloads/windows/)和网络连接。安装 Python 时勾选 **Add python.exe to PATH**。

```powershell
git clone https://github.com/zdl17315155348/LiveMinutes.git
cd LiveMinutes
```

1. 双击 `start_meeting.bat`，首次自动安装依赖。
2. 在“API 设置”中填写 Key：
   - [豆包控制台](https://console.volcengine.com/speech/new/experience/asr)：开通“豆包流式语音识别模型 2.0 小时版”，获取 API Key。
   - [DeepSeek 开放平台](https://platform.deepseek.com/)：获取 API Key。
3. 选择会议模式和麦克风；线上模式另选会议软件使用的扬声器或耳机。
4. 点击“开始录音”，结束时点击“结束录音并生成会议纪要”，在“会议纪要”页查看结果。

已有录音：点击“导入音频生成纪要”，选择 M4A、WAV 或 MP3，自动转换、转写并生成纪要。首次启动会安装转换组件；当前转写耗时接近音频时长。

音频发送至豆包、文字发送至 DeepSeek，按账号额度计费。线上模式会录入所选播放设备上的全部声音。

## 输出

- 录音和转写：`data/recordings/`
- 会议纪要：`data/minutes/`，如 `20261102at143005.md`。
