"""人设与阶段 Prompt 片段（交流期 / 收束期）。"""

from __future__ import annotations

STANCE_LABELS = {
    "pro": "支持方辩手",
    "con": "反对方辩手",
    "judge": "评审方",
    "neutral": "专家",
}

DISCUSS_MODE_HINT = {
    "multi_angle": "当前为【多角度分析】讨论阶段：从你的专业角度回应用户，可追问、补充要点。",
    "debate": "当前为【正反辩论】讨论阶段：根据你的立场回应用户（决策方），可反驳、追问。",
    "expert_consult": "当前为【专家会诊】讨论阶段：给出专业诊断式短回复，可追问关键事实。",
    "risk_review": "当前为【风险评审】讨论阶段：聚焦风险、兜底与合规，短回复。",
}

FINALIZE_MODE_HINT = {
    "multi_angle": "请基于讨论纪要，输出完整的多角度决策分析报告。",
    "debate": "请基于讨论纪要与你的辩手立场，输出正式的辩论总结报告。",
    "expert_consult": "请基于讨论纪要，输出专家会诊式正式报告。",
    "risk_review": "请基于讨论纪要，输出风险评审正式报告（含风险清单与是否建议推进）。",
}


def build_persona_block(
    *,
    agent_name: str,
    role_description: str | None,
    focus_area: str | None,
    tone: str | None,
    stance: str | None,
    extra_notes: str | None,
) -> str:
    label = STANCE_LABELS.get(stance or "neutral", "专家")
    parts = [f"你是「{agent_name}」，{label}。"]
    if role_description:
        parts.append(f"【专业背景】{role_description}")
    if focus_area:
        parts.append(f"【关注重点】{focus_area}")
    if tone:
        parts.append(f"【表达风格】{tone}")
    notes = (extra_notes or "").strip()
    parts.append(f"【用户为本案补充】{notes if notes else '无'}")
    return "\n".join(parts)


def build_discuss_system_prompt(
    *,
    agent_name: str,
    role_description: str | None,
    focus_area: str | None,
    tone: str | None,
    stance: str | None,
    extra_notes: str | None,
    decision_mode: str,
    question: str,
    context_notes: str | None = None,
) -> str:
    persona = build_persona_block(
        agent_name=agent_name,
        role_description=role_description,
        focus_area=focus_area,
        tone=tone,
        stance=stance,
        extra_notes=extra_notes,
    )
    mode_hint = DISCUSS_MODE_HINT.get(decision_mode, DISCUSS_MODE_HINT["multi_angle"])
    blocks = [
        persona,
        mode_hint,
        f"【决策问题】{question}",
    ]
    ctx = (context_notes or "").strip()
    if ctx:
        blocks.append(f"【本案背景说明】{ctx}")
    blocks.append(
        "【交流期规则】用 3～8 句话回复；不要输出六维评分 JSON；不要使用完整八段报告标题。"
    )
    return "\n\n".join(blocks)


def build_discuss_user_message(user_content: str, room_transcript: str) -> str:
    """非辩论模式：将前轮讨论拼入 user 提示。"""
    parts: list[str] = []
    if room_transcript.strip():
        parts.append(f"【此前讨论记录】\n{room_transcript}")
    parts.append(f"【用户（决策方）本轮说】\n{user_content}")
    parts.append(
        "【你的任务】结合你的人设与上文讨论（若有），回应用户；"
        "可引用或回应其他专家已说过的观点；可追问。"
        "用 3～8 句话，不要 JSON 评分，不要八段报告标题。"
    )
    return "\n\n".join(parts)


def build_finalize_system_prompt(
    *,
    agent_name: str,
    role_description: str | None,
    focus_area: str | None,
    tone: str | None,
    stance: str | None,
    extra_notes: str | None,
    decision_mode: str,
    question: str,
    output_format_instruction: str,
) -> str:
    persona = build_persona_block(
        agent_name=agent_name,
        role_description=role_description,
        focus_area=focus_area,
        tone=tone,
        stance=stance,
        extra_notes=extra_notes,
    )
    mode_hint = FINALIZE_MODE_HINT.get(decision_mode, FINALIZE_MODE_HINT["multi_angle"])
    return "\n\n".join(
        [
            persona,
            mode_hint,
            f"【决策问题】{question}",
            output_format_instruction,
        ]
    )
