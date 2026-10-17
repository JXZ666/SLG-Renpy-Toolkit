"""Prepare an isolated gallery startup probe; optionally launch that copy.

The probe verifies live engine qualifications and resolved replay scope. It
does not claim to have played through replay scenes. It writes only into the
temporary SimulationSession, with isolated saves/multipersistent inherited
from simulation.launch. Originals are only read by simulation.prepare.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import renpy_gallery
import simulation


PROBE = '''# Disposable startup probe; NEVER install into an original game.
init 999 python:
    import json as _rpykit_probe_json
    import os as _rpykit_probe_os
    config.label_overrides["splashscreen"] = "_rpykit_gallery_probe"

label _rpykit_gallery_probe:
    python:
        _rpykit_probe_result = {"scene_playback_tested": False}
        if "_rpykit_replay_action" in globals():
            before = [renpy.seen_label(item.replay) for item in Replay_items]
            qualified = [_rpykit_replay_action(item).get_sensitive() for item in Replay_items]
            after = [renpy.seen_label(item.replay) for item in Replay_items]
            _rpykit_probe_result.update({"kind": "replay", "count": len(qualified), "qualified": all(qualified), "seen_unchanged": before == after, "scope_count": len(_rpykit_replay_scope())})
        else:
            _rpykit_probe_result.update({"kind": "standard", "qualified": all(button.check_unlock() and all(image.check_unlock(False) for image in button.images) for name in OBJECTS for button in getattr(_rpykit_gallery_store, name).buttons.values())})
        with open(_rpykit_probe_os.path.join(config.basedir, "gallery-probe.json"), "w") as f:
            _rpykit_probe_json.dump(_rpykit_probe_result, f, sort_keys=True)
    return
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args(argv)
    report = renpy_gallery.survey(args.game)
    if not report["supported"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    session = simulation.prepare(args.game, ["gallery"])
    probe = Path(session.staged_dir) / "game/zzz_rpykit_gallery_probe.rpy"
    probe.write_text(PROBE.replace("OBJECTS", repr(report["coverage"].get("objects", []))), encoding="utf-8")
    output = {"survey": report, "session": session.session_dir,
              "staged_game": session.staged_dir, "report": str(Path(session.staged_dir) / "gallery-probe.json")}
    print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)
    if args.launch:
        if not session.launchers:
            raise RuntimeError("No safe launcher was discovered in the isolated session")
        session.launch(session.launchers[0])
        result_path = Path(output["report"])
        deadline = time.monotonic() + max(1, args.timeout)
        while not result_path.is_file() and time.monotonic() < deadline:
            if session.poll() is not None:
                break
            time.sleep(0.5)
        if result_path.is_file():
            print(result_path.read_text(encoding="utf-8"), flush=True)
            live_report = json.loads(result_path.read_text(encoding="utf-8"))
            success = bool(live_report.get("qualified")) and live_report.get("seen_unchanged", True)
        else:
            print(json.dumps({"probe_complete": False, "errors": session.check_runtime_errors()}), flush=True)
            success = False
        success = success and not session.check_runtime_errors()
        session.stop()
        # Keep the disposable copy/report for review; source game is untouched.
        return 0 if success else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
