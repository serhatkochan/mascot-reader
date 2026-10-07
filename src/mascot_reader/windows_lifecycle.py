import ctypes
import hashlib
import os
import sys
from pathlib import Path

_mutex_handle = None


def installation_mutex_name(executable: Path) -> str:
    normalized = os.path.realpath(executable)
    if normalized.startswith('\\\\?\\UNC\\'):
        normalized = '\\\\' + normalized[8:]
    elif normalized.startswith('\\\\?\\'):
        normalized = normalized[4:]
    normalized = normalized.replace('/', '\\').translate(
        str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
    digest = hashlib.sha256(normalized.encode('utf-16le')).hexdigest()
    return 'Local\\MascotReader-' + digest


def hold_installation_mutex() -> None:
    global _mutex_handle
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False) or _mutex_handle:
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    _mutex_handle = kernel.CreateMutexW(None, False, installation_mutex_name(Path(sys.executable)))
    if not _mutex_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    # Keep the handle until process exit, including Qt and worker shutdown.
