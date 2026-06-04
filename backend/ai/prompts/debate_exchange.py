"""辩论模式交流期 Prompt 与展示文案。"""

from __future__ import annotations

from ai.prompts.persona import STANCE_LABELS, build_discuss_system_prompt

STANCE_DISPLAY_ZH = {
    "pro": "支持方",
    "con": "反对方",
    "judge": "评审方",
    "neutral": "专家",
}


def agent_display_name(agent_name: str, stance: str | None) -> str:
    label = STANCE_DISPLAY_ZH.get(stance or "neutral", "专家")
    return f"{agent_name}【{label}】"


def stance_label(stance: str | None) -> str:
    return STANCE_DISPLAY_ZH.get(stance or "neutral", "专家")


def build_debate_welcome(question: str, agents: list) -> str:
    lines = [
        "欢迎进入【正反辩论】讨论室。",
        f"决策问题：{question}",
        "",
        "── 辩手席位 ──",
    ]
    for a in agents:
        lines.append(
            f"· {agent_display_name(a.agent_name, a.stance)}"
            f"：{a.role_description or '专家'}"
        )
    lines.extend(
        [
            "",
            "你是决策方（用户）。创建任务时已由你指定正方/反方/评审。",
            "每次你发言后：支持方 → 反对方反驳 → 评审归纳。",
            "你也可以选择「不发言」，让辩手继续交锋一轮。",
            "结束时请选择「生成正式分析」。",
        ]
    )
    return "\n".join(lines)


def build_debate_system_prompt(
    agent,
    decision_mode: str,
    question: str,
    context_notes: str | None = None,
) -> str:
    base = build_discuss_system_prompt(
        agent_name=agent.agent_name,
        role_description=agent.role_description,
        focus_area=agent.focus_area,
        tone=agent.tone,
        stance=agent.stance,
        extra_notes=agent.extra_notes,
        decision_mode=decision_mode,
        question=question,
        context_notes=context_notes,
    )
    extra = {
        "pro": "你必须明确站在【支持该方案】立场，与反对方形成对立。",
        "con": "你必须明确站在【反对该方案】立场，要质疑、反驳支持方观点。",
        "judge": "你是评审，不站队；要归纳双方分歧，可向用户追问，不要替用户做决定。",
    }.get(agent.stance or "", "")
    debate_rules = (
        "【辩论规则】你在辩论厅中与对方辩手交锋，不是单独做客服问答。"
        "必须引用或回应对方辩手的最新观点（若有）。"
        "用 3～8 句话，不要 JSON 评分，不要八段报告标题。"
    )
    return "\n\n".join([base, extra, debate_rules])


def build_pro_user_message(user_content: str, room_transcript: str) -> str:
    parts = []
    if room_transcript.strip():
        parts.append(f"【此前辩论记录】\n{room_transcript}")
    parts.append(f"【用户（决策方）说】\n{user_content}")
    parts.append(
        "【你的任务】作为支持方，回应用户并简述你支持该方案的核心理由。"
        "若有反对方此前发言，可预先回应其质疑。"
    )
    return "\n\n".join(parts)


def build_con_user_message(
    user_content: str, room_transcript: str, pro_last: str | None
) -> str:
    parts = []
    if room_transcript.strip():
        parts.append(f"【此前辩论记录】\n{room_transcript}")
    parts.append(f"【用户（决策方）说】\n{user_content}")
    if pro_last:
        parts.append(f"【支持方刚才说】\n{pro_last}")
    parts.append(
        "【你的任务】作为反对方，先回应用户，再针对支持方刚才的观点进行反驳"
        "（指出风险、漏洞或不可行之处）。不要与支持方立场一致。"
    )
    return "\n\n".join(parts)


def build_agent_only_pro_message(room_transcript: str, con_last: str | None) -> str:
    parts = [f"【此前辩论记录】\n{room_transcript}" if room_transcript.strip() else ""]
    if con_last:
        parts.append(f"【反对方最新观点】\n{con_last}")
    parts.append(
        "【情况】用户（决策方）本轮暂不补充发言。"
        "【你的任务】作为支持方，请针对反对方最新观点继续辩护，强化支持理由。"
    )
    return "\n\n".join(p for p in parts if p)


def build_agent_only_con_message(room_transcript: str, pro_last: str | None) -> str:
    parts = [f"【此前辩论记录】\n{room_transcript}" if room_transcript.strip() else ""]
    if pro_last:
        parts.append(f"【支持方最新观点】\n{pro_last}")
    parts.append(
        "【情况】用户（决策方）本轮暂不补充发言。"
        "【你的任务】作为反对方，请反驳支持方最新观点，指出风险与漏洞。"
    )
    return "\n\n".join(p for p in parts if p)


def build_agent_only_judge_message(
    room_transcript: str, pro_last: str | None, con_last: str | None
) -> str:
    parts = [f"【此前辩论记录】\n{room_transcript}" if room_transcript.strip() else ""]
    if pro_last:
        parts.append(f"【支持方本轮要点】\n{pro_last[:600]}")
    if con_last:
        parts.append(f"【反对方本轮要点】\n{con_last[:600]}")
    parts.append(
        "【情况】用户本轮未发言，辩手进行自由交锋。"
        "【你的任务】评审方请更新分歧归纳，并判断是否需用户澄清。"
    )
    return "\n\n".join(p for p in parts if p)


def build_judge_user_message(
    user_content: str,
    room_transcript: str,
    pro_last: str | None,
    con_last: str | None,
) -> str:
    parts = []
    if room_transcript.strip():
        parts.append(f"【此前辩论记录】\n{room_transcript}")
    parts.append(f"【用户（决策方）说】\n{user_content}")
    if pro_last:
        parts.append(f"【支持方本轮要点】\n{pro_last[:600]}")
    if con_last:
        parts.append(f"【反对方本轮要点】\n{con_last[:600]}")
    parts.append(
        "【你的任务】作为评审，归纳双方本轮分歧（2～3 条），"
        "可向用户提出一个关键追问。不要站队，不要输出评分 JSON。"
    )
    return "\n\n".join(parts)
