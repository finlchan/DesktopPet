"""Keep the machine awake while the status marquee is visible.

On Windows, uses ``SetThreadExecutionState`` with continuous
``ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED`` so idle sleep, hibernate,
and display-off do not end the session while the marquee runs. Clearing
the state (``ES_CONTINUOUS`` alone) restores normal power policy.

Non-Windows platforms are a no-op (state is still tracked for tests).
"""

from __future__ import annotations

import atexit
import sys
from typing import Callable, Optional

# Win32 EXECUTION_STATE (winbase.h)
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_CONTINUOUS = 0x80000000

_KEEP_FLAGS = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
_CLEAR_FLAGS = ES_CONTINUOUS

_active = False
_api: Optional[Callable[[int], int]] = None
_api_loaded = False
_atexit_registered = False


def _load_api() -> Optional[Callable[[int], int]]:
    """Resolve kernel32.SetThreadExecutionState once (Windows only)."""
    global _api, _api_loaded
    if _api_loaded:
        return _api
    _api_loaded = True
    if sys.platform != "win32":
        _api = None
        return _api
    try:
        import ctypes

        fn = ctypes.windll.kernel32.SetThreadExecutionState
        fn.argtypes = [ctypes.c_uint]
        fn.restype = ctypes.c_uint
        _api = fn
    except Exception:
        _api = None
    return _api


def is_active() -> bool:
    """True when this process has requested continuous keep-awake."""
    return _active


def is_supported() -> bool:
    """True when the Win32 API is available (always False off Windows)."""
    return _load_api() is not None


def set_keep_awake(enabled: bool) -> bool:
    """Enable or clear keep-awake. Returns True if the request was applied.

    Enabling while already active re-asserts the Win32 flags (harmless).
    Clearing while already inactive is a no-op success. Off Windows the
    local flag is updated with no power effect.
    """
    global _active, _atexit_registered
    want = bool(enabled)

    if not want and not _active:
        return True

    api = _load_api()
    if api is None:
        _active = want
        if want:
            _ensure_atexit()
        return True

    flags = _KEEP_FLAGS if want else _CLEAR_FLAGS
    try:
        prev = api(flags)
    except Exception:
        return False
    # SetThreadExecutionState returns 0 on failure.
    if prev == 0:
        return False

    _active = want
    if want:
        _ensure_atexit()
    return True


def _ensure_atexit() -> None:
    global _atexit_registered
    if not _atexit_registered:
        atexit.register(_clear_on_exit)
        _atexit_registered = True


def _clear_on_exit() -> None:
    """Safety net for process exit / app quit without an orderly hide."""
    if _active:
        set_keep_awake(False)


def _reset_for_tests() -> None:
    """Reset module state without relying on atexit (smoke tests only)."""
    global _active, _api, _api_loaded, _atexit_registered
    if _active and sys.platform == "win32":
        api = _load_api()
        if api is not None:
            try:
                api(_CLEAR_FLAGS)
            except Exception:
                pass
    _active = False
    _api = None
    _api_loaded = False
    # Leave atexit hook registered; calling clear when inactive is fine.
    _atexit_registered = _atexit_registered
