# LiveMinutes

Windows 本地会议助手，使用豆包实时语音识别和 DeepSeek 生成会议纪要。

## 功能

- **线下会议**：采集麦克风，实时显示带标点的转写文字。
- **线上会议**：同时采集麦克风和系统声音，支持回声抑制。
- **会议纪要**：录音结束后自动生成纪要，支持失败重试及导入已有转写。
- **本机保存**：保存录音、转写和 Markdown 纪要。

## 使用方法

### 1. 下载并启动

需要 Windows 10/11、Python 3.11（包含 Tcl/Tk）和网络连接。

下载或克隆本仓库：

```powershell
git clone https://github.com/zdl17315155348/LiveMinutes.git
cd LiveMinutes
```

双击 **`start_meeting.bat`**。首次会自动创建运行环境并安装依赖，需要联网；后续直接启动。依赖清单变化时会自动更新，安装失败后可检查网络再双击重试。

没有安装Python时，启动器会提示安装[64位Python 3.11](https://www.python.org/downloads/windows/)，安装时勾选“Add python.exe to PATH”。当前不是免安装的独立exe。

### 2. 填写 API Key

- **豆包语音识别**：进入[火山引擎语音控制台](https://console.volcengine.com/speech/new/experience/asr)，开通“豆包流式语音识别模型 2.0 小时版”，在控制台的 API Key 管理中获取密钥。
- **DeepSeek**：在 [DeepSeek 开放平台](https://platform.deepseek.com/)获取 API Key。

首次启动会弹出 **API 设置**，填写并保存即可。之后也可以点击主界面的“API 设置”。豆包Key必填，DeepSeek Key可稍后填写。

程序会自动将配置保存到**项目根目录的 `.env`**；也支持用文本编辑器手动填写：

```dotenv
VOLCENGINE_ASR_API_KEY=填写你的豆包APIKey
VOLCENGINE_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DEEPSEEK_API_KEY=填写你的DeepSeekAPIKey
DEEPSEEK_MODEL=deepseek-flash
```

`.env` 用于本机配置，已加入 Git 忽略规则，请勿上传或分享。仓库中的 `.env.example` 只提供空密钥模板。首次安装时复制一次即可，已有 `.env` 时不要覆盖。

### 3. 开始会议

双击 `start_meeting.bat`：

1. 选择线下或线上会议模式，并选择麦克风。
2. 线上模式另选会议软件实际使用的扬声器或耳机，默认开启回声抑制。
3. 点击“开始录音（云端）”，结束后点击“结束并保存”。
4. 在“会议纪要”页查看结果；也可点击“生成/重试纪要”或“从已有转写生成”。

线上模式会采集所选播放设备上的全部声音，包括其他应用提示音。音频发送至豆包识别，文字发送至 DeepSeek 生成纪要，按各自账号额度计费。

### 4. 查看文件

- 录音与转写：`data/recordings/`。
- 会议纪要：`data/minutes/`，文件名如 `261028+16：30：05.md`（北京时间，使用全角冒号以兼容 Windows）。
