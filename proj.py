"""Project workspace, install manifest, and active-project state."""

import json
import hashlib
import os
import re
import tempfile


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


def canonical_game_dir(game_dir):
    """Return a stable absolute identity for a game directory."""
    return os.path.normcase(os.path.realpath(os.path.abspath(game_dir)))


def game_identity(game_dir):
    canonical = canonical_game_dir(game_dir)
    return hashlib.sha256(canonical.encode("utf-8", "surrogatepass")).hexdigest()


def legacy_work_dir_for(game_dir):
    """The pre-identity workspace name, retained only for safe migration."""
    return os.path.join(work_root(), slugify(game_dir))


def _manifest_matches_game(manifest, game_dir):
    stored = (manifest or {}).get("game_dir")
    if not stored:
        return False
    try:
        return canonical_game_dir(stored) == canonical_game_dir(game_dir)
    except (OSError, TypeError, ValueError):
        return False


def work_dir_for(game_dir):
    """Get an isolated workspace, accepting a matching legacy one if safe.

    Old releases used only the basename, so two games named ``Game`` shared a
    manifest and quarantine. A legacy workspace is adopted only when its
    recorded absolute game path matches this exact directory.
    """
    root = work_root()
    canonical = canonical_game_dir(game_dir)
    ident = game_identity(game_dir)
    current = os.path.join(root, "%s-%s" % (slugify(game_dir), ident[:16]))
    legacy = legacy_work_dir_for(game_dir)

    if legacy == current:
        return current

    current_manifest = read_json(manifest_path(current))
    if _manifest_matches_game(current_manifest, canonical):
        return current
    if os.path.isfile(manifest_path(current)):
        # Do not bypass a present-but-mismatched identity by falling back to a
        # basename workspace. The caller will fail closed on this manifest.
        return current

    legacy_manifest = read_json(manifest_path(legacy))
    if _manifest_matches_game(legacy_manifest, canonical):
        # Keep the old path in place. This is also safe for --dry-run, which
        # must not mutate even the per-user workspace while resolving identity.
        return legacy

    return current


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def write_json(path, obj):
    ensure_dir(os.path.dirname(path))
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".",
                               suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


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
    path = manifest_path(work_dir)
    m = read_json(path)
    if m is None:
        if os.path.exists(path):
            raise ValueError("install manifest is unreadable or invalid: %s" % path)
        m = {"version": 2, "game_dir": None, "files": [], "quarantined": []}
    if not isinstance(m, dict):
        raise ValueError("install manifest must be a JSON object: %s" % path)
    if not isinstance(m.get("files", []), list):
        raise ValueError("install manifest files must be a list: %s" % path)
    if not isinstance(m.get("quarantined", []), list):
        raise ValueError("install manifest quarantined must be a list: %s" % path)
    m.setdefault("files", [])
    m.setdefault("quarantined", [])
    return m


def save_manifest(work_dir, manifest):
    write_json(manifest_path(work_dir), manifest)


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def record_file(work_dir, game_dir, rel_path, source, digest=None):
    """Record a file rpykit placed into the game directory."""
    m = load_manifest(work_dir)
    m["version"] = 2
    m["game_dir"] = os.path.abspath(game_dir)
    m["game_id"] = game_identity(game_dir)
    entries = m.setdefault("files", [])
    if digest is None:
        digest = file_hash(os.path.join(game_dir, *rel_path.split("/")))
    for e in entries:
        if e["path"] == rel_path:
            e["source"] = source
            e["sha256"] = digest
            e["owner"] = "rpykit"
            break
    else:
        entries.append({"path": rel_path, "source": source,
                        "sha256": digest, "owner": "rpykit"})
    save_manifest(work_dir, m)


def record_quarantine(work_dir, game_dir, rel_path, stored_as, source=None):
    """Record a file moved out of the game directory.

    `source` says who moved it, because not every quarantine comes back: fontfix
    moves a rival splashscreen override aside during install and restores it on
    --revert, while init's leftovers are swept away for good. Entries without a
    source are never restored.
    """
    m = load_manifest(work_dir)
    m["version"] = 2
    m["game_dir"] = os.path.abspath(game_dir)
    m["game_id"] = game_identity(game_dir)
    q = m.setdefault("quarantined", [])
    entry = {"path": rel_path, "stored_as": stored_as}
    stored_path = os.path.join(work_dir, "quarantine", *stored_as.split("/"))
    if os.path.isfile(stored_path):
        entry["sha256"] = file_hash(stored_path)
    if source:
        entry["source"] = source
    for i, e in enumerate(q):
        if e["path"] == rel_path:
            q[i] = entry
            break
    else:
        q.append(entry)
    save_manifest(work_dir, m)
