"""Data-only RPG Maker MV/MZ font plugin installation."""
import json
import os
import re
from pathlib import Path

import features
import patch_transaction as transaction
import proj

PLUGIN_NAME = "RPYKit_CJK_Font"
FONT_NAME = "RPYKit-NotoSansSC.ttf"
SOURCE = "adapter:rpgmaker:fontfix"
ASSET_FONT = str(Path(__file__).resolve().parent / "assets" / "NotoSansSC-VF.ttf")


def layout(root):
    candidates = []
    for prefix in ("", "www/"):
        for engine, name in (("rpgmaker_mv", "rpg_core.js"), ("rpgmaker_mz", "rmmz_core.js")):
            rel = prefix + "js/" + name
            if os.path.isfile(os.path.join(root, *rel.split("/"))):
                candidates.append((engine, prefix, rel))
    return candidates


def parse_plugins(data):
    """Accept only the generated var $plugins = JSON; plus comments/whitespace."""
    text = data.decode("utf-8-sig")
    leading = r"(?:\s|//[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)*"
    match = re.match(leading + r"var\s+\$plugins\s*=\s*", text)
    if not match:
        raise transaction.TransactionError("plugins.js is not a generated data-only var $plugins assignment")
    try:
        plugins, end = json.JSONDecoder().raw_decode(text, match.end())
    except ValueError as exc:
        raise transaction.TransactionError("plugins.js must contain strict JSON: " + str(exc)) from exc
    if not re.fullmatch(r"\s*;?" + leading, text[end:]):
        raise transaction.TransactionError("plugins.js contains executable or unknown trailing content")
    if not isinstance(plugins, list):
        raise transaction.TransactionError("plugins.js must contain an array")
    for plugin in plugins:
        if (not isinstance(plugin, dict) or not isinstance(plugin.get("name"), str)
                or not isinstance(plugin.get("status"), bool)
                or not isinstance(plugin.get("parameters"), dict)):
            raise transaction.TransactionError("plugins.js plugin record has an unknown structure")
    return plugins, text, match.end(), end


PLUGIN = r'''/* RPYKit generated font fallback. Revert with SLG-Renpy-Toolkit --revert. */
(function() {
    "use strict";
    var family = "RPYKitCJK", ready = false, failure = null;
    if (typeof FontFace !== "function" || !document.fonts ||
        typeof Bitmap !== "function" || !Bitmap.prototype._makeFontNameText ||
        typeof Scene_Boot !== "function" || !Scene_Boot.prototype.isReady) {
        throw new Error("RPYKit CJK: required font/boot APIs unavailable");
    }
    var face = new FontFace(family, 'url("fonts/RPYKit-NotoSansSC.ttf")', {
        unicodeRange: "U+3000-30FF,U+3400-9FFF,U+F900-FAFF,U+FE10-FE4F,U+FF00-FFEF,U+20000-2FA1F"
    });
    var deadline = Date.now() + 30000;
    face.load().then(function(loaded) {
        document.fonts.add(loaded);
        ready = true;
    }, function(error) { failure = error || new Error("font load failed"); });
    var bootReady = Scene_Boot.prototype.isReady;
    Scene_Boot.prototype.isReady = function() {
        if (failure || (!ready && Date.now() > deadline)) {
            throw new Error("RPYKit CJK font failed: " + (failure || "load timeout"));
        }
        return bootReady.apply(this, arguments) && ready;
    };
    var fontName = Bitmap.prototype._makeFontNameText;
    Bitmap.prototype._makeFontNameText = function() {
        var original = this.fontFace;
        var faces = String(original || "sans-serif").split(",");
        var index = faces.length;
        for (var i = 0; i < faces.length; i++) {
            if (/^\s*(sans-serif|serif|monospace|cursive|fantasy|system-ui)\s*$/i.test(faces[i])) {
                index = i;
                break;
            }
        }
        faces.splice(index, 0, family);
        this.fontFace = faces.join(",");
        try { return fontName.apply(this, arguments); }
        finally { this.fontFace = original; }
    };
})();
'''


def prepare(root):
    candidates = layout(root)
    if len(candidates) != 1:
        raise transaction.TransactionError("RPG Maker layout is unknown or ambiguous")
    engine, prefix, _ = candidates[0]
    stem = "rpg" if engine == "rpgmaker_mv" else "rmmz"
    for rel, token in ((prefix + "js/" + stem + "_core.js", "_makeFontNameText"),
                       (prefix + "js/" + stem + "_scenes.js", "isReady")):
        path = transaction.safe_path(root, rel)
        if not os.path.isfile(path) or token not in Path(path).read_text(encoding="utf-8-sig", errors="replace"):
            raise transaction.TransactionError("required engine hook missing: " + rel)
    plugins_rel = prefix + "js/plugins.js"
    plugin_path = transaction.safe_path(root, plugins_rel)
    if not os.path.isfile(plugin_path):
        raise transaction.TransactionError("plugins.js missing")
    plugins, text, begin, end = parse_plugins(Path(plugin_path).read_bytes())
    own = [p for p in plugins if p["name"] == PLUGIN_NAME]
    if len(own) > 1:
        raise transaction.TransactionError("duplicate RPYKit plugin entries")
    if own:
        own_path = transaction.safe_path(root, prefix + "js/plugins/" + PLUGIN_NAME + ".js")
        if not os.path.isfile(own_path) or not Path(own_path).read_bytes().startswith(b"/* RPYKit generated font fallback."):
            raise transaction.TransactionError("RPYKit plugin name is already used by an unknown plugin")
    plugins = [p for p in plugins if p["name"] != PLUGIN_NAME]
    plugins.append({"name": PLUGIN_NAME, "status": True,
                    "description": "RPYKit Chinese glyph fallback", "parameters": {}})
    # Preserve header, trailing comments, order and all other record values.
    configuration = text[:begin] + json.dumps(plugins, ensure_ascii=False, indent=2) + text[end:]
    if not os.path.isfile(ASSET_FONT):
        raise transaction.TransactionError("bundled Noto font missing")
    return {plugins_rel: configuration.encode("utf-8"),
            prefix + "js/plugins/" + PLUGIN_NAME + ".js": PLUGIN.encode("utf-8"),
            prefix + "fonts/" + FONT_NAME: Path(ASSET_FONT).read_bytes()}, plugins_rel


def support(root):
    reasons = []
    try:
        prepare(root)
    except (OSError, ValueError) as exc:
        reasons.append(str(exc))
    return {"fontfix": {"supported": not reasons, "mechanism": "rpgmaker_plugin" if not reasons else None,
                        "reasons": reasons},
            "intro": {"supported": False, "mechanism": None, "reasons": ["MV/MZ intro bypass is not implemented"]},
            "runtime_compat": {"supported": False, "mechanism": None, "reasons": ["MV/MZ runtime compatibility patches are not implemented"]},
            "gallery": {"supported": False, "mechanism": None, "reasons": ["MV/MZ gallery unlock is not implemented"]}}


def empty_state():
    return {"shim": False, "ours": False, "current": False, "mode": None,
             "font": False, "intro": False, "intro_ours": False, "intro_current": False,
             "runtime_compat": False, "runtime_compat_ours": False, "runtime_compat_current": False,
             "gallery": False, "gallery_ours": False, "gallery_current": False}


def installed_state(root):
    state = empty_state()
    candidates = layout(root)
    if len(candidates) != 1:
        return state
    prefix = candidates[0][1]
    rel = prefix + "js/plugins/" + PLUGIN_NAME + ".js"
    path = transaction.safe_path(root, rel)
    state["shim"] = os.path.isfile(path)
    state["font"] = os.path.isfile(transaction.safe_path(root, prefix + "fonts/" + FONT_NAME))
    manifest = transaction._manifest(root, proj.work_dir_for(root))
    entries = [e for e in manifest["files"] if e.get("source") == SOURCE]
    owned = bool(entries) and all(os.path.isfile(transaction.safe_path(root, e["path"]))
                                  and proj.file_hash(transaction.safe_path(root, e["path"])) == e.get("sha256")
                                  for e in entries)
    state["ours"] = owned
    state["current"] = owned and state["shim"] and Path(path).read_bytes() == PLUGIN.encode("utf-8")
    state["mode"] = "luna" if owned else None
    return state


def run(args):
    root = os.path.abspath(args.game_dir)
    work = getattr(args, "work", None) or proj.work_dir_for(root)
    dry = getattr(args, "dry_run", False)
    if getattr(args, "revert", False):
        result = transaction.revert(root, work, source=SOURCE, dry_run=dry)
        for conflict in result["conflicts"]:
            print("[RPG] kept modified file: " + conflict)
        args.outcome = "conflicts" if result["conflicts"] else ("dry_run" if dry else "changed")
        return 1 if result["conflicts"] else 0
    selected = features.selected(args)
    if any(fid != "fontfix" for fid in selected):
        raise transaction.TransactionError("MV/MZ supports only fontfix; select --features fontfix")
    if not selected:
        args.outcome = "no_changes"
        return 0
    if getattr(args, "mode", "luna") != "luna":
        raise transaction.TransactionError("MV/MZ supports font-only luna mode")
    writes, configuration = prepare(root)
    transaction.install(root, work, writes, source=SOURCE, replace=[configuration], dry_run=dry)
    args.outcome = "dry_run" if dry else "changed"
    print("[RPG] %s: CJK fallback, original Latin faces retained; verify in a disposable copy." % args.outcome)
    return 0
