from dataclasses import dataclass, field

@dataclass(frozen=True)
class Message:
    role: str
    content: str

@dataclass
class Conversation:
    messages: list[Message] = field(default_factory=list)
