"""Separate bundled resources from writable, portable application data."""
import sys
from pathlib import Path


def resource_root():
    """PyInstaller keeps package files and assets together in _internal."""
    return Path(__file__).resolve().parent.parent


def application_root():
    """Data follows the executable, never the launcher's working directory."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return resource_root()


def database_path():
    return application_root() / 'data' / 'warehouse_demo.db'
