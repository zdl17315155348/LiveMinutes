"""Python bindings for the WebRTC audio processing module."""


# start delvewheel patch
def _delvewheel_patch_1_13_0():
    import os
    if os.path.isdir(libs_dir := os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, 'pywebrtc_audio.libs'))):
        os.add_dll_directory(libs_dir)


_delvewheel_patch_1_13_0()
del _delvewheel_patch_1_13_0
# end delvewheel patch

from ._webrtc_audio import AudioProcessor, EchoCanceller, GainController, NoiseSuppressor, VoiceDetector

__all__ = ["AudioProcessor", "EchoCanceller", "GainController", "NoiseSuppressor", "VoiceDetector"]
