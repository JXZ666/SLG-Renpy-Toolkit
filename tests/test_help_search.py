"""Search behavior is independent of Tk, games and online services."""

import copy

import pytest

import help_content


def _topic(title, summary, *sections):
    return {"title": title, "summary": summary, "sections": [
        {"heading": heading, "body": list(body)} for heading, body in sections
    ]}


@pytest.fixture
def index(monkeypatch):
    topics = {
        "body": _topic("普通说明", "概览", ("基础", ["可搜索 Alpha 和小写词。"])),
        "heading": _topic("其他说明", "概览", ("Alpha 设置", ["章节正文。"])),
        "title": _topic("Alpha 帮助", "概览", ("基础", ["标题命中。"])),
        "tie": _topic("普通说明", "概览", ("基础", ["可搜索 Alpha 和小写词。"])),
        "split": _topic("跨节主题", "普通概览",
                        ("第一节", ["独有苹果内容。"]),
                        ("第二节", ["独有橘子内容。"])),
    }
    monkeypatch.setattr(help_content, "TOPICS", topics)
    return topics


def test_title_then_heading_then_body_and_ties_keep_topic_order(index):
    assert [row["topic_id"] for row in help_content.search("alpha")] == [
        "title", "heading", "body", "tie"]


def test_query_nfkc_casefold_and_whitespace_are_equivalent(index):
    expected = help_content.search("alpha")
    assert help_content.search("ＡＬＰＨＡ") == expected
    assert help_content.search("\t  AlPhA \n") == expected
    assert help_content.search("alpha ALPHA") == expected


def test_and_terms_can_span_sections_but_not_different_topics(index):
    results = help_content.search("苹果 橘子")
    assert [row["topic_id"] for row in results] == ["split"]
    assert results[0]["section_index"] == 0
    assert results[0]["heading"] == "第一节"
    assert "苹果" in results[0]["snippet"]
    assert help_content.search("alpha 橘子") == []


def test_body_only_term_locates_section_and_relevant_paragraph(index):
    results = help_content.search("橘子")
    assert results == [{"topic_id": "split", "title": "跨节主题",
                        "section_index": 1, "heading": "第二节",
                        "snippet": "独有橘子内容。"}]


def test_summary_is_searchable_and_opens_overview(index):
    results = help_content.search("普通概览")
    assert results[0]["topic_id"] == "split"
    assert results[0]["section_index"] is None
    assert results[0]["heading"] == ""


def test_empty_and_cleared_queries_return_all_overviews(index):
    for query in ("", "\t \n", "　"):
        rows = help_content.search(query)
        assert [row["topic_id"] for row in rows] == list(index)
        assert all(row["section_index"] is None and row["heading"] == ""
                   for row in rows)
    help_content.search("苹果")
    assert len(help_content.search("")) == len(index)


def test_unknown_terms_have_no_results(index):
    assert help_content.search("无此关键词") == []


def test_results_are_independent_and_never_modify_content(index):
    before = copy.deepcopy(index)
    rows = help_content.search("alpha")
    assert all(set(row) == {"topic_id", "title", "section_index", "heading", "snippet"}
               for row in rows)
    rows[0]["title"] = "测试变更"
    rows.clear()
    assert index == before
    assert help_content.search("alpha")[0]["title"] == "Alpha 帮助"


def test_snippet_chooses_relevant_paragraph_and_bounds_length(monkeypatch):
    monkeypatch.setattr(help_content, "TOPICS", {
        "long": _topic("长文", "概览", ("章节", ["无关短文。", "前文" * 150 + "独有词" + "后文" * 150]))
    })
    row = help_content.search("独有词")[0]
    assert "独有词" in row["snippet"]
    assert len(row["snippet"]) <= 134
    assert row["snippet"].startswith("…")
    assert row["snippet"].endswith("…")


@pytest.mark.parametrize("query, topic_id, heading", [
    ("DPAPI", "translation", "服务与凭据"),
    ("预测 不联网", "translation", "它做什么"),
    ("迟到 缓存", "translation", "它做什么"),
    ("全角英文", "faq", "日志与反馈"),
    ("更换启动程序", "library", "首次选择启动程序"),
])
def test_real_chinese_help_searches_body_and_locates_section(query, topic_id, heading):
    rows = help_content.search(query)
    assert rows
    row = next(row for row in rows if row["topic_id"] == topic_id)
    assert row["heading"] == heading
    topic = help_content.topic_for(topic_id)
    assert topic["sections"][row["section_index"]]["heading"] == heading


def test_english_queries_search_real_content_with_fullwidth_casefold():
    assert help_content.search("ｄｐａｐｉ") == help_content.search("DPAPI")
    assert help_content.search("ＧＯＯＧＬＥ")[0]["topic_id"] == "translation"
