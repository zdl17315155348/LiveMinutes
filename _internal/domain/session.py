from dataclasses import dataclass
from enum import Enum

class SessionState(str, Enum):
    READY = "ready"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Session:
    id: str
    transcript: str = ""
    minutes: str = ""
    state: SessionState = SessionState.READY

    def begin_summary(self):
        if not self.transcript.strip():
            raise ValueError("没有有效转写")
        self.state = SessionState.SUMMARIZING
