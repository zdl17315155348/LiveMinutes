"""Backward-compatible desktop entry point."""
from adapters.desktop.ui import display_transcript

def Demo(root, backend='cloud', auto_minutes=True):
    from bootstrap.composition_root import build_services
    from adapters.desktop.ui import Demo as Desktop
    return Desktop(root, backend, auto_minutes, services=build_services())

if __name__ == '__main__':
    from bootstrap.composition_root import main
    main()
