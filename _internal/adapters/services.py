from adapters.audio import converter
from adapters.transcription import doubao, live
from adapters.storage import minutes_runtime

class AudioConverter:
    def prepare(self, source, stop):
        return converter.prepare_audio(source, stop)

class Transcriber:
    def transcribe_file(self, source, emit, stop):
        return doubao.run_cloud(source, emit, stop)
    def transcribe_microphone(self, device, emit, stop):
        return live.run_microphone(device, emit, stop)
    def transcribe_online(self, device, speaker, emit, stop, echo=True):
        return live.run_online(device, speaker, emit, stop, echo_cancellation=echo)

class MinutesGenerator:
    def __init__(self, client_factory=None):
        self.client_factory = client_factory

    def generate(self, text, output, progress, stop):
        return minutes_runtime.generate_minutes(text, output, progress, stop, client_factory=self.client_factory)
