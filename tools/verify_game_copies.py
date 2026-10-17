"""Offline compatibility probes in temporary game copies, never originals.

Usage: python tools/verify_game_copies.py GAME_ROOT --kind replay|luna [--label LABEL]
Reports actual engine probes, not confirmation of the game's main menu or of
a live Luna client. Synthetic strings only; no story text is collected.
For --kind replay, --label names the reviewed native main-menu Start target;
the label is supplied by the caller and never hardcoded in this repository.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import renpy_compat
import simulation
import proj


def _harness(kind, patched, label=None):
    if kind == "replay":
        if not isinstance(label, str) or not label.strip() or any(
                char in label for char in "'\"\\\r\n"):
            raise ValueError("--label must be a non-empty label name for --kind replay")
        return '''init 1000 python:
    import renpy as _probe_engine
    config.log = "probe-result.txt"
    _target = %r
    if %r:
        assert _probe_engine.game.script.lookup("start") is _probe_engine.game.script.lookup(_target)
        _probe_engine.exports.log("RPYKIT_PROBE: native start lookup PASS")
    else:
        try:
            _probe_engine.game.script.lookup("start")
        except _probe_engine.script.ScriptError:
            _probe_engine.exports.log("RPYKIT_PROBE: missing start reproduced")
        else:
            raise AssertionError("baseline unexpectedly defines start")
    _probe_engine.exports.quit()
''' % (label, patched)
    return '''init 1000 python:
    import renpy as _probe_engine
    config.log = "probe-result.txt"
    config.developer = True
    config.label_overrides["start"] = "_rpykit_probe"
    _probe_seen = []
    _probe_original_update = _probe_engine.text.text.Text.update
    def _probe_update(self, *args, **kwargs):
        if self.text and "LongTranslatedToken" in self.text[0]:
            _probe_seen.append((self.start, self.end, self.slow))
        return _probe_original_update(self, *args, **kwargs)
    _probe_engine.text.text.Text.update = _probe_update
    _probe_namespace = {"original_Text_init_hook": _probe_engine.text.text.Text.__init__}
    exec("def callLunaHost(text, split):\\n    return text.replace('ProbeToken', 'LongTranslatedToken') if isinstance(text, str) else text\\ndef callLunaIsUsingEmbed(split):\\n    return split == 1\\ndef new_init(self, text, *args, **kwargs):\\n    return original_Text_init_hook(self, callLunaHost(text, 1), *args, **kwargs)\\n", _probe_namespace)
    _probe_engine.text.text.Text.__init__ = _probe_namespace["new_init"]
    _probe_engine.game.preferences.text_cps = 30
    def _probe_auto_advance():
        _probe_engine.ui.timer(0.25, action=_probe_engine.store.Return())
    config.overlay_functions.append(_probe_auto_advance)
label _rpykit_probe:
    python:
        _probe_engine.exports.say(None, "ProbeToken{w}end", interact=True)
        assert config.developer is True
        assert any(item[1] == len("LongTranslatedToken{w}end") for item in _probe_seen), _probe_seen
        assert any(item[2] for item in _probe_seen), _probe_seen
        _probe_engine.exports.log("RPYKIT_PROBE: Luna mock translated say and slow ranges PASS")
        _probe_engine.exports.quit()
'''


def verify(root, kind, cli=None, label=None):
    source = Path(root).resolve()
    # Reject links/junctions before copying; destination is a new mkdtemp
    # under the system temp directory, never under the original game.
    simulation._scan_tree(str(source))
    temp_parent = Path(tempfile.gettempdir()).resolve()
    if source == temp_parent or source in temp_parent.parents:
        raise ValueError("temporary directory must be outside source game")
    with tempfile.TemporaryDirectory(prefix="rpykit-runtime-probe-") as folder:
        session = Path(folder)
        staged = session / "game-copy"
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("saves", "cache", "log.txt", "traceback.txt"))
        # Every launcher invocation gets fresh save/persistent paths and no
        # inherited Ren'Py launch controls, even for the baseline.
        launcher = next((p for p in staged.glob("*.exe") if not p.name.lower().startswith("python")), None)
        if launcher is None:
            raise ValueError("no Windows game launcher found")
        results = []
        for patched in (False, True):
            installer_ok = False
            for path in (staged / "log.txt", staged / "traceback.txt", staged / "probe-result.txt"):
                if path.exists():
                    path.unlink()
            for rel in (renpy_compat.REL, renpy_compat.REL + "c"):
                path = staged / "game" / rel
                if path.exists():
                    path.unlink()
            if patched:
                # Survey the source, where the historical mismatch diagnostic
                # exists; generated patch has no private source paths.
                if cli is None:
                    (staged / "game" / renpy_compat.REL).write_text(renpy_compat.render(source), encoding="utf-8")
                else:
                    work_root = session / "work-root"
                    work = work_root / (proj.slugify(str(staged)) + "-" + proj.game_identity(str(staged))[:16])
                    work.mkdir(parents=True, exist_ok=True)
                    simulation._stage_ownership(str(source), str(staged), str(work))
                    cli_path = Path(cli).resolve()
                    if not cli_path.is_file():
                        raise ValueError("CLI path does not exist")
                    command = ([sys.executable, str(cli_path)] if cli_path.suffix.lower() == ".py" else [str(cli_path)])
                    command += [str(staged), "--features", "fontfix,runtime_compat", "--force"]
                    install_env = {k: v for k, v in os.environ.items() if not k.startswith("RENPY_")}
                    install_env["RPYKIT_WORK"] = str(work_root)
                    installed = subprocess.run(command, cwd=ROOT, env=install_env, capture_output=True, timeout=60)
                    installer_ok = installed.returncode == 0
                    if not installer_ok:
                        raise RuntimeError("CLI patch installation failed with exit " + str(installed.returncode))
            harness = staged / "game" / "zzzz_rpykit_probe.rpy"
            harness.write_text(_harness(kind, patched, label), encoding="utf-8")
            compiled = Path(str(harness) + "c")
            if compiled.exists():
                compiled.unlink()
            env = {k: v for k, v in os.environ.items() if not k.startswith("RENPY_")}
            env["RENPY_PATH_TO_SAVES"] = str(session / ("saves-patched" if patched else "saves-baseline"))
            env["RENPY_MULTIPERSISTENT"] = str(session / ("persistent-patched" if patched else "persistent-baseline"))
            env["RENPY_SKIP_MAIN_MENU"] = "1"
            try:
                process = subprocess.run([str(launcher)], cwd=staged, env=env, capture_output=True, timeout=45)
                exited = process.returncode
            except subprocess.TimeoutExpired:
                exited = "timeout"
            log_path = staged / "probe-result.txt"
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            error_path = staged / "traceback.txt"
            error = error_path.read_text(encoding="utf-8", errors="replace") if error_path.exists() else ""
            if kind == "luna" and not patched:
                passed = "was not given the exact contents" in error
                evidence = "original exact-contents mismatch reproduced" if passed else "baseline mismatch unconfirmed"
            else:
                passed = "RPYKIT_PROBE:" in log and not error
                evidence = next((line for line in log.splitlines() if "RPYKIT_PROBE:" in line), "probe unconfirmed")
            if error and not passed:
                evidence += "; " + next((line for line in error.splitlines() if line.startswith(("Exception:", "AttributeError:", "AssertionError:", "TypeError:", "NameError:"))), "see engine traceback")
            results.append({"patched": patched, "passed": passed, "exit": exited, "evidence": evidence,
                            "packaged_cli_verified": bool(patched and passed and installer_ok and Path(cli).suffix.lower() == ".exe") if cli else False,
                            "source_cli_verified": bool(patched and passed and installer_ok and Path(cli).suffix.lower() == ".py") if cli else False})
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game")
    parser.add_argument("--kind", choices=("replay", "luna"), required=True)
    parser.add_argument("--label", help="native main-menu Start target label for --kind replay")
    parser.add_argument("--cli", help="Built CLI .exe or source app_main.py; install fontfix,runtime_compat in the copy")
    args = parser.parse_args()
    results = verify(args.game, args.kind, args.cli, args.label)
    for item in results:
        print(item)
    raise SystemExit(0 if all(item["passed"] for item in results) else 1)
