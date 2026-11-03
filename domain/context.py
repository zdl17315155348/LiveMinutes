from dataclasses import dataclass

@dataclass(frozen=True)
class Context:
    transcript: str
    source: str = "meeting"

    def __post_init__(self):
        if not self.transcript.strip():
            raise ValueError("会议转写不能为空")
