"""Prepared file transactions for adapters; Ren'Py keeps its existing ledger."""
import copy
import hashlib
import os
import re
import tempfile
from pathlib import Path

import proj


class TransactionError(ValueError):
    pass


def safe_path(root, rel):
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        raise TransactionError("invalid relative path")
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        raise TransactionError("absolute path refused: " + rel)
    parts = rel.split("/")
    if any(p in ("", ".", "..") or ":" in p for p in parts):
        raise TransactionError("unsafe path: " + rel)
    root = os.path.abspath(root)
    current = root
    for part in [None] + parts:
        if part is not None:
            current = os.path.join(current, part)
        if os.path.lexists(current):
            st = os.lstat(current)
            if os.path.islink(current) or getattr(st, "st_file_attributes", 0) & 0x400:
                raise TransactionError("link/reparse point refused: " + current)
    if os.path.commonpath((os.path.realpath(root), os.path.realpath(current))) != os.path.realpath(root):
        raise TransactionError("path escaped root")
    return current


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _read(path):
    return Path(path).read_bytes() if os.path.isfile(path) else None


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="rpykit-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _manifest(root, work):
    manifest = proj.load_manifest(work)
    if manifest.get("game_dir") and proj.canonical_game_dir(manifest["game_dir"]) != proj.canonical_game_dir(root):
        raise TransactionError("manifest belongs to another game")
    if manifest.get("game_id") and manifest["game_id"] != proj.game_identity(root):
        raise TransactionError("manifest identity mismatch")
    return manifest


def install(root, work, writes, source="adapter:fontfix", replace=(), dry_run=False):
    """Install prepared bytes. Only explicitly replaceable foreign files are backed up."""
    manifest = _manifest(root, work)
    new_manifest = copy.deepcopy(manifest)
    entries = {e["path"]: e for e in manifest["files"]}
    destinations, backups = {}, {}
    before = {}
    for rel, data in writes.items():
        if not isinstance(data, bytes):
            raise TransactionError("prepared writes must contain bytes")
        path = safe_path(root, rel)
        if os.path.exists(path) and not os.path.isfile(path):
            raise TransactionError("target is not a regular file: " + rel)
        current = _read(path)
        before[path] = current
        entry = entries.get(rel)
        if entry:
            if entry.get("source") != source or current is None or _digest(current) != entry.get("sha256"):
                raise TransactionError("installed file changed or has another owner: " + rel)
        elif current is not None and rel not in replace:
            raise TransactionError("foreign file refused: " + rel)
        updated = {"path": rel, "source": source, "owner": "rpykit", "sha256": _digest(data)}
        if entry and entry.get("backup"):
            backup = safe_path(work, entry["backup"])
            if _read(backup) is None or _digest(_read(backup)) != entry.get("backup_sha256"):
                raise TransactionError("original backup missing or changed: " + rel)
            updated.update(backup=entry["backup"], backup_sha256=entry["backup_sha256"])
        elif current is not None and not entry:
            backup_rel = "adapter_backups/" + _digest(rel.encode("utf-8")) + ".bin"
            backup = safe_path(work, backup_rel)
            if os.path.lexists(backup):
                raise TransactionError("unowned backup already exists: " + rel)
            backups[backup] = current
            updated.update(backup=backup_rel, backup_sha256=_digest(current))
        new_manifest["files"] = [e for e in new_manifest["files"] if e["path"] != rel] + [updated]
        destinations[path] = data
    manifest_file = safe_path(work, proj.MANIFEST_NAME)
    before[manifest_file] = _read(manifest_file)
    before.update({p: None for p in backups})
    new_manifest.update(version=2, game_dir=os.path.abspath(root), game_id=proj.game_identity(root))
    if dry_run:
        return {"written": list(writes), "conflicts": []}
    missing_dirs = set()
    for path in before:
        parent = os.path.dirname(path)
        while not os.path.exists(parent):
            missing_dirs.add(parent)
            parent = os.path.dirname(parent)
    try:
        for path, data in backups.items():
            _write(path, data)
        for path, data in destinations.items():
            _write(path, data)
        proj.save_manifest(work, new_manifest)
    except Exception:
        for path, data in before.items():
            if data is None:
                if os.path.isfile(path):
                    os.remove(path)
            else:
                _write(path, data)
        for directory in sorted(missing_dirs, key=len, reverse=True):
            if os.path.isdir(directory) and not os.listdir(directory):
                os.rmdir(directory)
        raise
    return {"written": list(writes), "conflicts": []}


def revert(root, work, source="adapter:fontfix", dry_run=False):
    manifest = _manifest(root, work)
    remaining, actions, conflicts, consumed = [], {}, [], []
    for entry in manifest["files"]:
        if entry.get("source") != source:
            remaining.append(entry)
            continue
        path = safe_path(root, entry["path"])
        current = _read(path)
        if current is not None and _digest(current) != entry.get("sha256"):
            remaining.append(entry)
            conflicts.append(entry["path"])
            continue
        original = None
        if entry.get("backup"):
            original = _read(safe_path(work, entry["backup"]))
            if original is None or _digest(original) != entry.get("backup_sha256"):
                remaining.append(entry)
                conflicts.append(entry["path"] + " (backup)")
                continue
        actions[path] = original
        if entry.get("backup"):
            consumed.append(safe_path(work, entry["backup"]))
    if conflicts:
        # A modified config can still reference our plugin/font. Preserve the
        # whole feature until the user resolves the conflict, not half of it.
        return {"restored": [], "conflicts": conflicts}
    if dry_run:
        return {"restored": list(actions), "conflicts": conflicts}
    before = {p: _read(p) for p in actions}
    manifest_file = safe_path(work, proj.MANIFEST_NAME)
    before[manifest_file] = _read(manifest_file)
    try:
        for path, original in actions.items():
            if original is None:
                if os.path.isfile(path):
                    os.remove(path)
            else:
                _write(path, original)
        manifest["files"] = remaining
        proj.save_manifest(work, manifest)
    except Exception:
        for path, data in before.items():
            if data is None:
                if os.path.isfile(path):
                    os.remove(path)
            else:
                _write(path, data)
        raise
    for backup in consumed:
        try:
            os.remove(backup)
        except OSError:
            # A stale backup fails closed on the next install.
            pass
    return {"restored": list(actions), "conflicts": conflicts}
