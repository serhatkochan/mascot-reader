import ctypes
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mascot_reader.windows_lifecycle import installation_mutex_name


def test_mutex_identifies_executable_path_with_inno_unicode_digest(tmp_path):
    executable = tmp_path / 'Kurulum alanı ÇAĞRI İpek' / 'MascotReader.exe'
    normalized = os.path.abspath(executable).replace('/', '\\').translate(
        str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
    expected = 'Local\\MascotReader-' + hashlib.sha256(normalized.encode('utf-16le')).hexdigest()
    assert installation_mutex_name(executable) == expected
    assert installation_mutex_name(executable) != installation_mutex_name(tmp_path / 'portable.exe')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows case-insensitive file paths')
def test_unicode_case_alias_uses_the_same_installed_application_mutex(tmp_path):
    directory = tmp_path / 'ÇAĞRI İpek'
    directory.mkdir()
    executable = directory / 'MascotReader.exe'
    executable.write_bytes(b'installed application')
    alias = tmp_path / 'çaĞRI İpek' / 'MASCOTREADER.EXE'
    assert alias.exists()
    assert installation_mutex_name(executable) == installation_mutex_name(alias)
    extended = Path('\\\\?\\' + str(executable))
    assert extended.exists()
    assert installation_mutex_name(executable) == installation_mutex_name(extended)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows installer mutex')
def test_frozen_gui_mutex_exists_until_process_exits(tmp_path):
    executable = tmp_path / 'MascotReader.exe'
    name = installation_mutex_name(executable)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenMutexW.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.OpenMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_bool
    code = '''import sys
from mascot_reader.windows_lifecycle import hold_installation_mutex
sys.frozen = True
sys.executable = sys.argv[1]
hold_installation_mutex()
print('ready', flush=True)
input()
'''
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    process = subprocess.Popen([sys.executable, '-c', code, str(executable)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, startupinfo=startup, env=environment)
    try:
        assert process.stdout.readline().strip() == 'ready'
        handle = kernel.OpenMutexW(0x00100000, False, name)
        assert handle, 'The uninstaller cannot detect the running application'
        assert kernel.CloseHandle(handle)
        _, stderr = process.communicate('\n', timeout=10)
        assert process.returncode == 0, stderr
        assert not kernel.OpenMutexW(0x00100000, False, name)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
