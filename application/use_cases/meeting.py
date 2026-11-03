from uuid import uuid4
from domain.session import Session, SessionState
from application.ports.session_store import SessionStore
from application.ports.meeting import AudioConverter, Transcriber, MinutesGenerator

class MeetingService:
    def __init__(self, converter: AudioConverter, transcriber: Transcriber, minutes: MinutesGenerator, store: SessionStore | None = None):
        self.converter, self.transcriber, self.minutes = converter, transcriber, minutes
        self.store = store

    def import_audio(self, source, emit, stop):
        emit({'kind': 'import_progress', 'message': '正在转换导入音频…'})
        prepared = self.converter.prepare(source, stop)
        if stop.is_set():
            raise RuntimeError('已取消音频导入。')
        return self.transcriber.transcribe_file(prepared, emit, stop)

    def record(self, device, emit, stop, speaker=None, echo=True):
        if speaker is None:
            return self.transcriber.transcribe_microphone(device, emit, stop)
        return self.transcriber.transcribe_online(device, speaker, emit, stop, echo)

    def generate_minutes(self, text, output, progress, stop):
        session = Session(uuid4().hex, transcript=text)
        session.begin_summary()
        if self.store:
            self.store.save(session)
        try:
            result = self.minutes.generate(text, output, progress, stop)
            session.minutes = result['text']
            session.state = SessionState.COMPLETED
            return result
        except Exception:
            session.state = SessionState.FAILED
            raise
        finally:
            if self.store:
                self.store.save(session)
