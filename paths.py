"""Compatibility entry point for the layered implementation."""
import sys
from importlib import import_module

if __name__ == '__main__':
    import runpy
    runpy.run_module("bootstrap.paths", run_name='__main__')
else:
    sys.modules[__name__] = import_module("bootstrap.paths")
