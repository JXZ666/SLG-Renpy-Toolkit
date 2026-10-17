/* Minimal executable MV/MZ hook sample. This is not a commercial game. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const plugin = fs.readFileSync(process.argv[2], "utf8");

async function sample(engine, rejectLoad, timeout) {
    let resolve, reject, loaded = false, descriptor;
    const wait = new Promise((yes, no) => { resolve = yes; reject = no; });
    const context = {
        Utils: { RPGMAKER_NAME: engine },
        FontFace: function(name, url, options) {
            descriptor = {name, url, options};
            this.load = () => wait;
        },
        document: {fonts: {add: () => { loaded = true; }}},
        Date: {now: () => timeout.value},
        Bitmap: function() { this.fontFace = engine === "MV" ? "GameFont" : "rmmz-mainfont, sans-serif"; },
        Scene_Boot: function() {this.baseReady = true;},
    };
    // Existing plugin behavior must survive ours loading last.
    context.Bitmap.prototype._makeFontNameText = function() { return "italic 28px " + this.fontFace; };
    context.Scene_Boot.prototype.isReady = function() { return this.baseReady; };
    vm.runInNewContext(plugin, context, {filename: "RPYKit_CJK_Font.js"});
    const boot = new context.Scene_Boot();
    assert.equal(boot.isReady(), false, "boot must wait for the CJK face");
    assert.equal(loaded, false);
    assert.equal(descriptor.name, "RPYKitCJK");
    assert.equal(descriptor.options.unicodeRange.includes("U+3400-9FFF"), true);
    assert.equal(descriptor.url.includes("fonts/RPYKit-NotoSansSC.ttf"), true);
    if (rejectLoad) {
        reject(new Error("missing font"));
        await Promise.resolve();
        assert.throws(() => boot.isReady(), /missing font/);
        return;
    }
    if (timeout.trigger) {
        timeout.value = 30001;
        assert.throws(() => boot.isReady(), /load timeout/);
        return;
    }
    resolve({});
    await Promise.resolve();
    assert.equal(loaded, true);
    assert.equal(boot.isReady(), true);
    boot.baseReady = false;
    assert.equal(boot.isReady(), false, "base engine readiness remains required");
    const bitmap = new context.Bitmap();
    const original = bitmap.fontFace;
    const font = bitmap._makeFontNameText();
    assert.equal(font.startsWith("italic 28px " + (engine === "MV" ? "GameFont" : "rmmz-mainfont")), true);
    assert.equal(font.includes("RPYKitCJK"), true);
    if (engine === "MZ") assert.equal(font.indexOf("RPYKitCJK") < font.indexOf("sans-serif"), true);
    assert.equal(bitmap.fontFace, original);
}

(async () => {
    for (const engine of ["MV", "MZ"]) {
        await sample(engine, false, {value: 0});
        await sample(engine, true, {value: 0});
        await sample(engine, false, {value: 0, trigger: true});
    }
    assert.throws(() => vm.runInNewContext(plugin, {document: {fonts: {}}}), /required font\/boot APIs/);
    process.stdout.write("MV/MZ minimal hook samples passed (font loading, failure, timeout, plugin coexistence).\n");
})().catch(error => { console.error(error); process.exitCode = 1; });
