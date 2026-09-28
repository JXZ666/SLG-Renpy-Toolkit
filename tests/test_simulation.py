"""Exercise disposable-copy simulation without launching a real game.

Run: python tests/test_simulation.py
"""

import hashlib
import os
import shutil
import stat
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

import simulation  # noqa: E402


def _write(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    kwargs = {} if mode == "wb" else {"encoding": "utf-8", "newline": "\n"}
    with open(path, mode, **kwargs) as stream:
        stream.write(data)


def make_game(root, font_map=True, label_overrides=True, include_exe=True):
    """Build the smallest plausible Ren'Py tree accepted by the installer."""
    os.makedirs(os.path.join(root, "game"), exist_ok=True)
    os.makedirs(os.path.join(root, "renpy", "text"), exist_ok=True)
    os.makedirs(os.path.join(root, "lib", "python3.9"), exist_ok=True)
    os.makedirs(os.path.join(root, "lib", "py3-windows-x86_64"), exist_ok=True)
    _write(os.path.join(root, "game", "script_version.txt"), "(8, 3, 0)\n")
    config = []
    if font_map:
        config.append("font_name_map = {}\n")
    if label_overrides:
        config.append("label_overrides = {}\n")
    _write(os.path.join(root, "renpy", "config.py"), "".join(config))
    _write(os.path.join(root, "renpy", "__init__.py"), "# synthetic Ren'Py\n")
    _write(os.path.join(root, "renpy", "text", "font.py"),
           "class FontGroup(object):\n"
           "    def add(self, font, start, end, target=None):\n"
           "        pass\n")
    _write(os.path.join(root, "game", "script.rpy"), "label start:\n    return\n")
    if include_exe:
        # The launcher is only passed to a mocked Popen in these tests.
        _write(os.path.join(root, "SyntheticGame.exe"), b"not a real executable")
        _write(os.path.join(root, "unins000.exe"), b"not a game launcher")
    return root


def fingerprint(root):
    """Hash names and bytes, proving simulation did not write the source tree."""
    digest = hashlib.sha256()
    for directory, dirs, files in os.walk(root):
        dirs.sort()
        files.sort()
        for name in dirs + files:
            path = os.path.join(directory, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            digest.update(rel.encode("utf-8", "surrogatepass"))
            if os.path.isfile(path) and not os.path.islink(path):
                with open(path, "rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
    return digest.hexdigest()


class FakeProcess(object):
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.stdout = None
        self.wait_calls = []

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode


def main():
    failures = []

    def check(label, condition, detail=""):
        if condition:
            print("  ok   %s" % label)
        else:
            print("  FAIL %s %s" % (label, detail))
            failures.append(label)

    tmp = tempfile.mkdtemp(prefix="rpykit_simulation_test_")
    try:
        source = make_game(os.path.join(tmp, "source"))
        read_only_source = os.path.join(source, "read-only.dat")
        _write(read_only_source, b"copied as read-only")
        try:
            os.chmod(read_only_source, stat.S_IREAD)
        except OSError:
            pass
        before = fingerprint(source)

        print("prepare isolated copy")
        session = simulation.prepare(source, ["intro"])
        try:
            check("compatibility, copy, and install steps pass",
                  [s["status"] for s in session.steps[:3]] ==
                  ["success", "success", "success"], session.steps)
            check("launch remains pending until explicitly started",
                  session.steps[-1]["status"] == "pending", session.steps[-1])
            check("one safe game launcher is returned",
                  session.launchers == ["SyntheticGame.exe"], session.launchers)
            check("simulated intro patch exists only in the staging copy",
                  os.path.isfile(os.path.join(session.staged_dir, "game",
                                              "zz_rpykit_intro.rpy")))
            check("manifest and workspace are inside this session",
                  os.path.commonpath((session.session_dir, session.work_dir)) ==
                  session.session_dir and
                  os.path.isfile(os.path.join(session.work_dir,
                                              "install_manifest.json")))
            check("source game fingerprint remains unchanged",
                  fingerprint(source) == before)

            print("launch and isolate save data")
            process = FakeProcess()
            with mock.patch.object(simulation.subprocess, "Popen", return_value=process) as popen:
                returned = session.launch("SyntheticGame.exe")
            call = popen.call_args
            kwargs = call.kwargs if hasattr(call, "kwargs") else call[1]
            check("launch uses staged cwd", returned is process and
                  kwargs["cwd"] == session.staged_dir, kwargs)
            check("spawned executable is under staging, never the source",
                  os.path.commonpath((session.staged_dir, popen.call_args[0][0][0])) ==
                  session.staged_dir, popen.call_args)
            check("Ren'Py save and persistent paths stay inside session",
                  os.path.commonpath((session.session_dir,
                                      kwargs["env"]["RENPY_PATH_TO_SAVES"])) == session.session_dir and
                  os.path.commonpath((session.session_dir,
                                      kwargs["env"]["RENPY_MULTIPERSISTENT"])) == session.session_dir)
            check("running process reports None",
                  session.poll() is None and session.steps[-1]["status"] == "running")
            process.returncode = 0
            check("zero exit awaits explicit main-menu confirmation",
                  session.poll() == 0 and
                  session.steps[-1]["status"] == "pending_confirmation")
            check("explicit main-menu confirmation is success",
                  session.confirm_main_menu() and
                  session.steps[-1]["status"] == "success")
            session.cleanup()
            check("cleanup removes the session directory",
                  not os.path.exists(session.session_dir))
        finally:
            if os.path.exists(session.session_dir):
                if session.process is not None and session.process.poll() is None:
                    session.stop()
                session.cleanup()

        print("failure cases and cleanup")
        incompatible = make_game(os.path.join(tmp, "incompatible"), font_map=False)
        with mock.patch.object(simulation.tempfile, "mkdtemp",
                               side_effect=AssertionError("must not stage incompatible game")):
            try:
                simulation.prepare(incompatible, ["fontfix"])
                check("missing font API is rejected before staging", False)
            except simulation.SimulationError as exc:
                check("missing font API fails compatibility step",
                      exc.steps[-1]["id"] == "compat" and
                      exc.steps[-1]["status"] == "failed", exc.steps)

        space_game = make_game(os.path.join(tmp, "low_space"))
        with mock.patch.object(simulation.shutil, "disk_usage",
                               return_value=type("Usage", (), {"free": 0})()), \
                mock.patch.object(simulation.tempfile, "mkdtemp",
                                  side_effect=AssertionError("must not stage low-space game")):
            try:
                simulation.prepare(space_game, ["intro"])
                check("low space is refused before staging", False)
            except simulation.SimulationError as exc:
                check("low-space result is attached to copy step",
                      exc.steps[-1]["id"] == "copy" and
                      exc.steps[-1]["status"] == "failed", exc.steps)

        copy_game = make_game(os.path.join(tmp, "copy_failure"))
        created = []
        real_mkdtemp = tempfile.mkdtemp

        def capture_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            created.append(path)
            return path

        with mock.patch.object(simulation.tempfile, "mkdtemp", side_effect=capture_mkdtemp), \
                mock.patch.object(simulation, "_copy_tree",
                                  side_effect=OSError("synthetic copy failure")):
            try:
                simulation.prepare(copy_game, ["intro"])
                check("copy failure raises", False)
            except simulation.SimulationError as exc:
                check("copy failure is attributed to copy step",
                      exc.steps[-1]["id"] == "copy" and
                      exc.steps[-1]["status"] == "failed", exc.steps)
        check("partial temporary copy is removed after copy failure",
              len(created) == 1 and not os.path.exists(created[0]), created)

        link_game = make_game(os.path.join(tmp, "linked"))
        external = os.path.join(tmp, "outside.txt")
        _write(external, "outside")
        try:
            os.symlink(external, os.path.join(link_game, "external-link"))
        except (OSError, NotImplementedError):
            link_created = False
        else:
            link_created = True
        if link_created:
            try:
                simulation.prepare(link_game, ["intro"])
                check("external symlink is rejected", False)
            except simulation.SimulationError as exc:
                check("external symlink is rejected during compatibility safety scan",
                      exc.steps[-1]["status"] == "failed", exc.steps)
        else:
            check("external symlink test skipped (platform does not allow creating one)", True)
        try:
            simulation._check_entry(
                "synthetic-junction",
                type("Stat", (), {"st_mode": stat.S_IFDIR | 0o755,
                                  "st_file_attributes": 0x400})())
            check("Windows reparse-point flag is rejected", False)
        except ValueError:
            check("Windows reparse-point flag is rejected", True)

        print("process failure, stop, and launcher absence")
        exit_game = make_game(os.path.join(tmp, "nonzero"))
        session = simulation.prepare(exit_game, ["intro"])
        process = FakeProcess()
        with mock.patch.object(simulation.subprocess, "Popen", return_value=process):
            session.launch("SyntheticGame.exe")
        process.returncode = 7
        check("nonzero exit is a visible failure",
              session.poll() == 7 and session.steps[-1]["status"] == "failed",
              session.steps[-1])
        session.cleanup()

        stop_game = make_game(os.path.join(tmp, "stop"))
        session = simulation.prepare(stop_game, ["intro"])
        process = FakeProcess()
        with mock.patch.object(simulation.subprocess, "Popen", return_value=process):
            session.launch("SyntheticGame.exe")
        try:
            session.cleanup()
            check("cleanup refuses while the game process is running", False)
        except RuntimeError:
            check("cleanup refuses while the game process is running", True)
        check("stop terminates and waits for the process",
              session.stop() == 0 and process.terminated and
              process.wait_calls and session.steps[-1]["status"] == "stopped")
        session.cleanup()

        no_exe = make_game(os.path.join(tmp, "no_exe"), include_exe=False)
        session = simulation.prepare(no_exe, ["intro"])
        check("missing launcher is pending and not overall success",
              not session.launchers and session.steps[-1]["status"] == "pending" and
              "cannot be launched" in session.steps[-1]["message"], session.steps[-1])
        session.cleanup()

        check("all successful and failed simulations leave originals unchanged",
              fingerprint(source) == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("\nFAILED: %s" % ", ".join(failures))
        return 1
    print("\nAll simulation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
