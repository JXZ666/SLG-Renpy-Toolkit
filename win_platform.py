"""Best-effort Windows process setup for the GUI entry points.

Tk reads the process DPI-awareness mode when it creates its root, so these
calls only help if they run before ``ctk.CTk()``. The CLI deliberately does not
import this module: making a console process DPI-aware or giving it a taskbar
identity can change how the console is grouped by the shell.

Every call is best-effort. A missing API, an old Windows build, or a policy
that forbids changing awareness must not stop the window from opening.
"""

import ctypes


def _bool_succeeded(result):
    """Windows BOOL APIs return non-zero on success."""
    return bool(result)


def _hresult_succeeded(result):
    """COM-style APIs return S_OK (0) on success."""
    return result == 0


def enable_dpi_awareness():
    """Enable the best DPI-awareness mode this Windows build offers.

    Tries per-monitor-v2, per-monitor, system-aware, then the legacy API.
    Returns ``per_monitor_v2`` / ``per_monitor`` / ``system`` / ``legacy``, or
    ``unavailable`` when none of them could be applied. Never raises.
    """
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return "unavailable"

    attempts = (
        ("per_monitor_v2", "user32", "SetProcessDpiAwarenessContext",
         (ctypes.c_void_p(-4),), _bool_succeeded),
        ("per_monitor", "shcore", "SetProcessDpiAwareness",
         (2,), _hresult_succeeded),
        ("system", "shcore", "SetProcessDpiAwareness",
         (1,), _hresult_succeeded),
        ("legacy", "user32", "SetProcessDPIAware", (), _bool_succeeded),
    )
    for mode, module_name, function_name, args, succeeded in attempts:
        try:
            function = getattr(getattr(windll, module_name), function_name)
            if succeeded(function(*args)):
                return mode
        except Exception:  # noqa: BLE001 - any platform failure means "try the next one"
            continue
    return "unavailable"


def set_app_user_model_id(app_id="JXZ666.SLG-Renpy-Toolkit"):
    """Give the process a stable AppUserModelID for taskbar grouping.

    Returns True when Windows accepted the ID and False for a missing API or
    any failure. Never raises.
    """
    try:
        function = getattr(
            getattr(ctypes, "windll").shell32,
            "SetCurrentProcessExplicitAppUserModelID",
        )
        return bool(function(str(app_id)) == 0)
    except Exception:  # noqa: BLE001 - the caller only needs a success flag
        return False


def prepare_windows_process():
    """Apply the GUI process settings and report what actually happened.

    Call this once, before the Tk root is created. Returns a dict with
    ``dpi_awareness`` and ``app_user_model_id`` keys; a failure in either step
    is recorded rather than raised so startup can continue.
    """
    try:
        dpi_awareness = enable_dpi_awareness()
    except Exception:  # noqa: BLE001 - platform setup must never block startup
        dpi_awareness = "unavailable"

    try:
        app_user_model_id = set_app_user_model_id()
    except Exception:  # noqa: BLE001 - platform setup must never block startup
        app_user_model_id = False

    return {
        "dpi_awareness": dpi_awareness,
        "app_user_model_id": app_user_model_id,
    }
