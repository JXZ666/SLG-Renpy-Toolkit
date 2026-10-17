"""Install selected Ren'Py patches into a disposable copy and run that copy.

The original game tree is read only.  Each session gets a fresh temporary
directory containing the copied game, its rpykit manifest/workspace, and the
save/persistent directories used when the staged game is launched.

This module deliberately reports "main menu unconfirmed" after process exit
with code zero.  A zero exit status says that the process ended normally; it
does not prove that the player ever reached the main menu.
"""

from __future__ import print_function

import codecs
import contextlib
import io
import hashlib
import copy
import os
import shutil
import stat
import subprocess
import tempfile
import threading

import cmd_fontfix
import compat
import features
import engine_adapters
import proj
import patch_transaction


def _diagnostic_snapshot(root):
    result = {}
    for name in ("traceback.txt", "errors.txt", "log.txt"):
        path = os.path.join(root, name)
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode) or _is_reparse(st):
                continue
            with open(path, "rb") as stream:
                stream.seek(max(0, st.st_size - LOG_TAIL_LIMIT))
                data = stream.read(LOG_TAIL_LIMIT)
            result[name] = ((st.st_mtime_ns, st.st_size, hashlib.sha256(data).hexdigest()),
                            data.decode("utf-8", "replace"))
        except OSError:
            continue
    return result


def _stage_ownership(source_dir, staged_dir, work_dir):
    """Copy verified ownership evidence so installed games can be simulated safely."""
    source_work = proj.work_dir_for(source_dir)
    if not os.path.isfile(proj.manifest_path(source_work)):
        return
    manifest = proj.load_manifest(source_work)
    cmd_fontfix._check_manifest_game(source_dir, manifest)
    staged_manifest = copy.deepcopy(manifest)
    for entry in manifest["files"]:
        rel = entry["path"]
        original = patch_transaction.safe_path(source_dir, rel)
        staged = patch_transaction.safe_path(staged_dir, rel)
        if not entry.get("sha256") or not os.path.isfile(original) or proj.file_hash(original) != entry["sha256"]:
            raise ValueError("installed file no longer matches ownership record: " + rel)
        if proj.file_hash(staged) != entry["sha256"]:
            raise ValueError("staged file differs from verified source: " + rel)
        if entry.get("backup"):
            backup_rel = entry["backup"]
            backup = patch_transaction.safe_path(source_work, backup_rel)
            if proj.file_hash(backup) != entry.get("backup_sha256"):
                raise ValueError("adapter backup changed: " + rel)
            dest = patch_transaction.safe_path(work_dir, backup_rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(backup, dest)
    for entry in manifest["quarantined"]:
        backup_rel = "quarantine/" + entry["stored_as"]
        backup = patch_transaction.safe_path(source_work, backup_rel)
        if not entry.get("sha256") or proj.file_hash(backup) != entry["sha256"]:
            raise ValueError("quarantined backup changed: " + entry["path"])
        dest = patch_transaction.safe_path(work_dir, backup_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(backup, dest)
    staged_manifest.update(game_dir=staged_dir, game_id=proj.game_identity(staged_dir))
    proj.save_manifest(work_dir, staged_manifest)


LOG_TAIL_LIMIT = 16000
MINIMUM_RESERVE_BYTES = 64 * 1024 * 1024
CAPACITY_MARGIN_NUMERATOR = 5
CAPACITY_MARGIN_DENOMINATOR = 100
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class SimulationError(Exception):
    """A failed preparation step, with structured status for the GUI."""

    def __init__(self, message, steps):
        Exception.__init__(self, message)
        self.steps = steps


def _step(steps, name, status, message):
    item = next((s for s in steps if s["id"] == name), None)
    if item is None:
        item = {"id": name, "status": status, "message": message}
        steps.append(item)
    else:
        item["status"] = status
        item["message"] = message
    return item


def _notify(callback, message):
    if callback is not None:
        try:
            callback(message)
        except Exception:
            # A disappearing GUI/log widget must not interrupt safe cleanup.
            pass


def _is_reparse(st):
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE_POINT)


def _check_entry(path, st):
    if stat.S_ISLNK(st.st_mode) or _is_reparse(st):
        raise ValueError("game contains a symbolic link or junction: %s" % path)
    if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
        raise ValueError("game contains an unsupported special file: %s" % path)


def _scan_tree(root):
    """Return logical file bytes while rejecting symlinks and reparse points."""
    try:
        root_stat = os.lstat(root)
    except OSError as exc:
        raise ValueError("cannot inspect game directory: %s" % exc)
    _check_entry(root, root_stat)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("game path is not a real directory")

    total = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    st = entry.stat(follow_symlinks=False)
                    _check_entry(entry.path, st)
                    if stat.S_ISDIR(st.st_mode):
                        stack.append(entry.path)
                    else:
                        total += st.st_size
        except OSError as exc:
            raise ValueError("cannot inspect game files: %s" % exc)
    return total


def _copy_directory(source, destination):
    """Copy regular files as new files; never preserve links or hardlinks."""
    source_stat = os.lstat(source)
    _check_entry(source, source_stat)
    if not stat.S_ISDIR(source_stat.st_mode):
        raise ValueError("game directory changed while it was being copied: %s" % source)
    os.mkdir(destination)
    try:
        with os.scandir(source) as entries:
            ordered = sorted(entries, key=lambda item: item.name.lower())
        for entry in ordered:
            source_path = entry.path
            destination_path = os.path.join(destination, entry.name)
            st = os.stat(source_path, follow_symlinks=False)
            _check_entry(source_path, st)
            if stat.S_ISDIR(st.st_mode):
                # Recheck immediately before descending.  A junction swapped
                # in after the sizing pass is rejected before it is followed.
                _copy_directory(source_path, destination_path)
            else:
                shutil.copy2(source_path, destination_path, follow_symlinks=False)
                copied_stat = os.lstat(destination_path)
                _check_entry(destination_path, copied_stat)
        shutil.copystat(source, destination, follow_symlinks=False)
    except Exception:
        raise


def _copy_tree(source, destination):
    _copy_directory(source, destination)


def _remove_tree(path):
    """Remove a session even when copied game files are read-only on Windows."""
    def retry_writable(function, target, exc_info):
        try:
            os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
        except OSError:
            pass
        function(target)

    if os.path.lexists(path):
        shutil.rmtree(path, onerror=retry_writable)


def _required_bytes(game_bytes):
    font_bytes = 0
    try:
        font_bytes = os.path.getsize(cmd_fontfix.ASSET_FONT)
    except OSError:
        pass
    margin = max(MINIMUM_RESERVE_BYTES,
                 game_bytes * CAPACITY_MARGIN_NUMERATOR // CAPACITY_MARGIN_DENOMINATOR)
    return game_bytes + margin + font_bytes


def _check_capacity(game_bytes, temporary_parent):
    required = _required_bytes(game_bytes)
    available = shutil.disk_usage(temporary_parent).free
    if available < required:
        raise ValueError(
            "not enough free space for a safe simulation copy "
            "(need about %.1f MiB, have %.1f MiB)" %
            (required / (1024.0 * 1024.0), available / (1024.0 * 1024.0)))
    return required


def _launcher_candidates(staged_dir):
    """List plausible root-level game executables for explicit selection."""
    excluded = ("unins", "uninstall", "installer", "setup", "crashreporter",
                "crash_reporter", "vc_redist", "dxsetup", "redist", "update")
    result = []
    try:
        names = os.listdir(staged_dir)
    except OSError:
        return result
    for name in sorted(names, key=lambda value: value.lower()):
        if not name.lower().endswith(".exe"):
            continue
        stem = name[:-4].lower()
        if any(stem.startswith(prefix) for prefix in excluded):
            continue
        path = os.path.join(staged_dir, name)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode) and not _is_reparse(st):
            result.append(name)
    return result


class SimulationSession(object):
    """A prepared copy which can be launched, observed, and then discarded."""

    def __init__(self, session_dir, staged_dir, work_dir, launchers, steps,
                 log_callback=None, log_text=""):
        self.session_dir = session_dir
        self.staged_dir = staged_dir
        self._staged_identity = os.path.normcase(os.path.realpath(staged_dir))
        self.work_dir = work_dir
        self.launchers = list(launchers)
        self.steps = steps
        self.process = None
        self.exit_code = None
        self.main_menu_confirmed = False
        self.gameplay_confirmed = False
        self.runtime_errors = []
        self._diagnostic_baseline = _diagnostic_snapshot(staged_dir)
        self._diagnostics_seen = dict(self._diagnostic_baseline)
        self._stop_requested = False
        self._cleaned = False
        self._log_callback = log_callback
        self._log_text = log_text[-LOG_TAIL_LIMIT:]
        self._log_lock = threading.Lock()
        self._reader = None

    @property
    def log_tail(self):
        with self._log_lock:
            return self._log_text

    def _append_log(self, text):
        if not text:
            return
        with self._log_lock:
            self._log_text = (self._log_text + text)[-LOG_TAIL_LIMIT:]
        _notify(self._log_callback, text)

    def _set_launch_step(self, status, message):
        _step(self.steps, "launch", status, message)

    def launch(self, rel_launcher):
        """Launch one listed staged executable, never a path in the source."""
        if self._cleaned:
            raise RuntimeError("simulation session has already been cleaned up")
        if self.process is not None:
            raise RuntimeError("a simulation process has already been launched")
        if not isinstance(rel_launcher, str) or rel_launcher not in self.launchers:
            raise ValueError("launcher is not one of this session's safe candidates")
        if not os.path.isdir(self.staged_dir):
            raise RuntimeError("staged game copy is no longer available")
        staged_lstat = os.lstat(self.staged_dir)
        if (not stat.S_ISDIR(staged_lstat.st_mode) or stat.S_ISLNK(staged_lstat.st_mode)
                or _is_reparse(staged_lstat)
                or os.path.normcase(os.path.realpath(self.staged_dir)) != self._staged_identity):
            raise RuntimeError("staged game directory changed after preparation")

        if (not isinstance(rel_launcher, str) or os.path.isabs(rel_launcher)
                or os.path.basename(rel_launcher) != rel_launcher):
            raise ValueError("launcher path must be a root-level filename")
        launcher = os.path.abspath(os.path.join(self.staged_dir, rel_launcher))
        staged_real = os.path.normcase(os.path.realpath(self.staged_dir))
        launcher_real = os.path.normcase(os.path.realpath(launcher))
        try:
            inside_staging = os.path.normcase(os.path.commonpath(
                (staged_real, launcher_real))) == staged_real
        except ValueError:
            inside_staging = False
        if not inside_staging:
            raise ValueError("launcher path is outside the staged game copy")
        st = os.lstat(launcher)
        if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or _is_reparse(st):
            raise ValueError("launcher is no longer a regular staged file")

        saves_dir = os.path.join(self.session_dir, "saves")
        persistent_dir = os.path.join(self.session_dir, "multipersistent")
        os.makedirs(saves_dir, exist_ok=True)
        os.makedirs(persistent_dir, exist_ok=True)
        environment = os.environ.copy()
        # Inherited debug/skip flags must not accidentally change the test entry.
        for name in ("RENPY_SKIP_MAIN_MENU", "RENPY_SKIP_SPLASHSCREEN",
                     "RENPY_FORCE_DEVELOPER", "RENPY_DEVELOPER"):
            if name in environment:
                self._append_log("[simulation] ignored inherited " + name + "\n")
                environment.pop(name)
        environment["RENPY_PATH_TO_SAVES"] = saves_dir
        environment["RENPY_MULTIPERSISTENT"] = persistent_dir
        self._diagnostic_baseline = _diagnostic_snapshot(self.staged_dir)
        self._diagnostics_seen = dict(self._diagnostic_baseline)

        try:
            process = subprocess.Popen(
                [launcher], cwd=self.staged_dir, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        except Exception as exc:
            self._set_launch_step("failed", "could not start staged game: %s" % exc)
            raise

        self.process = process
        self._set_launch_step(
            "running", "staged game process started; main menu is not yet confirmed")
        _notify(self._log_callback, "Staged game process started.\n")
        stdout = getattr(process, "stdout", None)
        if stdout is not None and hasattr(stdout, "read"):
            self._reader = threading.Thread(target=self._read_process_output,
                                            args=(stdout,), daemon=True)
            self._reader.start()
        return process

    def _read_process_output(self, stream):
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    text = chunk
                else:
                    text = decoder.decode(chunk)
                self._append_log(text)
            self._append_log(decoder.decode(b"", final=True))
        except Exception as exc:
            self._append_log("\n[simulation log read error: %s]\n" % exc)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def poll(self):
        """Return None while running, else return the process exit code."""
        if self.process is None:
            return None
        self.check_runtime_errors()
        code = self.process.poll()
        if self.runtime_errors:
            self._set_launch_step("failed", "new game error: " + self.runtime_errors[-1])
            self.exit_code = code
            return code
        if code is None:
            return None
        self.exit_code = code
        if self._stop_requested:
            self._set_launch_step("stopped", "staged game process was stopped")
        elif code != 0:
            self._set_launch_step("failed", "staged game exited with code %s" % code)
        elif self.main_menu_confirmed:
            self._set_launch_step("success", "user confirmed the staged game reached its main menu")
        else:
            self._set_launch_step(
                "pending_confirmation",
                "process exited normally (code 0), but reaching the main menu is unconfirmed")
        return code

    def confirm_main_menu(self):
        """Record the user's explicit confirmation that the menu appeared."""
        if self.process is None:
            raise RuntimeError("no staged game has been launched")
        self.check_runtime_errors()
        if self.runtime_errors:
            raise RuntimeError("game reported a new error: " + self.runtime_errors[-1])
        code = self.process.poll()
        if code not in (None, 0):
            raise RuntimeError("the staged game exited with code %s" % code)
        if self._stop_requested:
            raise RuntimeError("a stopped simulation cannot be confirmed")
        self.main_menu_confirmed = True
        self._set_launch_step(
            "success", "user confirmed the staged game reached its main menu")
        return True

    def check_runtime_errors(self):
        """Observe only changed diagnostics; a running process can still crash in-game."""
        current = _diagnostic_snapshot(self.staged_dir)
        for name, value in current.items():
            if self._diagnostics_seen.get(name, (None,))[0] == value[0]:
                continue
            self._diagnostics_seen[name] = value
            text = value[1]
            if not text.strip():
                continue
            self._append_log("\n[game diagnostic: " + name + "]\n" + text + "\n")
            if name in ("traceback.txt", "errors.txt") or any(
                    marker in text for marker in ("uncaught exception", "Full traceback:",
                                                  "ScriptError:", "Traceback (most recent")):
                message = name + ": " + next((line.strip() for line in reversed(text.splitlines())
                                              if "Error:" in line or "Exception:" in line),
                                             "game reported an error")
                self.runtime_errors.append(message)
        if self.runtime_errors:
            self._set_launch_step("failed", "new game error: " + self.runtime_errors[-1])
        return list(self.runtime_errors)

    def confirm_gameplay(self):
        if not self.main_menu_confirmed:
            raise RuntimeError("confirm the main menu before gameplay")
        self.check_runtime_errors()
        if self.runtime_errors:
            raise RuntimeError("game reported a new error: " + self.runtime_errors[-1])
        if self.process.poll() not in (None, 0) or self._stop_requested:
            raise RuntimeError("game did not finish normally")
        self.gameplay_confirmed = True
        _step(self.steps, "gameplay", "success", "user confirmed the tested gameplay scene")
        return True

    def stop(self, timeout=3.0):
        """Request process termination and wait; kill only if it ignores that."""
        if self.process is None:
            return None
        code = self.process.poll()
        if code is not None:
            return self.poll()

        self._stop_requested = True
        try:
            self.process.terminate()
        except Exception:
            # The process may have exited between poll() and terminate().
            pass
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                self.process.kill()
            finally:
                code = self.process.wait()
        self.exit_code = code
        self._set_launch_step("stopped", "staged game process was stopped")
        return code

    def cleanup(self):
        """Delete the disposable session after its process has stopped."""
        if self._cleaned:
            return
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("stop the staged game before cleaning up its session")
        if self._reader is not None:
            self._reader.join(timeout=0.5)
        _remove_tree(self.session_dir)
        self._cleaned = True


def prepare(game_dir, feature_ids, log_callback=None):
    """Check, copy, and install selected features into a temporary game copy.

    Successful return means only that installation passed in the disposable
    copy.  The launch step remains ``pending`` until the caller explicitly
    selects a candidate and calls ``session.launch``.
    """
    steps = []
    source_dir = os.path.abspath(os.fspath(game_dir))
    selected = list(feature_ids or [])
    known = features.ids()
    if engine_adapters.detect(source_dir)["id"] in ("unknown", "ambiguous"):
        _step(steps, "compat", "failed", "selected directory has no supported engine layout")
        raise SimulationError("not a supported game directory: %s" % source_dir, steps)
    if not selected or any(fid not in known for fid in selected):
        _step(steps, "compat", "failed", "select one or more known patch features")
        raise SimulationError("invalid simulation feature selection", steps)

    try:
        survey = engine_adapters.survey(source_dir)
    except Exception as exc:
        _step(steps, "compat", "failed", "compatibility scan failed: %s" % exc)
        raise SimulationError("compatibility scan failed: %s" % exc, steps)

    if survey.get("verdict") == "bad":
        reasons = "; ".join(survey.get("reasons", [])) or "not a recognized Ren'Py distribution"
        _step(steps, "compat", "failed", reasons)
        raise SimulationError(reasons, steps)

    support = survey.get("feature_support", {})
    unsupported = []
    for fid in selected:
        feature = support.get(fid, {})
        if not feature.get("supported", False):
            reason = "; ".join(feature.get("reasons", [])) or "required engine APIs are unknown"
            unsupported.append("%s: %s" % (features.title_of(fid), reason))
    if unsupported:
        message = "selected feature is not supported: " + " | ".join(unsupported)
        _step(steps, "compat", "failed", message)
        raise SimulationError(message, steps)

    try:
        game_bytes = _scan_tree(source_dir)
    except Exception as exc:
        message = "unsafe or unreadable game tree: %s" % exc
        _step(steps, "compat", "failed", message)
        raise SimulationError(message, steps)

    _step(steps, "compat", "success",
          "selected patch APIs are available; original game tree passed the safety scan")
    _notify(log_callback, "Compatibility precheck passed.\n")

    temporary_parent = tempfile.gettempdir()
    source_real = os.path.normcase(os.path.realpath(source_dir))
    temporary_real = os.path.normcase(os.path.realpath(temporary_parent))
    try:
        if os.path.commonpath((source_real, temporary_real)) == source_real:
            message = "system temporary directory is inside the game directory"
            _step(steps, "copy", "failed", message)
            raise SimulationError(message, steps)
    except ValueError as exc:
        if str(exc) == "system temporary directory is inside the game directory":
            raise
        # Different volumes cannot overlap.
    try:
        _check_capacity(game_bytes, temporary_parent)
    except Exception as exc:
        _step(steps, "copy", "failed", str(exc))
        raise SimulationError(str(exc), steps)

    session_dir = None
    staged_dir = None
    work_dir = None
    try:
        session_dir = tempfile.mkdtemp(prefix="rpykit-simulation-")
        # Avoid placing the copy inside its source, which can occur when a
        # caller chooses the system temp directory itself as their game root.
        session_real = os.path.normcase(os.path.realpath(session_dir))
        try:
            if os.path.commonpath((source_real, session_real)) == source_real:
                raise ValueError("system temporary directory is inside the game directory")
        except ValueError as exc:
            if str(exc) == "system temporary directory is inside the game directory":
                raise

        staged_dir = os.path.join(session_dir, "game-copy")
        work_dir = os.path.join(session_dir, "work")
        _step(steps, "copy", "running",
              "copying about %.1f MiB into an isolated temporary directory" %
              (game_bytes / (1024.0 * 1024.0)))
        _notify(log_callback, "Copying game into a temporary session.\n")
        _copy_tree(source_dir, staged_dir)
        os.makedirs(work_dir)
        _stage_ownership(source_dir, staged_dir, work_dir)
        _step(steps, "copy", "success", "isolated game copy created")

        _step(steps, "install", "running", "installing selected patches in the copy")
        _notify(log_callback, "Installing patches in the temporary copy.\n")
        captured = io.StringIO()
        args = type("SimulationArgs", (), {})()
        args.game_dir = staged_dir
        args.work = work_dir
        args.mode = "luna"
        args.lang = "chinesesimplified"
        args.revert = False
        args.force = True
        args.dry_run = False
        args.skip_intro = "intro" in selected
        args.features = selected
        try:
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                engine_adapters.run(args)
        except BaseException as exc:
            # SystemExit is used by the CLI runner for a refused operation;
            # KeyboardInterrupt from the host should propagate after cleanup.
            output = captured.getvalue()
            message = str(exc) or exc.__class__.__name__
            if output:
                message += "\n" + output[-4000:]
            _step(steps, "install", "failed", message)
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise SimulationError("patch simulation failed: %s" % message, steps)

        install_log = captured.getvalue()
        _notify(log_callback, install_log)
        launchers = _launcher_candidates(staged_dir)
        _step(steps, "install", "success",
              "selected patches installed in the disposable copy; original game was not written")
        if launchers:
            launch_message = ("patch simulation passed; choose a staged launcher to run "
                              "the copy (main menu not yet confirmed)")
        else:
            launch_message = ("patch simulation passed, but no root-level game .exe was found; "
                              "the copy cannot be launched from this session")
        _step(steps, "launch", "pending", launch_message)
        _notify(log_callback, "Patch simulation passed; waiting for an explicit launcher selection.\n")
        return SimulationSession(session_dir, staged_dir, work_dir, launchers,
                                 steps, log_callback, install_log)
    except SimulationError as exc:
        try:
            if session_dir:
                _remove_tree(session_dir)
        except Exception as cleanup_exc:
            raise SimulationError("%s; temporary cleanup also failed: %s" %
                                  (exc, cleanup_exc), exc.steps)
        raise
    except BaseException as exc:
        if "copy" in [s["id"] for s in steps] and steps[-1]["id"] == "copy":
            _step(steps, "copy", "failed", str(exc))
        elif "install" in [s["id"] for s in steps]:
            _step(steps, "install", "failed", str(exc))
        else:
            _step(steps, "copy", "failed", str(exc))
        cleanup_error = None
        try:
            if session_dir:
                _remove_tree(session_dir)
        except Exception as cleanup_exc:
            cleanup_error = cleanup_exc
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        if cleanup_error:
            message = "%s; temporary cleanup also failed: %s" % (exc, cleanup_error)
        else:
            message = str(exc)
        raise SimulationError("simulation preparation failed: %s" % message, steps)
