"""Bounded tool loop, independent of model protocols and tool implementations."""
from dataclasses import dataclass, field
from typing import Protocol
from domain.conversation import Conversation, Message
from domain.tool import Tool, ToolCall, ToolResult


@dataclass
class ModelTurn:
    content: str = ''
    calls: list[ToolCall] = field(default_factory=list)


class AgentModel(Protocol):
    def turn(self, conversation: Conversation, tools: list[Tool]) -> ModelTurn: ...


class ToolExecutor(Protocol):
    def execute(self, call: ToolCall) -> ToolResult: ...


class AgentLoop:
    def __init__(self, model: AgentModel, executor: ToolExecutor, tools: list[Tool], max_turns=6):
        if max_turns < 1:
            raise ValueError('max_turns must be positive')
        self.model, self.executor, self.tools, self.max_turns = model, executor, tools, max_turns

    def run(self, conversation, stop):
        allowed = {tool.name for tool in self.tools}
        for _ in range(self.max_turns):
            if stop.is_set():
                raise RuntimeError('Agent 已取消')
            turn = self.model.turn(conversation, self.tools)
            if not turn.calls:
                if not turn.content.strip():
                    raise RuntimeError('模型返回空结果')
                conversation.messages.append(Message('assistant', turn.content))
                return turn.content
            if len(turn.calls) > 8:
                raise RuntimeError('单轮工具调用数量超限')
            conversation.messages.append(Message('assistant', turn.content))
            for call in turn.calls:
                if stop.is_set():
                    raise RuntimeError('Agent 已取消')
                if call.name not in allowed:
                    raise RuntimeError('未知工具：' + call.name)
                result = self.executor.execute(call)
                conversation.messages.append(Message('tool', str(result.value)))
        raise RuntimeError('Agent 已达到最大处理轮数')
