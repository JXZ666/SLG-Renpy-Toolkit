"""Make pytest collect the five script-style suites (Task 1).

`test_compat`, `test_fontfix`, `test_gui`, `test_install` and `test_simulation`
are runnable scripts: each builds a `check(label, ok)` list, prints a summary
from `main()`, and returns 0 on success / 1 on failure. pytest never saw them
because they define no `test_*` function and their `__main__` block is skipped
on import, so the routing assertions in test_compat.py that would have caught
the 7.5.3 startup crash never ran in CI.

This wrapper is deliberately thin and requires no edit to any of those files:
one pytest function per suite, importing the module and asserting `main()`
returned 0. Keeping them separate means a red test names the guilty file. The
suites' own prints are left in place - pytest captures them per test and shows
them only when the assertion fails, which is where they are useful.

`test_gui` is imported lazily and guarded with `importorskip("tkinter")` so a
machine without Tk fails collection cleanly instead of erroring; tkinter is
present here, so it is not skipped.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
# Same mechanism as test_release.py / test_rpa.py for the repo root; HERE is
# added so the sibling script modules are importable when this file is run
# directly as well as under pytest.
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _assert_ok(module):
    """Run a script suite's main() and fail pytest on a non-zero return."""
    code = module.main()
    assert code == 0, ("%s.main() returned %r; captured output above names the "
                       "failing checks" % (module.__name__, code))


def test_compat_script_suite():
    import test_compat
    _assert_ok(test_compat)


def test_fontfix_script_suite():
    import test_fontfix
    _assert_ok(test_fontfix)


def test_gui_script_suite():
    import pytest
    pytest.importorskip("tkinter")
    import test_gui
    _assert_ok(test_gui)


def test_install_script_suite():
    import test_install
    _assert_ok(test_install)


def test_simulation_script_suite():
    import test_simulation
    _assert_ok(test_simulation)
