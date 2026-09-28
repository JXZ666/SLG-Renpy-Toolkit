"""Pre-commit privacy scan.

This repository is public, so two classes of string must never be committed:
the contributor's own filesystem paths, and credentials. The scan works on
*shapes* rather than on a list of forbidden literals, because a scrub tool that
spelled out the path it scrubs would itself be the leak.

Run it before committing:

    python tools/check_privacy.py

Exit status is non-zero when anything needs a human look, so it can gate a
commit. Findings are reported as file:line plus the reason; nothing is
rewritten - this tool only reads.

The allowlist below covers placeholder paths that are deliberately generic
(`D:\\Games\\SomeGame` in the README examples, `C:\\Users\\x` in the test
fixtures). Adding an entry is a judgement call: if a hit names a real person,
a real machine or a real game, it belongs in the code as a placeholder, not in
this list.
"""

import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `label %s:\n` is a Python format string, not a path: a single letter drive
# followed by one escape character is always an escape sequence in source.
ESCAPE_TAIL = re.compile(r"^[A-Za-z]:[\\/][nrtbfvaxuUN0'\"\\]$")

# Absolute paths, in the spellings a Windows or POSIX machine actually produces.
SHAPES = (
    ("windows absolute path", re.compile(r"\b[A-Za-z]:[\\/][^\s\"'`)]*")),
    ("UNC path", re.compile(r"\\\\[A-Za-z0-9._-]+\\[^\s\"'`)]*")),
    ("POSIX home directory", re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+")),
    ("email address",
     re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("credential-shaped token", re.compile(
        r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}"
        r"|AIza[0-9A-Za-z_-]{20,}"
        r"|gh[pousr]_[A-Za-z0-9]{20,}"
        r"|xox[baprs]-[A-Za-z0-9-]{10,}"
        r"|AKIA[0-9A-Z]{12,}"
        r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.")),
)

# Generic placeholders that are fine to publish. Matched against the whole hit.
ALLOWED_HITS = (
    r"D:\Games",
    r"D:\temp",
    r"C:/games",
    r"C:\Users\x",
    "AppData\\Local",
    "AppData/Local",
    "example.com",
    "adobe.com",
    "sil.org",
)

# These must never be tracked at all, wherever they appear in the tree.
SECRET_FILES = (
    ".env",
    "credentials.json",
    "config.local.toml",
    "state.json",
    "id_rsa",
)

SKIP_SUFFIXES = (
    ".ttf", ".otf", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".zip",
    ".exe", ".dll", ".pyc", ".bundle",
)


def _tracked():
    out = subprocess.check_output(
        ["git", "-C", REPO, "ls-files"], text=True)
    return [line for line in out.splitlines() if line.strip()]


def _read(path):
    """File text, or None when the file is binary or unreadable."""
    full = os.path.join(REPO, path)
    with open(full, "rb") as f:
        raw = f.read()
    if b"\x00" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def main():
    findings = []
    tracked = _tracked()

    for path in tracked:
        base = os.path.basename(path).lower()
        if base in SECRET_FILES or base.endswith(".pem") or base.endswith(".p12"):
            findings.append((path, 0, "credential file is tracked", base))
            continue
        if path.lower().endswith(SKIP_SUFFIXES):
            continue
        text = _read(path)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for reason, pattern in SHAPES:
                for hit in pattern.findall(line):
                    hit = hit.rstrip(".,;:")
                    if ESCAPE_TAIL.match(hit):
                        continue
                    if any(allowed in hit for allowed in ALLOWED_HITS):
                        continue
                    findings.append((path, number, reason, hit))

    for path, number, reason, hit in findings:
        where = "%s:%d" % (path, number) if number else path
        print("%s  %s: %s" % (where, reason, hit))

    if findings:
        print("\n%d finding(s) in %d tracked file(s). "
              "Replace with a generic placeholder or add it to ALLOWED_HITS "
              "if it genuinely names nobody." % (len(findings), len(tracked)))
        return 1

    print("clean: %d tracked file(s) scanned, nothing personal found."
          % len(tracked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
