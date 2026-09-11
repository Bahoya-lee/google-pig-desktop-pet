# -*- coding: utf-8 -*-
"""Windows single-instance lock for the desktop pet."""

from __future__ import annotations

import atexit
import ctypes
from ctypes import wintypes

_ERROR_ALREADY_EXISTS = 183
_handle = None

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def acquire_single_instance() -> bool:
    """Return False when another Google Pig instance owns the lock."""
    global _handle
    if _handle:
        return True
    handle = _kernel32.CreateMutexW(None, False, r"Local\GooglePigPet_SingleInstance")
    if not handle:
        return True
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return False
    _handle = handle

    def release():
        if _handle:
            _kernel32.CloseHandle(_handle)

    atexit.register(release)
    return True

