"""Lossless protection of Ren'Py formatting and interpolation syntax.

The constant source is also embedded verbatim in the removable game connector.
It has no game/tool imports, performs no evaluation and has no mutable state.
"""

RUNTIME_SOURCE = r'''
import re as _text_re

def _syntax_tokens(text):
    if not isinstance(text, str):
        return None
    found = []
    i = 0
    while i < len(text):
        start = i
        char = text[i]
        marker = _text_re.match(r"__RPYKITX*_TOKEN_\d+__", text[i:]) if char == "_" else None
        if marker:
            i += len(marker.group(0))
        elif text.startswith("{{", i) or text.startswith("[[", i):
            i += 2
        elif char == "{":
            end = text.find("}", i + 1)
            i = end + 1 if end >= 0 else i + 1
        elif char == "[":
            depth, quote, escaped = 1, None, False
            i += 1
            while i < len(text) and depth:
                c = text[i]
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif quote:
                    if c == quote:
                        quote = None
                elif c in ("'", '"'):
                    quote = c
                elif c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                i += 1
        elif char in "}]":
            i += 1
        elif char == "%":
            match = _text_re.match(r"%(?:%|(?:\([^\n)]*\))?[-+#0 ]*\d*(?:\.\d+)?[diouxXeEfFgGcrsa])", text[i:])
            if not match:
                i += 1
                continue
            i += len(match.group(0))
        else:
            i += 1
            continue
        found.append((start, i, text[start:i]))
    return found

def protect(text):
    """Return a masked string and an immutable tuple of (marker, literal)."""
    if not isinstance(text, str):
        raise TypeError("translation text must be a string")
    prefix = "__RPYKIT_TOKEN_"
    while prefix in text:
        prefix = prefix.replace("_TOKEN_", "X_TOKEN_")
    pieces, tokens, position = [], [], 0
    for index, (start, end, literal) in enumerate(_syntax_tokens(text)):
        marker = prefix + str(index) + "__"
        pieces.extend((text[position:start], marker))
        tokens.append((marker, literal))
        position = end
    pieces.append(text[position:])
    return "".join(pieces), tuple(tokens)

def restore(candidate, tokens):
    """Restore only exact, once-only markers, without adding control syntax."""
    if not isinstance(candidate, str) or len(candidate) > 131072:
        return None
    cursor = 0
    for marker, literal in tokens:
        if candidate.count(marker) != 1:
            return None
        location = candidate.find(marker)
        if location < cursor:
            return None
        cursor = location + len(marker)
    markerless = candidate
    for marker, literal in tokens:
        markerless = markerless.replace(marker, "")
    if _text_re.search(r"__RPYKITX*_TOKEN_\d+__", markerless):
        return None
    if _syntax_tokens(markerless):
        return None
    for marker, literal in tokens:
        candidate = candidate.replace(marker, literal)
    return candidate

def is_safe_translation(original, candidate):
    if not isinstance(original, str) or not isinstance(candidate, str):
        return False
    if not candidate.strip() and original.strip():
        return False
    if len(candidate) > 131072 or "\x00" in candidate:
        return False
    return ([part[2] for part in _syntax_tokens(original)] ==
            [part[2] for part in _syntax_tokens(candidate)])
'''

# Only the fixed, reviewed source above is compiled. Keeping one implementation
# ensures the host and standalone game connector reject the same unsafe output.
exec(compile(RUNTIME_SOURCE, __file__, "exec"))
