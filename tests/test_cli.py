"""测试：CLI — 各命令冒烟（角色/设定集/精修/配置/info）"""

import json

import pytest
from click.testing import CliRunner

from story_engine.cli import cli, main


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """隔离数据目录：字符卡、设定集均写入临时目录。"""
    import story_engine.characters.manager as char_mod
    import story_engine.core.config as cfg_mod
    import story_engine.lore.lorebook as lore_mod

    data_dir = tmp_path / "data"
    cfg_dir = tmp_path / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(char_mod, "CHARACTERS_DIR", data_dir / "characters")
    monkeypatch.setattr(lore_mod, "LOREB_DIR", data_dir / "lore")

    def _data_dir():
        return data_dir

    def _config_dir():
        return cfg_dir

    monkeypatch.setattr(cfg_mod, "data_dir", _data_dir)
    monkeypatch.setattr(cfg_mod, "config_dir", _config_dir)

    cfg_path = cfg_dir / "config.yaml"
    cfg_path.write_text(
        json.dumps({"llm": {"default_model": "test-model", "models": []}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "DEFAULT_CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cfg_mod, "_config_instance", None)
    yield tmp_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCharacterCommands:
    def test_list_empty(self, runner):
        result = runner.invoke(cli, ["character", "list"])
        assert result.exit_code == 0
        assert "暂无角色卡" in result.output

    def test_show_missing(self, runner):
        result = runner.invoke(cli, ["character", "show", "不存在"])
        assert result.exit_code == 0
        assert "未找到" in result.output

    def test_example_then_list(self, runner):
        result = runner.invoke(cli, ["character", "example"])
        assert result.exit_code == 0
        assert "林晓月" in result.output
        result2 = runner.invoke(cli, ["character", "list"])
        assert "林晓月" in result2.output

    def test_show_existing(self, runner):
        runner.invoke(cli, ["character", "example"])
        result = runner.invoke(cli, ["character", "show", "林晓月"])
        assert result.exit_code == 0
        assert "【角色名】林晓月" in result.output

    def test_delete_missing(self, runner):
        result = runner.invoke(cli, ["character", "delete", "没有"])
        assert result.exit_code == 0
        assert "未找到" in result.output

    def test_delete_existing(self, runner):
        runner.invoke(cli, ["character", "example"])
        result = runner.invoke(cli, ["character", "delete", "林晓月"])
        assert result.exit_code == 0
        assert "已删除" in result.output
        assert "林晓月" not in runner.invoke(cli, ["character", "list"]).output

    def test_search_no_results(self, runner):
        result = runner.invoke(cli, ["character", "search", "zzz"])
        assert result.exit_code == 0
        assert "未找到匹配" in result.output

    def test_search_with_results(self, runner):
        runner.invoke(cli, ["character", "example"])
        result = runner.invoke(cli, ["character", "search", "林晓月"])
        assert result.exit_code == 0
        assert "林晓月" in result.output

    def test_import_requires_path(self, runner):
        result = runner.invoke(cli, ["character", "import-card", "x"])
        assert result.exit_code == 0
        assert "请指定 --path" in result.output

    def test_import_from_json(self, runner, tmp_path):
        f = tmp_path / "card.json"
        f.write_text(json.dumps({
            "name": "临时卡",
            "description": "导入测试",
            "personality": "活泼",
        }, ensure_ascii=False), encoding="utf-8")
        result = runner.invoke(cli, ["character", "import-card", "新名", "--path", str(f)])
        assert result.exit_code == 0
        assert "已保存" in result.output
        assert "新名" in runner.invoke(cli, ["character", "list"]).output

    def test_example_save_failure(self, runner, monkeypatch):
        """save_card 返回 False 时输出创建失败"""
        monkeypatch.setattr("story_engine.cli.save_card", lambda *a, **k: False)
        result = runner.invoke(cli, ["character", "example"])
        assert result.exit_code == 0
        assert "创建失败" in result.output

    def test_import_save_failure(self, runner, tmp_path, monkeypatch):
        """import-card 保存失败输出提示"""
        f = tmp_path / "card.json"
        f.write_text(json.dumps({"name": "x"}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr("story_engine.cli.save_card", lambda *a, **k: False)
        result = runner.invoke(cli, ["character", "import-card", "新名", "--path", str(f)])
        assert result.exit_code == 0
        assert "保存失败" in result.output


class TestLoreCommands:
    def test_list_empty(self, runner):
        result = runner.invoke(cli, ["lore", "list"])
        assert result.exit_code == 0
        assert "暂无设定集" in result.output

    def test_show_missing(self, runner):
        result = runner.invoke(cli, ["lore", "show", "不存在"])
        assert result.exit_code == 0
        assert "未找到" in result.output

    def test_show_existing(self, runner):
        runner.invoke(cli, ["lore", "example"])
        result = runner.invoke(cli, ["lore", "show", "天玄大陆"])
        assert result.exit_code == 0
        assert "名称：天玄大陆" in result.output
        assert "条目数" in result.output

    def test_example_then_list(self, runner):
        result = runner.invoke(cli, ["lore", "example"])
        assert result.exit_code == 0
        assert "天玄大陆" in result.output
        result2 = runner.invoke(cli, ["lore", "list"])
        assert "天玄大陆" in result2.output

    def test_delete_missing(self, runner):
        result = runner.invoke(cli, ["lore", "delete", "没有"])
        assert result.exit_code == 0
        assert "未找到" in result.output

    def test_delete_existing(self, runner):
        runner.invoke(cli, ["lore", "example"])
        result = runner.invoke(cli, ["lore", "delete", "天玄大陆"])
        assert result.exit_code == 0
        assert "已删除设定集" in result.output
        assert "天玄大陆" not in runner.invoke(cli, ["lore", "list"]).output

    def test_example_save_failure(self, runner, monkeypatch):
        """save_lorebook 返回 False 时输出创建失败"""
        monkeypatch.setattr("story_engine.cli.save_lorebook", lambda *a, **k: False)
        result = runner.invoke(cli, ["lore", "example"])
        assert result.exit_code == 0
        assert "创建失败" in result.output

    def test_match_no_hit(self, runner):
        result = runner.invoke(cli, ["lore", "match", "完全无关的文本"])
        assert result.exit_code == 0
        assert "未匹配到任何设定" in result.output

    def test_match_hit(self, runner):
        runner.invoke(cli, ["lore", "example"])
        result = runner.invoke(cli, ["lore", "match", "筑基境界"])
        assert result.exit_code == 0
        assert "世界观设定" in result.output


class TestPolishCommands:
    def test_deai(self, runner, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("然而，这是一个测试。值得注意的是，内容正常。", encoding="utf-8")
        result = runner.invoke(cli, ["polish", "deai", str(f)])
        assert result.exit_code == 0
        assert "这是一个测试" in result.output
        assert "然而，" not in result.output
        assert "值得注意的是" not in result.output

    def test_deai_with_report(self, runner, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("然而，测试。", encoding="utf-8")
        result = runner.invoke(cli, ["polish", "deai", str(f), "--report"])
        assert result.exit_code == 0
        assert "原文长度" in result.output
        assert "移除" in result.output

    def test_style(self, runner, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("他走上山。山风呼啸。心中暗想：前路漫漫。", encoding="utf-8")
        result = runner.invoke(cli, ["polish", "style", str(f)])
        assert result.exit_code == 0
        assert "风格分析报告" in result.output
        assert "字符数" in result.output

    def test_rhythm(self, runner, tmp_path):
        f = tmp_path / "text.txt"
        f.write_text("突然，他突破晋级。究竟这一切是为何？", encoding="utf-8")
        result = runner.invoke(cli, ["polish", "rhythm", str(f)])
        assert result.exit_code == 0
        assert "节奏分析报告" in result.output
        assert "钩子数" in result.output


class TestConfigCommands:
    def test_show(self, runner):
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "default_model" in result.output

    def test_set_key(self, runner):
        result = runner.invoke(cli, ["config", "set-key", "llm.temperature", "0.5"])
        assert result.exit_code == 0
        assert "已设置 llm.temperature=0.5" in result.output
        result2 = runner.invoke(cli, ["config", "show"])
        assert '"temperature": "0.5"' in result2.output


class TestInfo:
    def test_info(self, runner):
        result = runner.invoke(cli, ["info"])
        assert result.exit_code == 0
        assert "故事引擎" in result.output
        assert "角色卡" in result.output
        assert "设定集" in result.output

    def test_info_with_data(self, runner):
        """存在角色卡与设定集时 info 应列出明细"""
        runner.invoke(cli, ["character", "example"])
        runner.invoke(cli, ["lore", "example"])
        result = runner.invoke(cli, ["info"])
        assert result.exit_code == 0
        assert "林晓月" in result.output
        assert "天玄大陆" in result.output

    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0." in result.output


class TestMain:
    def test_main_close_router_on_exit(self, monkeypatch):
        """main() 退出前应关闭 LLM 连接池（L3.2）"""
        closed = []

        async def _close():
            closed.append(True)

        monkeypatch.setattr(
            "story_engine.api.routes.generate.close_router", _close, raising=False
        )
        from story_engine import cli as cli_mod

        real_cli = cli_mod.cli

        def _fake_cli():
            raise SystemExit(0)

        cli_mod.cli = _fake_cli
        try:
            with pytest.raises(SystemExit):
                main()
        finally:
            cli_mod.cli = real_cli
        assert closed == [True]

    def test_main_close_router_failure_swallowed(self, monkeypatch):
        """close_router 抛异常时 main() 不应崩溃"""
        from story_engine import cli as cli_mod

        real_cli = cli_mod.cli

        def _fail():
            raise SystemExit(0)

        async def _close_boom():
            raise RuntimeError("close failed")

        cli_mod.cli = _fail
        monkeypatch.setattr(
            "story_engine.api.routes.generate.close_router", _close_boom, raising=False
        )
        try:
            with pytest.raises(SystemExit):
                main()  # close_router 异常被吞，不崩溃
        finally:
            cli_mod.cli = real_cli
