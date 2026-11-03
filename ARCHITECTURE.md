# LiveMinutes 架构

依赖方向：Application → Domain；Adapter → Application 接口与 Domain；Composition Root 组装所有实现。

| 目录 | 职责 |
| --- | --- |
| `domain/` | Conversation、Context、Session、Tool 等纯业务对象 |
| `application/ports/` | 模型、会话存储、音频源处理、转写、纪要生成与导出接口 |
| `application/use_cases/` | 录音/导入编排、会话状态、分段提取与递归合并 |
| `application/agent/` | 有取消、工具白名单与轮数上限的独立 Agent loop |
| `adapters/audio/` | Windows 采集、回声处理、FFmpeg 转换 |
| `adapters/transcription/` | 豆包 WebSocket 协议、本地识别 |
| `adapters/models/` | DeepSeek HTTP 协议与 ModelClient 实现 |
| `adapters/storage/` | 会话 JSON、生成缓存、生成报告和文件落盘 |
| `adapters/tools/` | 按片段读取和搜索会议原文 |
| `adapters/desktop/` | Tkinter 展示、后台任务及 UI 事件消费 |
| `bootstrap/` | 配置路径与唯一组装入口 `composition_root.py` |

## 启动与替换

源码入口为 `python .`。旧的 `python -m ui`、原模块导入路径保留兼容入口，实际实现已经迁入各层。

`build_services()` 注入 AudioConverter、Transcriber、MinutesGenerator、ModelClient 工厂及 SessionStore。新增实现应放入 Adapter，在组装根切换；Application 不应导入具体适配器。

会话记录位于 `data/sessions/`，会议录音、转写和纪要的位置及格式沿用原行为。所有会话与本机 Key 仍不提交 Git。

## 纪要策略与 Agent loop

桌面程序默认继续使用确定性的分段提取与合并策略，保留缓存和失败重试。AgentLoop 是独立的应用能力，接受 AgentModel 和 ToolExecutor 接口，目前通过模拟模型验证；DeepSeek 的自主工具调用协议尚未接入桌面默认流程。它不是实时音频收发循环的替代品。

## 验证

`python -m unittest discover -s tests -q` 包含领域/应用依赖检查、工具循环上限与取消、会话存储和既有协议、音频、纪要回归。桌面路由以模拟数据验证，不调用麦克风或付费 API。

Windows 构建：安装 `requirements-build.txt` 后运行 `python scripts/build_windows.py`，再对产物执行 `LiveMinutes.exe --self-check`。构建产物的根目录 exe 与 `_internal` 必须一起更新；不得复制 `.env` 或 `data` 到发布范围。
