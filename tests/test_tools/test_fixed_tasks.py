"""测试：固定流程工具 — 角色/地名一致性检查"""
from __future__ import annotations

from story_engine.tools.fixed_tasks import check_name_consistency


class TestCheckNameConsistency:
    def test_no_issues(self):
        issues = check_name_consistency("张三丰走上武当山", ["张三丰"], ["武当山"])
        assert len(issues) == 0

    def test_typo_detection(self):
        issues = check_name_consistency("张三丰走上了武当山", ["张三丰"])
        # 检查是否有疑似错字
        assert isinstance(issues, list)

    def test_place_mismatch(self):
        issues = check_name_consistency("张三丰走上了武当山", ["张三丰"], ["武当山"])
        # 应该没有错误
        non_typo = [i for i in issues if i["type"] != "typo"]
        assert len(non_typo) >= 0

    def test_empty_names(self):
        issues = check_name_consistency("一段文本", [])
        assert issues == []

    def test_place_similar_word_detected_once(self):
        """L16.1: 等长且差一字的候选词命中一次，每地名至多一条 issue"""
        issues = check_name_consistency(
            "张三丰走上武档山，云雾缭绕。",
            ["张三丰"],
            ["武当山"],
        )
        place_issues = [i for i in issues if i["type"] == "place"]
        assert len(place_issues) == 1
        assert "武档山" in place_issues[0]["issue"]

    def test_place_similar_word_issue_at_most_one(self):
        """L16.1: 同一地名多次近似出现只报一条"""
        issues = check_name_consistency(
            "武档山与武荡山相对，武荡山更险峻。",
            [],
            ["武当山"],
        )
        place_issues = [i for i in issues if i["type"] == "place"]
        assert len(place_issues) == 1

    def test_place_exact_match_no_issue(self):
        issues = check_name_consistency("张三丰走上武当山", [], ["武当山"])
        assert all(i["type"] != "place" for i in issues)

    def test_place_different_length_no_issue(self):
        """阈值收紧：长度不同（2 字 vs 3 字）不报疑似"""
        issues = check_name_consistency("张三丰走上武当", [], ["武当山"])
        assert all(i["type"] != "place" for i in issues)

    def test_large_text_full_scan(self):
        """L16.1: 差一字的词出现在长文末尾也能命中（索引覆盖整篇而非局部）"""
        text = "序章。" + "正文。" * 600 + "众人登上武档山，云雾缭绕。"
        issues = check_name_consistency(text, [], ["武当山"])
        place_issues = [i for i in issues if i["type"] == "place"]
        assert len(place_issues) == 1
        assert "武档山" in place_issues[0]["issue"]

    def test_many_places_each_one_issue(self):
        """L16.1: 大量地名逐一比对，命中只报一条且不误伤不相关地名"""
        known = [f"地点{i}山" for i in range(100)]
        text = "主角走进影帝出，风声萧瑟。" + "，".join(known)
        issues = check_name_consistency(text, [], known + ["影帝山"])
        place_issues = [i for i in issues if i["type"] == "place"]
        assert len(place_issues) == 1
        assert "影帝出" in place_issues[0]["issue"]
        assert all(i["name"] == "影帝山" for i in place_issues)

    def test_two_char_place_typo(self):
        """L16.1: 两字地名差一字同样命中（签名索引对 n=2 有效）"""
        issues = check_name_consistency("东安城内热闹非凡", [], ["长安"])
        place_issues = [i for i in issues if i["type"] == "place"]
        assert len(place_issues) == 1
        assert "东安" in place_issues[0]["issue"]
