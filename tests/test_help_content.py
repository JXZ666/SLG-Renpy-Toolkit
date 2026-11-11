"""Contract tests for the offline Help content."""

from pathlib import Path

import pytest

import features
import help_content


FEATURE_SECTIONS = ("它做什么", "适用条件", "风险与验证", "撤销")
EXPECTED_IDS = [
    "fontfix",
    "intro",
    "runtime_compat",
    "gallery",
    "translation",
    "library",
    "simulation",
    "install",
    "paid_content",
    "faq",
]
SOURCE = (Path(__file__).resolve().parents[1] / "help_content.py").read_text(
    encoding="utf-8")
EM_DASH = "\u2014"


def _headings(topic):
    return [section["heading"] for section in topic["sections"]]


def _all_text(topic):
    parts = [topic["title"], topic["summary"]]
    for section in topic["sections"]:
        parts.append(section["heading"])
        parts.extend(section["body"])
    return "\n".join(parts)


def test_every_feature_has_a_topic_and_the_four_required_sections():
    for feature_id in features.ids():
        assert feature_id in help_content.TOPICS
        topic = help_content.topic_for(feature_id)
        assert topic is not None
        headings = _headings(topic)
        for heading in FEATURE_SECTIONS:
            assert heading in headings, (feature_id, heading, headings)


@pytest.mark.parametrize(
    "topic_id, required",
    [
        ("simulation", ("流程", "失败时", "注意")),
        ("install", ("流程", "失败时", "注意")),
        ("paid_content", ("本工具不做什么", "建议")),
        ("faq", ("常见问题", "日志与反馈")),
        ("library", ("首次选择启动程序", "启动与打开文件夹", "版本与配置")),
    ],
)
def test_utility_topics_exist_with_required_sections(topic_id, required):
    topic = help_content.topic_for(topic_id)
    assert topic is not None
    headings = _headings(topic)
    for heading in required:
        assert heading in headings, (topic_id, heading, headings)


def test_every_topic_has_readable_text():
    for topic_id in help_content.topic_ids():
        topic = help_content.topic_for(topic_id)
        assert isinstance(topic, dict), topic_id
        assert isinstance(topic["title"], str) and topic["title"].strip(), topic_id
        assert isinstance(topic["summary"], str) and topic["summary"].strip(), topic_id
        assert isinstance(topic["sections"], list) and topic["sections"], topic_id
        for section in topic["sections"]:
            assert isinstance(section["heading"], str), topic_id
            assert section["heading"].strip(), topic_id
            assert isinstance(section["body"], list) and section["body"], topic_id
            for item in section["body"]:
                assert isinstance(item, str), (topic_id, item)
                assert item.strip(), (topic_id, item)


def test_source_has_no_urls_or_em_dashes():
    for scheme in ("http", "https"):
        assert scheme + "://" not in SOURCE
    assert EM_DASH not in SOURCE


def test_topic_for_missing_is_none_and_results_are_copies():
    assert help_content.topic_for("missing") is None

    topic = help_content.topic_for("fontfix")
    assert topic is not None
    assert topic is not help_content.TOPICS["fontfix"]

    topic["title"] = "被测试改过的标题"
    topic["sections"][0]["body"].append("被测试追加的条目")
    assert help_content.TOPICS["fontfix"]["title"] != "被测试改过的标题"
    assert "被测试追加的条目" not in (
        help_content.TOPICS["fontfix"]["sections"][0]["body"])

    listed = help_content.topics()
    listed[0][1]["title"] = "被测试改过的列表标题"
    assert help_content.TOPICS["fontfix"]["title"] != "被测试改过的列表标题"


def test_paid_content_states_the_boundary_without_promising_a_bypass():
    text = _all_text(help_content.topic_for("paid_content"))
    assert "付费/订阅" in text
    assert "付费" in text and "订阅" in text
    assert "不" in text
    assert "解锁付费" not in text
    assert "绕过" not in text


def test_topic_order_and_key_set_are_stable():
    assert list(help_content.TOPICS) == EXPECTED_IDS
    assert help_content.topic_ids() == EXPECTED_IDS
    assert set(help_content.TOPICS) == set(EXPECTED_IDS)
    assert [topic_id for topic_id, _topic in help_content.topics()] == EXPECTED_IDS
    assert [topic_id for topic_id, _topic in help_content.topics()] == [
        topic_id for topic_id, _topic in help_content.topics()]


def test_translation_explains_session_provider_and_preservation_limits():
    text = _all_text(help_content.topic_for("translation"))
    for required in ("2 秒", "0 到 30", "Google", "DPAPI", "auto", "zh-CN",
                     "迟到", "预测", "NVL", "8.5.2", "测试连接", "原文", "缓存",
                     "不自动转用收费 AI", "普通双击", "停止汉化"):
        assert required in text, required


def test_simulation_help_places_controls_and_session_state_in_log():
    text = _all_text(help_content.topic_for("simulation"))
    assert "运行日志" in text
    assert "全部" in text
    assert "清空日志文本不会清除会话状态" in text
