from typing import Protocol

class ModelClient(Protocol):
    def complete(self, prompt: str, max_tokens: int = 8192) -> tuple[str, dict]: ...
