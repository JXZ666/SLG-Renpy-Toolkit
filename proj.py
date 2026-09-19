"""Project workspace, install manifest, and active-project state."""

import json
import os
import re


def work_root():
    """Where workspaces and the install manifest live.

    A per-user location, forced by the frozen build and shared by the source
    tree on purpose.

    Frozen forces it: the exe unpacks into a temp directory that Windows
    deletes on exit, so anything derived from __file__ there is gone by the
    next launch. That matters more than it sounds - the install manifest would
    read back empty, and `fontfix` refuses to write a file it cannot prove it
    owns, so the second run against the same game would fail outright and
    `--revert` would have no record to prune.

    Source shares it because the manifest is the proof of ownership. Two
    separate workspaces would mean a game fixed by the exe could not be
    reverted by a source checkout, or the other way round. A fixed per-user
    location also means the exe can be moved or re-downloaded without losing
    track of what it installed.

    RPYKIT_WORK overrides it, for tests and for keeping a workspace on a
    different drive.
    """
    env = os.environ.get("RPYKIT_WORK")
    if env:
        return os.path.abspath(env)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "rpykit")


def state_path():
    return os.path.join(work_root(), "state.json")


def slugify(path):
    base = os.path.basename(os.path.normpath(path))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base) or "game"


def work_dir_for(game_dir):
    return os.path.join(work_root(), slugify(game_dir))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def write_json(path, obj):
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# --- active project state -------------------------------------------------

def set_active(work_dir):
    write_json(state_path(), {"active": os.path.abspath(work_dir)})


def get_active():
    st = read_json(state_path()) or {}
    return st.get("active")


def load_project(explicit_work=None):
    """Load project.json from explicit work dir, or the active one."""
    work = explicit_work or get_active()
    if not work:
        raise SystemExit("no active project; run `rpykit init <game_dir>` first")
    proj_path = os.path.join(work, "project.json")
    proj = read_json(proj_path)
    if proj is None:
        raise SystemExit("project.json missing at %s" % proj_path)
    proj["_work"] = work
    return proj


# --- install manifest -----------------------------------------------------

MANIFEST_NAME = "install_manifest.json"


def manifest_path(work_dir):
    return os.path.join(work_dir, MANIFEST_NAME)


def load_manifest(work_dir):
    m = read_json(manifest_path(work_dir))
    if m is None:
        m = {"game_dir": None, "files": [], "quarantined": []}
    return m


def save_manifest(work_dir, manifest):
    write_json(manifest_path(work_dir), manifest)


def record_file(work_dir, game_dir, rel_path, source):
    """Record a file rpykit placed into the game directory."""
    m = load_manifest(work_dir)
    m["game_dir"] = game_dir
    entries = m.setdefault("files", [])
    for e in entries:
        if e["path"] == rel_path:
            e["source"] = source
            break
    else:
        entries.append({"path": rel_path, "source": source})
    save_manifest(work_dir, m)


def record_quarantine(work_dir, game_dir, rel_path, stored_as, source=None):
    """Record a file moved out of the game directory.

    `source` says who moved it, because not every quarantine comes back: fontfix
    moves a rival splashscreen override aside during install and restores it on
    --revert, while init's leftovers are swept away for good. Entries without a
    source are never restored.
    """
    m = load_manifest(work_dir)
    m["game_dir"] = game_dir
    q = m.setdefault("quarantined", [])
    entry = {"path": rel_path, "stored_as": stored_as}
    if source:
        entry["source"] = source
    for i, e in enumerate(q):
        if e["path"] == rel_path:
            q[i] = entry
            break
    else:
        q.append(entry)
    save_manifest(work_dir, m)
