"""CLI 入口 — click 实现的多级命令"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from story_engine import __version__
from story_engine.characters.manager import (
    create_example_card,
    delete_card,
    list_cards,
    load_card,
    save_card,
    search_cards,
)
from story_engine.core.config import config_dir, data_dir, get_config
from story_engine.core.models import CharacterCard
from story_engine.lore.lorebook import (
    build_lore_context,
    create_example_lorebook,
    delete_lorebook,
    list_lorebooks,
    load_lorebook,
    save_lorebook,
)
from story_engine.polish import (
    DeAIFilter,
    analyze_rhythm,
    detect_narrative_style,
)

# ── 全局选项 ──────────────────────────────────────────

@click.group()
@click.version_option(version=__version__)
def cli():
    """故事引擎 — AI 小说生成系统"""
    pass


def main():
    """CLI 入口 — 退出前关闭 LLM 连接池（见 L3.2）"""
    try:
        cli()
    finally:
        try:
            from story_engine.api.routes.generate import close_router
            asyncio.run(close_router())
        except Exception:
            pass


# ── 角色卡管理 ────────────────────────────────────────

@cli.group()
def character():
    """角色卡管理"""
    pass


@character.command(name="list")
def cmd_list_characters():
    """列出所有角色卡"""
    cards = list_cards()
    if not cards:
        click.echo("暂无角色卡。运行 `story character example` 创建示例。")
        return
    click.echo(f"共 {len(cards)} 张角色卡：")
    for name in cards:
        click.echo(f"  • {name}")


@character.command()
@click.argument("name")
def show(name: str):
    """查看角色卡详情"""
    card = load_card(name)
    if not card:
        click.echo(f"未找到角色卡：{name}")
        return
    click.echo(card.to_prompt_block())


@character.command()
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="从JSON文件导入")
def import_card(name: str, path: str):
    """从JSON文件导入角色卡"""
    if not path:
        click.echo("请指定 --path")
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    card = CharacterCard(**data)
    card.name = name
    ok = save_card(card, overwrite=True)
    if ok:
        click.echo(f"角色卡「{name}」已保存")
    else:
        click.echo("保存失败")


@character.command()
@click.argument("name")
def delete(name: str):
    """删除角色卡"""
    if delete_card(name):
        click.echo(f"已删除：{name}")
    else:
        click.echo(f"未找到：{name}")


@character.command()
@click.argument("query")
def search(query: str):
    """搜索角色卡"""
    results = search_cards(query)
    if not results:
        click.echo(f"未找到匹配「{query}」的角色卡")
        return
    click.echo(f"找到 {len(results)} 个结果：")
    for name in results:
        click.echo(f"  • {name}")


@character.command()
def example():
    """创建示例角色卡"""
    card = create_example_card()
    ok = save_card(card, overwrite=True)
    if ok:
        click.echo(f"已创建示例角色卡：{card.name}")
        click.echo(f"  路径：{data_dir() / 'characters' / f'{card.name}.json'}")
        click.echo("")
        click.echo(card.to_prompt_block())
    else:
        click.echo("创建失败")


# ── Lorebook 管理 ─────────────────────────────────────

@cli.group()
def lore():
    """Lorebook 设定管理"""
    pass


@lore.command(name="list")
def cmd_list_lore():
    """列出所有设定集"""
    books = list_lorebooks()
    if not books:
        click.echo("暂无设定集。运行 `story lore example` 创建示例。")
        return
    click.echo(f"共 {len(books)} 个设定集：")
    for name in books:
        click.echo(f"  • {name}")


@lore.command(name="show")
@click.argument("name")
def cmd_show_lore(name: str):
    """查看设定集详情"""
    book = load_lorebook(name)
    if not book:
        click.echo(f"未找到设定集：{name}")
        return
    click.echo(f"名称：{book.name}")
    click.echo(f"描述：{book.description}")
    click.echo(f"条目数：{len(book.entries)}")
    for eid, entry in book.entries.items():
        status = "✓" if entry.enabled else "✗"
        click.echo(f"  [{status}] {eid}: {'|'.join(entry.keys)} (P{entry.priority})")


@lore.command(name="delete")
@click.argument("name")
def cmd_delete_lore(name: str):
    """删除设定集"""
    if delete_lorebook(name):
        click.echo(f"已删除设定集：{name}")
    else:
        click.echo(f"未找到：{name}")


@lore.command()
@click.argument("text")
def match(text: str):
    """测试关键词匹配"""
    ctx = build_lore_context(text)
    if ctx:
        click.echo(ctx)
    else:
        click.echo("未匹配到任何设定")


@lore.command(name="example")
def cmd_example_lore():
    """创建示例设定集"""
    book = create_example_lorebook()
    ok = save_lorebook(book, overwrite=True)
    if ok:
        click.echo(f"已创建示例设定集：{book.name}（{len(book.entries)} 个条目）")
    else:
        click.echo("创建失败")


# ── 精修工具 ──────────────────────────────────────────

@cli.group()
def polish():
    """精修工具 — 去AI味 / 风格分析 / 节奏分析"""
    pass


@polish.command()
@click.argument("text_file", type=click.Path(exists=True))
@click.option("--aggressive", is_flag=True, help="激进模式")
@click.option("--report", is_flag=True, help="输出分析报告")
def deai(text_file: str, aggressive: bool, report: bool):
    """去AI味处理文本文件"""
    text = Path(text_file).read_text(encoding="utf-8")
    filter_ = DeAIFilter(aggressive=aggressive)
    cleaned = filter_.clean(text)

    if report:
        r = filter_.report(text)
        click.echo(f"原文长度：{r['original_length']} 字")
        click.echo(f"清理后：{r['cleaned_length']} 字")
        click.echo(f"移除：{r['removed_chars']} 字")
        click.echo(f"软性标记：{r['soft_hits_count']} 处")
        if r['soft_hits']:
            click.echo("\n标记位置：")
            for hit in r['soft_hits'][:10]:
                click.echo(f"  [{hit['match']}] ...{hit['context']}...")
        click.echo("\n--- 清理后内容 ---")
    click.echo(cleaned)


@polish.command()
@click.argument("text_file", type=click.Path(exists=True))
def style(text_file: str):
    """分析文本风格特征"""
    text = Path(text_file).read_text(encoding="utf-8")
    analysis = detect_narrative_style(text)
    click.echo("【风格分析报告】")
    click.echo(f"  字符数：{analysis['character_count']}")
    click.echo(f"  句子数：{analysis['sentence_count']}")
    click.echo(f"  平均句长：{analysis['avg_sentence_length']} 字")
    click.echo(f"  段落数：{analysis['paragraph_count']}")
    click.echo(f"  对话占比：{analysis['dialogue_ratio']*100:.1f}%")


@polish.command()
@click.argument("text_file", type=click.Path(exists=True))
def rhythm(text_file: str):
    """分析章节节奏"""
    text = Path(text_file).read_text(encoding="utf-8")
    analysis = analyze_rhythm(text)
    click.echo("【节奏分析报告】")
    click.echo(f"  钩子数：{analysis['hook_count']}")
    click.echo(f"  钩子密度：{analysis['hook_density']}/千字")
    click.echo(f"  悬念句：{analysis['suspense_count']}")
    click.echo(f"  平均段长：{analysis['avg_paragraph_length']:.0f} 字")
    click.echo(f"  超长段落(>300字)：{analysis['long_paragraphs']} 段")
    click.echo(f"  评级：{analysis['rating']}")


# ── 配置管理 ──────────────────────────────────────────

@cli.group()
def config():
    """配置管理"""
    pass


@config.command(name="show")
def cmd_show_config():
    """显示当前配置"""
    cfg = get_config()
    click.echo(json.dumps(cfg.all(), ensure_ascii=False, indent=2))


@config.command()
@click.argument("key")
@click.argument("value")
def set_key(key: str, value: str):
    """设置配置值，如: story config set llm.deepseek.api_key sk-xxx"""
    cfg = get_config()
    cfg.set(key, value)
    cfg.save()
    click.echo(f"已设置 {key}={value}")


# ── 工具 ──────────────────────────────────────────────

@cli.command()
def info():
    """显示系统信息"""
    click.echo(f"故事引擎 v{__version__}")
    click.echo(f"数据目录：{data_dir()}")
    click.echo(f"配置目录：{config_dir()}")
    click.echo("")
    cards = list_cards()
    books = list_lorebooks()
    click.echo(f"角色卡：{len(cards)} 张")
    click.echo(f"设定集：{len(books)} 个")
    if cards:
        click.echo(f"  角色：{', '.join(cards)}")
    if books:
        click.echo(f"  设定：{', '.join(books)}")
