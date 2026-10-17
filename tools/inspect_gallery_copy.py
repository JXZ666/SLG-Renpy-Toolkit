"""Inventory live gallery mechanisms inside an isolated game copy.

The game's own engine loads its normal scripts. The host never unpickles a
script/persistent; diagnostics contain only types, names and counts, no story
text or persistent values. This is research, not qualification for install.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simulation

PROBE = '''# Disposable gallery inventory; isolated copy only.
init 999 python:
    import renpy.store as _rpykit_inspect_store
    import json as _rpykit_inspect_json
    import os as _rpykit_inspect_os
    import re as _rpykit_inspect_re
    config.label_overrides["splashscreen"] = "_rpykit_inspect_gallery"

label _rpykit_inspect_gallery:
    python:
        result = {"standard": [], "custom": [], "screens": []}
        for name, value in list(vars(_rpykit_inspect_store).items()):
            if isinstance(value, Gallery):
                buttons = list(value.buttons.values())
                images = [image for button in buttons for image in button.images]
                result["standard"].append({"name": name, "button_count": len(buttons), "image_count": len(images), "button_conditions": sorted(set(type(c).__name__ for b in buttons for c in b.conditions)), "image_conditions": sorted(set(type(c).__name__ for i in images for c in i.conditions))})
            elif "gallery" in name.lower() or "replay" in name.lower():
                entry = {"name": name, "type": type(value).__name__}
                if isinstance(value, (list, tuple, dict)):
                    entry["count"] = len(value)
                    if isinstance(value, (list, tuple)) and value:
                        item = value[0]
                        entry["item_type"] = type(item).__name__
                        if isinstance(item, (list, tuple)):
                            entry["row_length"] = len(item)
                            entry["row_types"] = [type(field).__name__ for field in item]
                            entry["scope_keys"] = [sorted(field.keys()) for field in item if isinstance(field, dict)]
                        if hasattr(item, "__dict__"):
                            entry["item_fields"] = sorted(vars(item).keys())
                elif hasattr(value, "__dict__") and not isinstance(value, type):
                    entry["fields"] = sorted(vars(value).keys())
                result["custom"].append(entry)
        for key, screen in renpy.display.screen.screens.items():
            name = key[0] if isinstance(key, tuple) else key
            if isinstance(name, str) and ("gallery" in name.lower() or "replay" in name.lower()):
                nodes = [screen.ast] if screen.ast is not None else []
                gates, persistent_fields, uses, seen_calls = 0, set(), set(), 0
                gate_expressions, actions = [], []
                while nodes:
                    node = nodes.pop()
                    nodes.extend(getattr(node, "children", None) or [])
                    block = getattr(node, "block", None)
                    if block is not None:
                        nodes.append(block)
                    for keyword, expr in getattr(node, "keyword", []):
                        if keyword == "action" and isinstance(expr, str):
                            actions.append(_rpykit_inspect_re.sub(r"(['\\\"]).*?\\1", "<literal>", expr))
                    if type(node).__name__ == "SLUse":
                        target = getattr(node, "target", None)
                        if isinstance(target, str):
                            uses.add(target)
                    for expr, block in getattr(node, "entries", []):
                        gates += 1
                        if isinstance(expr, str):
                            persistent_fields.update(_rpykit_inspect_re.findall(r"persistent\\.(\\w+)", expr))
                            seen_calls += int("seen_label" in expr or "seen_image" in expr)
                            gate_expressions.append(_rpykit_inspect_re.sub(r"(['\\\"]).*?\\1", "<literal>", expr))
                        nodes.append(block)
                result["screens"].append({"name": name, "definition_type": type(screen).__name__, "conditional_entries": gates, "persistent_fields": sorted(persistent_fields), "seen_condition_count": seen_calls, "uses": sorted(uses), "gate_expressions": gate_expressions, "actions": actions})
        with open(_rpykit_inspect_os.path.join(config.basedir, "gallery-inventory.json"), "w") as f:
            _rpykit_inspect_json.dump(result, f, sort_keys=True)
    return
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game")
    parser.add_argument("--features", default="fontfix,runtime_compat")
    parser.add_argument("--timeout", type=int, default=40)
    args = parser.parse_args(argv)
    session = simulation.prepare(args.game, args.features.split(","))
    (Path(session.staged_dir) / "game/zzz_rpykit_gallery_inventory.rpy").write_text(PROBE, encoding="utf-8")
    report = Path(session.staged_dir) / "gallery-inventory.json"
    print(json.dumps({"session": session.session_dir, "report": str(report)}), flush=True)
    if not session.launchers:
        raise RuntimeError("No safe launcher found")
    session.launch(session.launchers[0])
    try:
        deadline = time.monotonic() + max(1, args.timeout)
        while not report.is_file() and time.monotonic() < deadline:
            if session.poll() is not None:
                break
            time.sleep(0.5)
        if report.is_file():
            print(report.read_text(encoding="utf-8"), flush=True)
            return 0 if not session.check_runtime_errors() else 1
        print(json.dumps({"probe_complete": False, "errors": session.check_runtime_errors()}), flush=True)
        return 1
    finally:
        session.stop()


if __name__ == "__main__":
    raise SystemExit(main())
