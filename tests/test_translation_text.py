import pytest

from translation_text import protect, restore, is_safe_translation


@pytest.mark.parametrize("text", [
    "Hello world", "Hello {b}[name!q]{/b}{w=0.5} again{p}",
    "Value [player.stats['hp']:.2f] and [items[index]]",
    "Escaped {{ and [[name] end", "%(name)s has %03d points %%", "",
    "Literal __RPYKIT_TOKEN_0__ and [x]", "[array[\"key]\"]] {color=#fff}text{/color}",
])
def test_protection_roundtrip_and_immutable_tokens(text):
    masked, tokens = protect(text)
    assert isinstance(tokens, tuple)
    assert restore(masked, tokens) == text
    assert is_safe_translation(text, text)


def test_translatable_words_change_but_controls_cannot():
    text = "Hello {b}[name]{/b}{w=1} world"
    masked, tokens = protect(text)
    translated = restore(masked.replace("Hello", "你好").replace("world", "世界"), tokens)
    assert translated == "你好 {b}[name]{/b}{w=1} 世界"
    assert is_safe_translation(text, translated)
    assert not is_safe_translation(text, translated.replace("{w=1}", "{w=2}"))
    assert not is_safe_translation("Hello", "你好{nw}")
    assert not is_safe_translation("Hello [name]", "你好[name.upper()]")


def test_restore_rejects_missing_repeated_reordered_and_added_tokens():
    masked, tokens = protect("A {b}B{/b} [name]")
    assert restore(masked.replace(tokens[0][0], ""), tokens) is None
    assert restore(masked + tokens[0][0], tokens) is None
    assert restore(masked.replace(tokens[0][0], "TEMP").replace(tokens[1][0], tokens[0][0]).replace("TEMP", tokens[1][0]), tokens) is None
    assert restore(masked + "{nw}", tokens) is None
    assert restore(masked + "[evil()]", tokens) is None
    assert restore(masked + "__RPYKIT_TOKEN_99__", tokens) is None


def test_no_empty_nul_or_non_string_translation():
    assert not is_safe_translation("hello", " ")
    assert not is_safe_translation("hello", "a\x00b")
    assert not is_safe_translation("hello", None)
    assert restore(None, ()) is None
    with pytest.raises(TypeError):
        protect(None)


def test_bracket_quotes_and_escapes_are_not_evaluated():
    text = "Read [names['a]b']] [obj[\"a\\\"b\"]!q]"
    masked, tokens = protect(text)
    assert len(tokens) == 2
    assert restore(masked, tokens) == text
