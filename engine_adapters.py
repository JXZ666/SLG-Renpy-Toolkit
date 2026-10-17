"""Static engine detection and lazy dispatch. No game code is executed."""
import os
import re
from pathlib import Path

import rpgmaker


def detect(root):
    root = os.path.abspath(root)
    candidates = []
    if os.path.isdir(os.path.join(root, "renpy")) and os.path.isdir(os.path.join(root, "game")):
        candidates.append(("renpy", "renpy/ + game/"))
    candidates.extend((engine, rel) for engine, _, rel in rpgmaker.layout(root))
    if len(candidates) != 1:
        return {"id": "ambiguous" if candidates else "unknown", "version": None,
                "evidence": [rel for _, rel in candidates]}
    engine, evidence = candidates[0]
    version = None
    if engine != "renpy":
        head = Path(root, *evidence.split("/")).read_text(encoding="utf-8-sig", errors="replace")[:262144]
        match = re.search(r"RPGMAKER_VERSION\s*=\s*['\"]([^'\"]+)['\"]", head)
        version = match.group(1) if match else None
    return {"id": engine, "version": version, "evidence": [evidence]}


def survey(root, quick=False):
    engine = detect(root)
    if engine["id"] == "renpy":
        import compat
        result = compat.survey(root, quick=quick)
        engine["version"] = result["renpy"].get("version")
        result["engine"] = engine
        return result
    recognized = engine["id"] in ("rpgmaker_mv", "rpgmaker_mz")
    reason = "Unknown engine" if engine["id"] == "unknown" else "Multiple engine layouts detected"
    support = rpgmaker.support(root) if recognized else {
        fid: {"supported": False, "mechanism": None, "reasons": [reason]}
        for fid in ("fontfix", "intro", "runtime_compat", "gallery")}
    usable = recognized and support["fontfix"]["supported"]
    return {"game_dir": os.path.abspath(root), "engine": engine,
            "ok": usable, "verdict": "ok" if usable else "bad",
            "label": "可装" if usable else "不适用",
            "reasons": [] if usable else support["fontfix"]["reasons"],
            "renpy": {"version": None, "major": None, "source": None, "name": None},
            "python": {"major": None, "runtime": None}, "arch": None,
            "sources": {}, "splash": {}, "collisions": [], "feature_support": support}


def run(args):
    engine = detect(args.game_dir)
    if engine["id"] == "renpy":
        import cmd_fontfix
        return cmd_fontfix.run(args)
    if engine["id"] in ("rpgmaker_mv", "rpgmaker_mz"):
        return rpgmaker.run(args)
    raise ValueError("Unknown or ambiguous engine; no files changed")


def installed_state(root):
    engine = detect(root)["id"]
    if engine == "renpy":
        import cmd_fontfix
        return cmd_fontfix.installed_state(root)
    if engine in ("rpgmaker_mv", "rpgmaker_mz"):
        return rpgmaker.installed_state(root)
    return rpgmaker.empty_state()


def launchers(root):
    result = []
    for path in sorted(Path(root).glob("*.exe")):
        name = path.name.lower()
        if any(word in name for word in ("unins", "crash", "setup", "install")):
            continue
        stat = path.lstat()
        if path.is_file() and not path.is_symlink() and not getattr(stat, "st_file_attributes", 0) & 0x400:
            result.append(path.name)
    return result
