"""Privacy-safe build inputs and artifact hashes for release provenance."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile


class ProvenanceError(ValueError):
    pass


def _regular_inside(root, path):
    root, path = Path(root).resolve(), Path(path)
    try:
        parts = path.relative_to(root).parts
    except ValueError as exc:
        raise ProvenanceError("artifact outside output root") from exc
    cursor = root
    for part in parts:
        cursor /= part
        if cursor.exists() or cursor.is_symlink():
            info = cursor.lstat()
            if cursor.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ProvenanceError("linked artifact refused")
    if not path.is_file():
        raise ProvenanceError("artifact is missing")
    return path


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hashes(root, output=None):
    """Only source/build inputs are listed; no workspace, game or environment paths."""
    root = Path(root).resolve()
    output = Path(output).resolve() if output is not None else None
    if output is not None and (output == root or output in root.parents):
        raise ProvenanceError("build output cannot contain the source root")
    # Include nested Python packages and runtime JS/JSON resources. Build outputs,
    # virtual environments and per-user state are never release source inputs.
    excluded = {".git", "build", "dist", "release", "__pycache__", ".pytest_cache",
                "node_modules", "_work", "pip", ".mypy_cache", ".ruff_cache",
                ".vscode", ".idea", ".codex", ".claude"}
    paths = set()
    def unreadable(_error):
        raise ProvenanceError("unreadable build input directory")
    for current, folders, files in os.walk(root, followlinks=False, onerror=unreadable):
        folders[:] = [name for name in folders if name not in excluded
                      and not name.lower().startswith((".venv", "venv"))
                      and (output is None or (Path(current) / name).resolve() != output)]
        for name in folders:
            candidate = Path(current) / name
            info = candidate.lstat()
            if candidate.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ProvenanceError("linked build input refused")
        for name in files:
            path = Path(current) / name
            relative = path.relative_to(root)
            if name in ("state.json", "config.local.toml") or name.endswith(".local.json"):
                continue
            if (relative.parts[0] == "assets" or path.suffix.lower() in (".py", ".spec", ".js", ".json")
                    or (len(relative.parts) == 1 and (name.startswith("requirements") and name.endswith(".txt")
                                                     or name in ("build_exe.bat", "LICENSE")))):
                paths.add(path)
    result = {}
    for path in sorted(paths):
        _regular_inside(root, path)
        result[path.relative_to(root).as_posix()] = _hash(path)
    return result


def git_identity(root):
    def run(arguments):
        result = subprocess.run(["git", "-C", str(root)] + arguments,
                                capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else None
    try:
        head = run(["rev-parse", "HEAD"])
        dirty = run(["status", "--porcelain", "--untracked-files=normal"])
    except (OSError, subprocess.SubprocessError):
        head, dirty = None, None
    return {"base_commit": head, "dirty": bool(dirty) if dirty is not None else None}


def windows_version():
    # platform.node()/uname would disclose the host name; never collect them.
    return {"system": platform.system(), "release": platform.release(), "version": platform.version()}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write(output, manifest):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "build_manifest.json"
    fd, temporary = tempfile.mkstemp(prefix="build-manifest-", suffix=".tmp", dir=output)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _validate_identity(source, channel):
    if channel not in ("stable", "local-test"):
        raise ProvenanceError("unknown release channel")
    if not source.get("base_commit") or source.get("dirty") is None:
        raise ProvenanceError("known Git identity required")
    if source["dirty"]:
        raise ProvenanceError("clean Git source required before building")


def begin(root, output, version, modes, channel="stable"):
    manifest = {"schema_version": 2, "app_version": version, "channel": channel, "status": "building",
                "started_at_utc": _now(), "finished_at_utc": None,
                "modes": list(modes), "source": git_identity(root),
                "windows": windows_version(), "python_version": platform.python_version(),
                "inputs": input_hashes(root, output), "artifacts": []}
    try:
        _validate_identity(manifest["source"], channel)
    except ProvenanceError:
        fail(output, manifest, "unclean_or_unknown_source")
        raise
    _write(output, manifest)
    return manifest


def fail(output, manifest, reason):
    manifest.update(status="failed", finished_at_utc=_now(), failure=reason, artifacts=[])
    _write(output, manifest)


def finish(root, output, manifest, executable_names):
    """Fail closed if inputs changed or any requested executable is absent."""
    if input_hashes(root, output) != manifest["inputs"]:
        fail(output, manifest, "build_inputs_changed")
        raise ProvenanceError("build inputs changed while building; rebuild from stable inputs")
    if git_identity(root) != manifest["source"]:
        fail(output, manifest, "git_identity_changed")
        raise ProvenanceError("Git identity changed while building")
    _validate_identity(manifest["source"], manifest["channel"])
    output = Path(output).resolve()
    artifacts = []
    for mode in manifest["modes"]:
        for name in executable_names:
            if mode == "onefile":
                expected = output / "onefile" / name
                paths = [expected]
            elif mode == "onedir":
                folder = output / Path(name).stem
                expected = folder / name
                paths = sorted(p for p in folder.rglob("*") if p.is_file())
            else:
                fail(output, manifest, "unknown_build_mode")
                raise ProvenanceError("unknown build mode")
            if not expected.is_file() or expected.stat().st_size == 0:
                fail(output, manifest, "missing_build_artifact")
                raise ProvenanceError("requested executable is missing or empty")
            for path in paths:
                try:
                    _regular_inside(output, path)
                except ProvenanceError:
                    fail(output, manifest, "linked_build_artifact")
                    raise ProvenanceError("linked artifact refused")
                artifacts.append({"path": path.relative_to(output).as_posix(), "mode": mode,
                                  "bytes": path.stat().st_size, "sha256": _hash(path)})
    # Recheck after hashing large onedir trees, too.
    if input_hashes(root, output) != manifest["inputs"]:
        fail(output, manifest, "build_inputs_changed")
        raise ProvenanceError("build inputs changed during artifact verification")
    if git_identity(root) != manifest["source"]:
        fail(output, manifest, "git_identity_changed")
        raise ProvenanceError("Git identity changed during artifact verification")
    manifest.update(status="complete", finished_at_utc=_now(), artifacts=artifacts,
                    executables=list(executable_names))
    _write(output, manifest)
    return manifest


def verify(root, output):
    """Read-only verification against the recorded source inputs and artifacts."""
    output = Path(output).resolve()
    manifest = json.loads((output / "build_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or input_hashes(root, output) != manifest.get("inputs"):
        raise ProvenanceError("manifest is incomplete or current source differs")
    if manifest.get("schema_version", 1) >= 2:
        _validate_identity(manifest.get("source", {}), manifest.get("channel"))
        if git_identity(root) != manifest["source"]:
            raise ProvenanceError("current Git identity differs from build source")
    if not manifest.get("artifacts"):
        raise ProvenanceError("manifest has no artifacts")
    for entry in manifest["artifacts"]:
        rel = entry["path"]
        if not isinstance(rel, str) or "\\" in rel or ":" in rel or rel.startswith("/") or any(p in ("", ".", "..") for p in rel.split("/")):
            raise ProvenanceError("unsafe artifact path in manifest")
    recorded = {entry["path"] for entry in manifest["artifacts"]}
    if not manifest.get("executables") or not manifest.get("modes"):
        raise ProvenanceError("manifest has no executable targets")
    for mode in manifest["modes"]:
        if mode not in ("onedir", "onefile"):
            raise ProvenanceError("unknown manifest mode")
        for name in manifest["executables"]:
            if not isinstance(name, str) or Path(name).name != name or not name.endswith(".exe"):
                raise ProvenanceError("unsafe executable target")
            expected = "onefile/" + name if mode == "onefile" else Path(name).stem + "/" + name
            if expected not in recorded:
                raise ProvenanceError("manifest is missing an executable target")
    for entry in manifest["artifacts"]:
        rel = entry["path"]
        path = output.joinpath(*rel.split("/"))
        _regular_inside(output, path)
        if _hash(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ProvenanceError("artifact differs from manifest")
    return manifest
