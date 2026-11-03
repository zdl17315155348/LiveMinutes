from dataclasses import asdict
import json
from pathlib import Path
import re
from domain.session import Session, SessionState

class JsonSessionStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, identity):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identity):
            raise ValueError("无效会话编号")
        return self.directory / (identity + '.json')

    def save(self, session):
        path = self._path(session.id)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(asdict(session), ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)

    def load(self, session_id):
        value = json.loads(self._path(session_id).read_text(encoding='utf-8'))
        value['state'] = SessionState(value['state'])
        return Session(**value)
