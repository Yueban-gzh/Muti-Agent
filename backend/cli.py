"""
终端交互式测试客户端
-------------------
基于 rich 库构建美观的终端界面，封装全部后端 API。
用法: python cli.py

功能：
  1. 用户注册 / 登录
  2. 浏览 Agent 模板
  3. 创建决策任务（自定义 Agent 组合）
  4. 实时轮询任务状态（含加载动画）
  5. 查看完整分析结果（格式化 Markdown 渲染）
  6. 提交反馈采纳
  7. 导出 Markdown 报告到本地
  8. 查看历史记录
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.rule import Rule
from rich.status import Status
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ai.constants import DIMENSION_NAME_MAP
from cli_persona_help import (
    CONTEXT_NOTES_GUIDE,
    DEBATE_COUNT_GUIDE,
    NON_DEBATE_COUNT_GUIDE,
    PERSONA_FIELD_GUIDES,
    STANCE_GUIDE,
)

# ============================================================================
# 全局配置
# ============================================================================

API_BASE = "http://localhost:8000"

console = Console()

# 决策模式选项
DECISION_MODES = {
    "1": ("multi_angle", "多角度分析", "各 Agent 从自身角度独立分析"),
    "2": ("debate", "正反辩论", "Agent 分为支持方和反对方"),
    "3": ("expert_consult", "专家会诊", "不同领域专家联合诊断"),
    "4": ("risk_review", "风险评审", "重点分析失败风险和应对"),
}

# 风格配色
STYLE_MAP = {
    "严谨型": "bold cyan",
    "鼓励型": "bold green",
    "中立型": "bold blue",
    "激进型": "bold red",
    "保守型": "bold yellow",
}


# ============================================================================
# API 客户端封装
# ============================================================================


class APIClient:
    """封装所有后端 API 调用"""

    def __init__(self):
        self.token: str = ""
        self.username: str = ""
        self.role: str = ""

    @property
    def headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    # ---- 认证 ----
    async def register(self, username: str, password: str) -> dict:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.post(f"{API_BASE}/api/auth/register", json={
                "username": username, "password": password
            })
            return r.json() if r.status_code in (200, 201) else {"error": r.text}

    async def login(self, username: str, password: str) -> dict:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.post(f"{API_BASE}/api/auth/login", data={
                "username": username, "password": password
            })
            if r.status_code == 200:
                data = r.json()
                self.token = data["access_token"]
                self.username = username
                return data
            return {"error": r.text}

    # ---- 模板 ----
    async def get_templates(self) -> list:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.get(f"{API_BASE}/api/templates/", headers=self.headers)
            return r.json().get("templates", []) if r.status_code == 200 else []

    async def recommend_agents(
        self, question: str, decision_mode: str, agent_count: int = 3
    ) -> dict:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as c:
            r = await c.post(
                f"{API_BASE}/api/templates/recommend",
                json={
                    "question": question,
                    "decision_mode": decision_mode,
                    "agent_count": agent_count,
                },
                headers=self.headers,
            )
            return r.json() if r.status_code == 200 else {"error": r.text}

    # ---- 任务 ----
    async def create_task(
        self,
        question: str,
        mode: str,
        agents: list,
        weight: str | None = None,
        *,
        context_notes: str | None = None,
        legacy_auto_finalize: bool = False,
    ) -> dict:
        payload = {
            "question": question,
            "decision_mode": mode,
            "agent_count": len(agents),
            "agents": agents,
            "start_discussion": not legacy_auto_finalize,
            "legacy_auto_finalize": legacy_auto_finalize,
        }
        if weight:
            payload["weight_config"] = weight
        if context_notes:
            payload["context_notes"] = context_notes
        async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
            r = await c.post(
                f"{API_BASE}/api/tasks/create",
                json=payload,
                headers=self.headers,
            )
            return r.json() if r.status_code == 201 else {"error": r.text}

    async def post_message(
        self, task_id: int, content: str, reply_scope: str = "all_brief",
        target_agent_id: int | None = None,
    ) -> dict:
        payload = {"content": content, "reply_scope": reply_scope}
        if target_agent_id:
            payload["target_agent_id"] = target_agent_id
        async with httpx.AsyncClient(timeout=300, trust_env=False) as c:
            r = await c.post(
                f"{API_BASE}/api/tasks/{task_id}/messages",
                json=payload,
                headers=self.headers,
            )
            return r.json() if r.status_code == 201 else {"error": r.text}

    async def get_debate_roster(self, task_id: int) -> list:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.get(
                f"{API_BASE}/api/tasks/{task_id}/debate-roster",
                headers=self.headers,
            )
            return r.json() if r.status_code == 200 else []

    async def debate_agent_exchange(self, task_id: int) -> dict:
        async with httpx.AsyncClient(timeout=600, trust_env=False) as c:
            r = await c.post(
                f"{API_BASE}/api/tasks/{task_id}/debate/agent-exchange",
                headers=self.headers,
            )
            return r.json() if r.status_code == 200 else {"error": r.text}

    async def finalize_task(self, task_id: int) -> dict:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
            r = await c.post(
                f"{API_BASE}/api/tasks/{task_id}/finalize",
                headers=self.headers,
            )
            return r.json() if r.status_code == 200 else {"error": r.text}

    async def get_status(self, task_id: int) -> dict:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.get(f"{API_BASE}/api/tasks/{task_id}/status",
                            headers=self.headers)
            return r.json() if r.status_code == 200 else {}

    async def get_result(self, task_id: int) -> dict:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
            r = await c.get(f"{API_BASE}/api/tasks/{task_id}/result",
                            headers=self.headers)
            return r.json() if r.status_code == 200 else {}

    async def export_report(self, task_id: int) -> str | None:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
            r = await c.get(f"{API_BASE}/api/history/{task_id}/export",
                            headers=self.headers)
            return r.text if r.status_code == 200 else None

    # ---- 反馈 ----
    async def submit_feedback(self, task_id: int, chosen_type: str,
                              chosen_agent_id: int | None = None,
                              comment: str = "") -> dict:
        payload = {
            "task_id": task_id, "chosen_type": chosen_type,
            "chosen_agent_id": chosen_agent_id, "comment": comment,
        }
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.post(f"{API_BASE}/api/feedback/vote", json=payload,
                             headers=self.headers)
            return r.json() if r.status_code == 201 else {"error": r.text}

    # ---- 历史 ----
    async def get_history(self) -> list:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
            r = await c.get(f"{API_BASE}/api/history/", headers=self.headers)
            return r.json() if r.status_code == 200 else []


# ============================================================================
# UI 组件
# ============================================================================


def print_banner():
    """打印系统横幅"""
    banner = Text.assemble(
        ("\n  ╔", "dim"),
        ("══════════════════════════════════════════", "dim"),
        ("╗\n", "dim"),
        ("  ║", "dim"),
        ("  可配置多智能体决策辅助系统", "bold cyan"),
        ("         ", ""),
        ("║\n", "dim"),
        ("  ║", "dim"),
        ("  Terminal Interactive Client  v1.0", "green"),
        ("     ", ""),
        ("║\n", "dim"),
        ("  ╚", "dim"),
        ("══════════════════════════════════════════", "dim"),
        ("╝", "dim"),
    )
    console.print(banner)
    console.print()


def print_section(title: str):
    """打印分隔标题"""
    console.print(Rule(f"[bold cyan]{title}"))


def confirm(msg: str) -> bool:
    """确认对话框"""
    return Confirm.ask(f"[yellow]?[/] {msg}", default=True)


def ask(msg: str, default: str = "", password: bool = False) -> str:
    """输入提示"""
    return Prompt.ask(f"[yellow]?[/] {msg}", default=default, password=password)


def info(msg: str):
    console.print(f"  [dim]ℹ[/] {msg}")


def success(msg: str):
    console.print(f"  [green]✓[/] {msg}")


def error(msg: str):
    console.print(f"  [red]✗[/] {msg}")


# ============================================================================
# 业务场景
# ============================================================================


async def scene_auth(client: APIClient) -> bool:
    """登录/注册流程"""
    print_section("用户认证")

    while True:
        console.print("  [1] 登录")
        console.print("  [2] 注册新账号")
        console.print("  [0] 退出")
        choice = Prompt.ask("  选择", choices=["1", "2", "0"], default="1")

        if choice == "0":
            return False

        username = ask("  用户名")
        password = ask("  密码", password=True)

        if choice == "1":
            with Status("[cyan]正在登录...", spinner="dots"):
                result = await client.login(username, password)
            if "error" in result:
                error(f"登录失败: {result.get('error', '未知错误')[:200]}")
                continue
            success(f"欢迎回来, [bold]{username}[/]!")
            return True
        else:
            if len(password) < 6:
                error("密码至少 6 位")
                continue
            with Status("[cyan]正在注册...", spinner="dots"):
                result = await client.register(username, password)
            if "error" in result:
                error(f"注册失败: {result.get('error', '未知错误')[:200]}")
                continue
            success("注册成功! 正在自动登录...")
            await client.login(username, password)
            return True


DEBATE_STANCE_CHOICES = {
    "1": ("pro", "支持方（正方）"),
    "2": ("con", "反对方（反方）"),
    "3": ("judge", "评审方"),
}


STANCE_LABEL_MAP = {"pro": "支持方", "con": "反对方", "judge": "评审方"}


def _show_persona_field_guide(field_key: str) -> None:
    label, help_text, example = PERSONA_FIELD_GUIDES[field_key]
    console.print(f"    [bold]{label}[/] — [dim]{help_text}[/]")
    console.print(f"    [dim]示例: {example}[/]")


def _pick_debate_stance(*, template_name: str | None = None, suggested: str | None = None) -> tuple[str, str]:
    if template_name:
        sug_label = STANCE_LABEL_MAP.get(suggested or "", suggested or "无")
        console.print(f"    [dim]模板「{template_name}」推荐立场: {sug_label}[/]")
    console.print(f"    [dim]{STANCE_GUIDE}[/]")
    console.print("    [1] 支持方(正方)  [2] 反对方(反方)  [3] 评审方")
    sc = Prompt.ask("    指定立场", choices=["1", "2", "3"], default="1")
    return DEBATE_STANCE_CHOICES[sc]


def _prompt_required_field(field_key: str) -> str:
    _show_persona_field_guide(field_key)
    label = PERSONA_FIELD_GUIDES[field_key][0]
    while True:
        val = Prompt.ask(f"    {label}").strip()
        if val:
            return val
        error(f"{label}不能为空")


def _prompt_optional_field(field_key: str, *, default: str = "") -> str | None:
    _show_persona_field_guide(field_key)
    label = PERSONA_FIELD_GUIDES[field_key][0]
    val = Prompt.ask(f"    {label}（回车跳过）", default=default).strip()
    if val:
        return val
    return default if default else None


def _prompt_optional_override(field_key: str, default: str | None) -> str | None:
    """回车保留模板默认；输入新值则覆盖。"""
    _show_persona_field_guide(field_key)
    label = PERSONA_FIELD_GUIDES[field_key][0]
    hint = (default or "")[:60]
    if len((default or "")) > 60:
        hint += "…"
    val = Prompt.ask(
        f"    {label} [dim](回车保留当前: {hint or '空'})[/]",
        default="",
    ).strip()
    if not val:
        return None
    if default and val == default:
        return None
    return val


def _pick_agent_count(mode_key: str) -> int:
    if mode_key == "debate":
        console.print(Panel(DEBATE_COUNT_GUIDE, title="辩论人数说明", border_style="yellow"))
        default = "3"
    else:
        console.print(f"  [dim]{NON_DEBATE_COUNT_GUIDE}[/]")
        default = "3"
    return int(
        IntPrompt.ask(
            "  选择专家/辩手人数",
            choices=["2", "3", "4", "5"],
            default=default,
        )
    )


def _validate_debate_slots(slots: list[dict]) -> bool:
    stances = [s.get("stance") for s in slots]
    if "pro" not in stances or "con" not in stances:
        error("辩论须至少 1 名支持方 + 1 名反对方；请调整人数或立场后重试")
        return False
    if stances.count("judge") > 1:
        error("评审方最多 1 名")
        return False
    n = len(slots)
    if n == 2 and "judge" not in stances:
        info("当前为 2 人辩论（无评审），交锋后不会自动生成评审归纳")
    elif n >= 4:
        info("4 人以上请确认正方/反方侧人数均衡，避免只有一方多人发言")
    return True


async def _slots_from_recommendation(
    client: APIClient,
    question: str,
    mode_key: str,
    agent_count: int,
    templates: list[dict],
) -> list[dict] | None:
    """调用推荐 API，用户确认后生成 slot 列表；取消则返回 None。"""
    by_id = {t["id"]: t for t in templates}
    with Status("[cyan]正在根据问题推荐人设...", spinner="dots"):
        rec = await client.recommend_agents(question, mode_key, agent_count)

    if "error" in rec:
        error(f"推荐失败: {str(rec['error'])[:200]}")
        return None

    agents = rec.get("agents") or []
    if not agents:
        error("推荐结果为空，请改用手动配置")
        return None

    console.print(Panel(rec.get("hint", ""), title="系统推荐说明", border_style="green"))
    rt = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    rt.add_column("#", width=3)
    rt.add_column("模板/名称", width=14)
    rt.add_column("背景", width=22)
    rt.add_column("关注", width=20)
    rt.add_column("推荐立场", width=8)
    for i, a in enumerate(agents, 1):
        sug = a.get("suggested_stance")
        rt.add_row(
            str(i),
            a.get("agent_name", "-"),
            (a.get("role_description") or "-")[:20],
            (a.get("focus_area") or "-")[:18],
            STANCE_LABEL_MAP.get(sug, "-") if mode_key == "debate" else "-",
        )
    console.print(rt)

    if not Confirm.ask("采用以上推荐人设?", default=True):
        return None

    slots: list[dict] = []
    for a in agents:
        tid = a.get("template_id")
        tpl = by_id.get(tid)
        if not tpl:
            error(f"推荐模板 ID {tid} 不可用，请改用手动配置")
            return None
        slot: dict = {"source": "template", "template": tpl, "stance": None}
        if mode_key == "debate":
            sug = a.get("suggested_stance")
            if sug in STANCE_LABEL_MAP:
                use_sug = Confirm.ask(
                    f"  「{tpl['name']}」采用推荐立场「{STANCE_LABEL_MAP[sug]}」?",
                    default=True,
                )
                slot["stance"] = sug if use_sug else _pick_debate_stance(template_name=tpl["name"])[0]
            else:
                slot["stance"] = _pick_debate_stance(template_name=tpl["name"])[0]
        slots.append(slot)

    extra_all = Confirm.ask("是否为全体专家添加统一的「本案补充」?", default=False)
    if extra_all:
        _show_persona_field_guide("extra_notes")
        note = Prompt.ask("    本案补充", default="").strip()
        if note:
            for slot in slots:
                slot["extra_notes"] = note

    return slots


def _configure_agent_slot(
    templates: list[dict],
    idx: int,
    *,
    mode_key: str,
) -> dict:
    """配置单个 Agent：模板 / 自定义 / 模板+微调。"""
    console.print(f"\n  [bold]Agent {idx + 1}[/] 人设配置")
    console.print("    [1] 从模板选择（可微调四字段 + 本案补充）")
    console.print("    [2] 完全自定义人设（手填名称/背景/关注/风格）")
    console.print(
        "    [dim]每项输入前会显示说明与示例；也可退出后改选「系统推荐人设」。[/]"
    )
    src = Prompt.ask("    选择", choices=["1", "2"], default="1")

    slot: dict = {"source": "template" if src == "1" else "custom", "stance": None}

    if src == "1":
        while True:
            num = IntPrompt.ask("    模板编号（见上方表格）", default=1)
            if 1 <= num <= len(templates):
                tpl = templates[num - 1]
                break
            error(f"请输入 1-{len(templates)}")
        slot["template"] = tpl
        info(f"已选模板: {tpl['name']}")

        if Confirm.ask("    是否微调该 Agent 的人设字段?", default=False):
            console.print("    [dim]以下每项回车=保留模板原值[/]")
            ov = _prompt_optional_override("agent_name", tpl.get("name"))
            if ov:
                slot["agent_name"] = ov
            for key in ("role_description", "focus_area", "tone"):
                ov = _prompt_optional_override(key, tpl.get(key))
                if ov:
                    slot[key] = ov

        extra = _prompt_optional_field("extra_notes")
        if extra:
            slot["extra_notes"] = extra
    else:
        console.print(Panel(
            "自定义人设会完整写入本任务，不关联模板库。\n"
            "「展示名称」「专业背景」必填；「关注重点」可空。",
            title="自定义说明",
            border_style="dim",
        ))
        slot["template"] = None
        slot["agent_name"] = _prompt_required_field("agent_name")
        slot["role_description"] = _prompt_required_field("role_description")
        slot["focus_area"] = _prompt_optional_field("focus_area")
        tone = _prompt_optional_field("tone", default="理性、简洁、有依据")
        slot["tone"] = tone or "理性、简洁、有依据"
        extra = _prompt_optional_field("extra_notes")
        if extra:
            slot["extra_notes"] = extra
        info(f"自定义: {slot['agent_name']}")

    if mode_key == "debate":
        suggested = slot["template"].get("default_stance") if slot.get("template") else None
        tname = slot["template"]["name"] if slot.get("template") else slot.get("agent_name")
        stance_key, stance_name = _pick_debate_stance(
            template_name=tname, suggested=suggested
        )
        slot["stance"] = stance_key
        info(f"立场: {stance_name}")

    return slot


def _slot_display_name(slot: dict) -> str:
    if slot.get("agent_name"):
        return slot["agent_name"]
    tpl = slot.get("template")
    return tpl["name"] if tpl else "?"


def _slot_display_role(slot: dict) -> str:
    if slot.get("role_description"):
        return slot["role_description"][:24]
    tpl = slot.get("template")
    return (tpl.get("role_description") or "-")[:24] if tpl else "-"


def _slot_to_agent_payload(slot: dict) -> dict:
    item: dict = {}
    if slot["source"] == "template":
        item["template_id"] = slot["template"]["id"]
        for key in ("agent_name", "role_description", "focus_area", "tone", "extra_notes"):
            if slot.get(key):
                item[key] = slot[key]
    else:
        item["agent_name"] = slot["agent_name"]
        item["role_description"] = slot["role_description"]
        for key in ("focus_area", "tone", "extra_notes"):
            if slot.get(key):
                item[key] = slot[key]
    if slot.get("stance"):
        item["stance"] = slot["stance"]
    return item


async def scene_create_task(client: APIClient):
    """创建决策任务"""
    print_section("创建决策任务")

    # --- 输入问题 ---
    console.print("\n[bold]Step 1:[/] 请输入你的决策问题")
    console.print("  [dim]示例: 是否应该开发校园二手交易小程序？[/]")
    console.print("  [dim]示例: 社团是否应该引入自动化报名和筛选系统？[/]")
    question = ask("\n  决策问题").strip()
    if not question:
        error("问题不能为空")
        return

    console.print(Panel(CONTEXT_NOTES_GUIDE, title="背景说明（可选）", border_style="dim"))
    context_notes = Prompt.ask("\n  背景说明", default="").strip() or None

    # --- 选择模式 ---
    console.print(f"\n[bold]Step 2:[/] 选择决策模式")
    for key, (mode, name, desc) in DECISION_MODES.items():
        console.print(f"  [{key}] {name} — [dim]{desc}[/]")
    mode_choice = Prompt.ask("  选择", choices=list(DECISION_MODES.keys()), default="1")
    mode_key, mode_name, _ = DECISION_MODES[mode_choice]

    console.print(f"\n[bold]Step 3:[/] 配置 Agent 人设（模板 / 自定义 / 模板微调）")
    with Status("[cyan]加载模板...", spinner="dots"):
        templates = await client.get_templates()

    if not templates:
        error("没有可用模板")
        return

    # 展示模板
    tpl_table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    tpl_table.add_column("编号", width=6, style="dim")
    tpl_table.add_column("名称", width=16)
    tpl_table.add_column("五行人格", width=14)
    tpl_table.add_column("职业", width=16, style="green")
    tpl_table.add_column("关注领域", width=36, style="dim")
    tpl_table.add_column("风格", width=10)

    for i, t in enumerate(templates, 1):
        tpl_table.add_row(
            str(i), t["name"],
            _element_tag(t["name"]),
            t.get("role_description", "-"),
            t.get("focus_area", "-"),
            t.get("tone", "-"),
        )
    console.print(tpl_table)

    agent_count = _pick_agent_count(mode_key)

    console.print("\n  [bold]人设配置方式[/]")
    console.print("    [1] 系统推荐（根据决策问题自动匹配专家组合）")
    console.print("    [2] 手动逐个配置（自选模板 / 自定义 / 微调）")
    setup = Prompt.ask("  选择", choices=["1", "2"], default="1")

    selected_slots: list[dict] | None = None
    if setup == "1":
        selected_slots = await _slots_from_recommendation(
            client, question, mode_key, agent_count, templates
        )
        if selected_slots is None and not Confirm.ask(
            "未采用推荐，是否改用手动配置?", default=True
        ):
            info("已取消")
            return

    if not selected_slots:
        selected_slots = []
        for idx in range(agent_count):
            selected_slots.append(
                _configure_agent_slot(templates, idx, mode_key=mode_key)
            )

    if mode_key == "debate" and not _validate_debate_slots(selected_slots):
        return

    console.print()
    summary = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    summary.add_column("名称", width=16)
    summary.add_column("来源", width=8)
    summary.add_column("立场", width=8)
    summary.add_column("角色/背景", width=28)
    for slot in selected_slots:
        src = "自定义" if slot["source"] == "custom" else "模板"
        summary.add_row(
            _slot_display_name(slot),
            src,
            STANCE_LABEL_MAP.get(slot.get("stance"), "-"),
            _slot_display_role(slot),
        )
    console.print(Panel(summary, title=f"任务摘要 · {mode_name}", border_style="cyan"))
    summary2 = Table(box=box.SIMPLE, show_header=False)
    summary2.add_column("项目", style="dim", width=16)
    summary2.add_column("内容")
    summary2.add_row("决策问题", question)
    if context_notes:
        summary2.add_row("背景说明", context_notes[:80])
    console.print(summary2)

    if not confirm("确认提交?"):
        info("已取消")
        return

    agents_payload = [_slot_to_agent_payload(s) for s in selected_slots]

    use_legacy = Confirm.ask("跳过讨论室、直接后台分析?", default=False)

    with Status("[cyan]正在提交任务...", spinner="dots"):
        result = await client.create_task(
            question,
            mode_key,
            agents_payload,
            context_notes=context_notes,
            legacy_auto_finalize=use_legacy,
        )

    if "error" in result:
        error(f"创建失败: {result['error'][:200]}")
        return

    task_id = result["task_id"]
    success(f"任务已创建 (ID: {task_id}) status={result.get('status')}")

    if use_legacy or result.get("status") == "pending":
        await scene_poll_status(client, task_id)
        return

    await scene_discussion(client, task_id, is_debate=(mode_key == "debate"))
    await scene_poll_status(client, task_id)


STANCE_PANEL_STYLE = {
    "pro": "green",
    "con": "red",
    "judge": "yellow",
    "neutral": "cyan",
}


def _print_agent_message(am: dict) -> None:
    title = am.get("agent_display_name") or am.get("agent_name") or "Agent"
    stance = am.get("stance") or "neutral"
    label = am.get("stance_label", "")
    if label and label not in title:
        title = f"{title}"
    style = STANCE_PANEL_STYLE.get(stance, "white")
    console.print(Panel(am.get("content", ""), title=title, border_style=style))


async def scene_discussion(client: APIClient, task_id: int, *, is_debate: bool = False):
    """讨论室：用户多轮交流后收束。"""
    print_section(f"任务 {task_id} 讨论室")

    if is_debate:
        roster = await client.get_debate_roster(task_id)
        if roster:
            rt = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            rt.add_column("ID", width=4)
            rt.add_column("辩手", width=28)
            rt.add_column("立场", width=8)
            rt.add_column("背景", width=24)
            for r in roster:
                rt.add_row(
                    str(r.get("task_agent_id", "")),
                    r.get("agent_display_name", r.get("agent_name", "")),
                    r.get("stance_label", "-"),
                    (r.get("role_description") or "-")[:22],
                )
            console.print(Panel(rt, title="辩手席位", border_style="magenta"))
        info("每轮交锋后可选择：补充发言 / 辩手继续交锋 / 结束并生成正式分析")

    if is_debate:
        await _debate_discussion_loop(client, task_id)
        return

    roster = await client.get_debate_roster(task_id)
    if roster:
        rt = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        rt.add_column("ID", width=4)
        rt.add_column("专家", width=28)
        rt.add_column("背景", width=36)
        for r in roster:
            rt.add_row(
                str(r.get("task_agent_id", "")),
                r.get("agent_display_name", r.get("agent_name", "")),
                (r.get("role_description") or "-")[:34],
            )
        console.print(Panel(rt, title="讨论专家", border_style="cyan"))

    info("发言将发送给全部专家，每人各回复一条；直接回车结束并生成正式分析")
    while True:
        content = Prompt.ask("\n  [你/决策方]", default="").strip()
        if not content:
            break
        with Status("[cyan]全体专家思考中...", spinner="dots"):
            resp = await client.post_message(task_id, content, reply_scope="all_brief")
        if "error" in resp:
            error(str(resp["error"])[:300])
            continue
        for am in resp.get("agent_messages", []):
            _print_agent_message(am)

    await _finalize_task(client, task_id)


async def _finalize_task(client: APIClient, task_id: int):
    with Status("[cyan]正在生成正式分析（含讨论纪要）...", spinner="dots"):
        fin = await client.finalize_task(task_id)
    if "error" in fin:
        error(f"收束失败: {fin['error'][:200]}")
    else:
        success(f"已进入收束: {fin.get('status')}")


async def _debate_discussion_loop(client: APIClient, task_id: int):
    """辩论模式：每轮交锋后由用户选择下一步。"""
    while True:
        console.print()
        console.print("[bold]本轮结束后，请选择：[/]")
        console.print("  [1] 我补充发言（触发：支持方→反对方→评审）")
        console.print("  [2] 我不说话，让辩手继续交锋一轮")
        console.print("  [3] 结束讨论，生成正式分析报告")
        choice = Prompt.ask("  选择", choices=["1", "2", "3"], default="1")

        if choice == "3":
            await _finalize_task(client, task_id)
            return

        if choice == "2":
            with Status("[cyan]辩手自由交锋中（支持→反对→评审）...", spinner="dots"):
                resp = await client.debate_agent_exchange(task_id)
            if "error" in resp:
                error(str(resp["error"])[:300])
                continue
            if resp.get("system_message"):
                console.print(
                    Panel(
                        resp["system_message"].get("content", ""),
                        title="系统",
                        border_style="dim",
                    )
                )
            info(f"辩手自主交锋第 {resp.get('debate_exchange_round', '?')} 轮完成")
            for am in resp.get("agent_messages", []):
                _print_agent_message(am)
            continue

        content = Prompt.ask("\n  [你/决策方] 补充发言", default="").strip()
        if not content:
            info("未输入内容，请重新选择")
            continue
        with Status("[cyan]辩手交锋中（支持→反对→评审）...", spinner="dots"):
            resp = await client.post_message(
                task_id, content, reply_scope="debate_round"
            )
        if "error" in resp:
            error(str(resp["error"])[:300])
            continue
        info("本轮顺序：支持方 → 反对方反驳 → 评审归纳")
        for am in resp.get("agent_messages", []):
            _print_agent_message(am)


async def scene_poll_status(client: APIClient, task_id: int):
    """实时轮询任务状态"""

    print_section(f"任务 {task_id} 处理中")

    status_map = {
        "pending": ("⏳", "yellow"),
        "discussing": ("💬", "blue"),
        "finalizing": ("📝", "magenta"),
        "processing": ("🔄", "cyan"),
        "completed": ("✅", "green"),
        "failed": ("❌", "red"),
    }

    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_progress = progress.add_task("[cyan]等待 AI 分析...", total=None)

        for _ in range(60):  # 最多等 5 分钟
            await asyncio.sleep(5)
            s = await client.get_status(task_id)
            if not s:
                continue

            emoji, color = status_map.get(s["status"], ("❓", "white"))
            progress.update(
                task_progress,
                description=f"[{color}]{emoji} {s['status'].upper()}[/] "
                            f"— 任务 {task_id}",
            )

            if s["status"] in ("discussing",):
                progress.update(
                    task_progress,
                    description=f"[blue]💬 DISCUSSING — 请先在讨论室交流[/]",
                )
            elif s["status"] == "completed":
                progress.stop()
                success("分析完成!")
                await scene_view_result(client, task_id)
                return
            elif s["status"] == "failed":
                progress.stop()
                error(f"任务失败: {s.get('error_message', '未知错误')[:200]}")
                console.print(f"  [dim]可尝试 GET /api/tasks/{task_id}/result 查看详情[/]")
                return

        progress.stop()
        error("等待超时（5分钟），请稍后通过历史记录查看")


async def scene_view_result(client: APIClient, task_id: int):
    """查看完整结果"""
    print_section(f"任务 {task_id} 分析结果")

    with Status("[cyan]加载结果...", spinner="dots"):
        data = await client.get_result(task_id)

    if not data or "outputs" not in data:
        error("无法获取结果")
        return

    # === 1. 基本信息 ===
    mode_map = {v[0]: v[1] for v in DECISION_MODES.values()}
    info_table = Table(box=box.SIMPLE, show_header=False)
    info_table.add_column("f", style="dim", width=14)
    info_table.add_column("v")
    info_table.add_row("决策问题", data["question"])
    info_table.add_row("决策模式", mode_map.get(data["decision_mode"], data["decision_mode"]))
    info_table.add_row("任务状态", data["status"])
    info_table.add_row("创建时间", data["created_at"])
    console.print(Panel(info_table, title="基本信息", border_style="cyan"))

    # === 2. Agent 分析 (逐个渲染 Markdown) ===
    print_section("各专家分析意见")

    for output in data.get("outputs", []):
        agent_name = output.get("agent_name", "未知")
        style = STYLE_MAP.get(
            _guess_tone(agent_name, data.get("agents", [])), "bold white"
        )
        console.print(Panel(
            f"[{style}]{agent_name}[/]",
            border_style=style.split()[-1] if style else "white",
        ))
        if output.get("output_text"):
            md = _clean_markdown(output["output_text"])
            console.print(Markdown(md[:4000]))
        else:
            console.print("  [dim](该 Agent 未生成有效分析)[/]")
        console.print()

    # === 3. 相似度 ===
    if data.get("similarities"):
        print_section("语义相似度")
        sim_table = Table(box=box.ROUNDED, header_style="bold cyan")
        sim_table.add_column("Agent A", width=16)
        sim_table.add_column("Agent B", width=16)
        sim_table.add_column("相似度", width=10)
        sim_table.add_column("判定")
        for s in data["similarities"]:
            level = "⚠ 高度相似" if s["similarity"] >= 0.7 else "✓ 差异明显"
            color = "red" if s["similarity"] >= 0.7 else "green"
            sim_table.add_row(
                _find_agent_name(s["agent_id_1"], data),
                _find_agent_name(s["agent_id_2"], data),
                f"{s['similarity']:.1%}",
                f"[{color}]{level}[/]",
            )
        console.print(sim_table)

    # === 4. 加权排名 ===
    if data.get("weighted_ranking"):
        scored = [r for r in data["weighted_ranking"] if r.get("score_available")]
        if scored:
            print_section("加权综合得分排名")
            rank_table = Table(box=box.ROUNDED, header_style="bold cyan")
            rank_table.add_column("排名", width=6)
            rank_table.add_column("Agent", width=16)
            rank_table.add_column("综合得分", width=12)
            for item in scored:
                rank_table.add_row(
                    str(item["rank"]),
                    item["agent_name"],
                    f"{item['total_score']:.2f} / 10",
                )
            console.print(rank_table)

    # === 5. 冲突 ===
    if data.get("conflicts"):
        print_section("观点冲突检测")
        high_c = [c for c in data["conflicts"] if c["conflict_level"] == "high"]
        if high_c:
            console.print(f"  [red]⚠ 发现 {len(high_c)} 个高冲突维度:[/]")
            for c in high_c:
                dim_cn = DIMENSION_NAME_MAP.get(c["dimension"], c["dimension"])
                console.print(
                    f"    [red]●[/] {dim_cn}: "
                    f"最高 {c['max_score']:.0f} vs 最低 {c['min_score']:.0f} "
                    f"(分差 {c['max_score'] - c['min_score']:.0f})"
                )

    # === 6. 综合建议 ===
    if data.get("final_summary"):
        print_section("综合建议")
        console.print(Markdown(data["final_summary"][:5000]))

    # === 7. 后续操作 ===
    console.print()
    console.print(Rule(style="dim"))
    console.print("  [1] 提交反馈采纳")
    console.print("  [2] 导出 Markdown 报告")
    console.print("  [3] 返回主菜单")
    action = Prompt.ask("  选择", choices=["1", "2", "3"], default="3")

    if action == "1":
        await scene_submit_feedback(client, task_id, data)
    elif action == "2":
        await scene_export(client, task_id)


async def scene_submit_feedback(client: APIClient, task_id: int, data: dict):
    """提交采纳反馈"""
    print_section("提交反馈")

    console.print("  请选择你要采纳的方案:")
    console.print("  [0] 采纳系统综合建议")
    for out in data.get("outputs", []):
        console.print(
            f"  [{out['task_agent_id']}] 采纳 "
            f"[bold]{out.get('agent_name', '未知')}[/]"
        )
    console.print("  [99] 暂不采纳")

    agent_ids = [o["task_agent_id"] for o in data.get("outputs", [])]
    choices = ["0"] + [str(a) for a in agent_ids] + ["99"]
    ch = Prompt.ask("  选择", choices=choices)

    if ch == "99":
        chosen_type, chosen_agent_id = "none", None
        info("已记录: 暂不采纳")
    elif ch == "0":
        chosen_type, chosen_agent_id = "summary", None
        info("已选择: 综合建议")
    else:
        chosen_type, chosen_agent_id = "agent", int(ch)
        name = _find_agent_name(int(ch), data)
        info(f"已选择: {name}")

    comment = ask("  备注（可选）", default="")

    with Status("[cyan]提交中...", spinner="dots"):
        r = await client.submit_feedback(task_id, chosen_type, chosen_agent_id, comment)
    if "error" in r:
        error(f"提交失败: {r['error'][:200]}")
    else:
        success("反馈已提交!")


async def scene_export(client: APIClient, task_id: int):
    """导出 Markdown 报告"""
    print_section("导出报告")

    with Status("[cyan]正在生成报告...", spinner="dots"):
        md = await client.export_report(task_id)

    if not md:
        error("导出失败")
        return

    # 保存到本地
    out_dir = Path.cwd() / "reports"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"decision_report_{task_id}.md"
    out_file.write_text(md, encoding="utf-8")

    success(f"报告已保存: [bold]{out_file}[/] ({len(md):,} 字符)")
    info(f"可用编辑器直接打开: {out_file}")


async def scene_history(client: APIClient):
    """历史记录"""
    print_section("历史决策记录")

    with Status("[cyan]加载中...", spinner="dots"):
        tasks = await client.get_history()

    if not tasks:
        console.print("  [dim]暂无历史记录[/]")
        console.print("  先创建一个决策任务吧 → 返回主菜单选择 [1]")
        return

    table = Table(box=box.ROUNDED, header_style="bold cyan")
    table.add_column("ID", width=5, style="dim")
    table.add_column("决策问题", width=40)
    table.add_column("模式", width=12)
    table.add_column("状态", width=10)
    table.add_column("时间", width=20, style="dim")

    for t in tasks:
        mode_map = {v[0]: v[1] for v in DECISION_MODES.values()}
        status_icon = {"completed": "✅", "failed": "❌", "processing": "🔄", "pending": "⏳"}
        table.add_row(
            str(t["id"]),
            t["question"][:38] + ("..." if len(t["question"]) > 38 else ""),
            mode_map.get(t["decision_mode"], t["decision_mode"]),
            f"{status_icon.get(t['status'], '?')} {t['status']}",
            t["created_at"][:19],
        )
    console.print(table)

    if confirm("是否查看某个任务的详情?"):
        tid = IntPrompt.ask("  任务 ID")
        # 先查状态
        s = await client.get_status(tid)
        if s.get("status") == "completed":
            await scene_view_result(client, tid)
        elif s.get("status") == "failed":
            error(f"任务失败: {s.get('error_message', '?')[:200]}")
        else:
            info(f"任务状态: {s.get('status')}，等待完成中...")
            await scene_poll_status(client, tid)


async def scene_templates(client: APIClient):
    """浏览模板"""
    print_section("预设 Agent 模板")
    with Status("[cyan]加载...", spinner="dots"):
        templates = await client.get_templates()

    for t in templates:
        element, element_color = _element_info(t["name"])
        style = STYLE_MAP.get(t.get("tone", ""), "white")
        console.print(Panel(
            Group(
                Text.assemble(
                    (t["name"], f"bold {element_color}"),
                    ("  —  ", "dim"),
                    (t.get("role_description", "-"), style),
                ),
                Text(f"关注: {t.get('focus_area', '-')}", style="dim"),
                Text(f"风格: {t.get('tone', '-')}  [{element}命]", style=style),
            ),
            border_style=element_color,
        ))


# ============================================================================
# 辅助函数
# ============================================================================


def _find_agent_name(agent_id: int, data: dict) -> str:
    """从 result 数据中找到 agent 名称"""
    for a in data.get("agents", []):
        if a["id"] == agent_id:
            return a["agent_name"]
    return f"Agent-{agent_id}"


def _guess_tone(agent_name: str, agents: list) -> str:
    """根据 agent_name 猜测 tone"""
    for a in agents:
        if a.get("agent_name") == agent_name:
            return a.get("tone", "")
    return ""


def _element_tag(name: str) -> str:
    """从名称中提取五行标签"""
    for el in ["金", "木", "水", "火", "土"]:
        if el in name:
            return f"{el}行"
    return "—"


def _element_info(name: str) -> tuple[str, str]:
    """返回 (元素名, 颜色)"""
    color_map = {
        "金": "yellow", "木": "green", "水": "blue",
        "火": "red", "土": "magenta",
    }
    for el, c in color_map.items():
        if el in name:
            return (el, c)
    return ("?", "white")


def _clean_markdown(text: str) -> str:
    """清理 Agent 输出的 Markdown，适配终端渲染"""
    # 去掉可能的开头空行
    text = text.strip()
    # 确保标题后有空格
    import re
    text = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
    return text


# ============================================================================
# 主菜单
# ============================================================================


async def main_menu(client: APIClient):
    """主交互循环"""
    while True:
        console.clear()
        print_banner()

        # 用户状态
        console.print(
            f"  [dim]当前用户:[/] [bold green]{client.username}[/]  "
            f"[dim]角色:[/] [bold]{client.role}[/]  "
            f"[dim]API:[/] {API_BASE}"
        )
        console.print()

        # 菜单项
        menu = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        menu.add_column("key", style="bold cyan", width=4)
        menu.add_column("name", width=20)
        menu.add_column("desc", style="dim")

        menu.add_row(" 1", "创建决策任务", "输入问题 → 选 Agent → 实时查看 AI 分析")
        menu.add_row(" 2", "历史记录", "浏览历史任务 & 查看详情 & 导出报告")
        menu.add_row(" 3", "浏览模板", "查看系统预设的五行人格 Agent 模板")
        menu.add_row("", "", "")
        menu.add_row(" 0", "退出", "")

        console.print(Panel(menu, border_style="cyan"))
        console.print()

        choice = Prompt.ask("  选择操作", choices=["0", "1", "2", "3"], default="1")

        if choice == "1":
            await scene_create_task(client)
        elif choice == "2":
            await scene_history(client)
        elif choice == "3":
            await scene_templates(client)
        elif choice == "0":
            console.print(f"\n  [dim]再见, {client.username}![/]\n")
            break

        # 操作后暂停
        if choice in ("1", "2", "3"):
            console.print()
            Prompt.ask("  [dim]按 Enter 返回主菜单[/]", default="", show_default=False)


# ============================================================================
# 入口
# ============================================================================


async def main():
    """程序入口"""
    try:
        # 快速检查服务是否可达
        async with httpx.AsyncClient(timeout=3, trust_env=False) as c:
            await c.get(f"{API_BASE}/")
    except Exception:
        console.print()
        error("无法连接到后端服务!")
        console.print(f"  [dim]请先启动后端: cd backend && python main.py[/]")
        console.print(f"  [dim]确认 {API_BASE} 可访问后重试[/]")
        console.print()
        return

    client = APIClient()
    console.clear()
    print_banner()

    # 认证
    if not await scene_auth(client):
        console.print("\n  [dim]已退出[/]\n")
        return

    # 获取用户信息
    async with httpx.AsyncClient(timeout=10, trust_env=False) as c:
        r = await c.get(f"{API_BASE}/api/auth/me", headers=client.headers)
        if r.status_code == 200:
            u = r.json()
            client.role = u.get("role", "user")
            client.username = u["username"]

    # 进入主菜单
    await main_menu(client)


if __name__ == "__main__":
    asyncio.run(main())
