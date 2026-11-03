from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)

@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict

@dataclass(frozen=True)
class ToolResult:
    name: str
    value: Any
    error: bool = False
