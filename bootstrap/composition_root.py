from application.use_cases.meeting import MeetingService
from adapters.services import AudioConverter, Transcriber, MinutesGenerator

def build_services():
    from adapters.models.deepseek import DeepSeekClient
    from adapters.storage.session_store import JsonSessionStore
    from bootstrap.paths import DATA_DIR
    return MeetingService(AudioConverter(), Transcriber(), MinutesGenerator(DeepSeekClient),
                          JsonSessionStore(DATA_DIR / 'sessions'))

def main():
    import tkinter as tk
    from adapters.desktop.ui import Demo
    from adapters.desktop.settings import needs_setup
    root = tk.Tk()
    app = Demo(root, services=build_services())
    if needs_setup():
        root.after(200, app.open_settings)
    root.mainloop()
