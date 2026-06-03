"""AI 模块共享常量（维度、决策模式等）。"""

ALL_DIMENSIONS = ["benefit", "cost", "risk", "tech", "exec", "long_term"]

DIMENSION_NAME_MAP = {
    "benefit": "收益潜力",
    "cost": "成本可控性",
    "risk": "风险可控性",
    "tech": "技术可行性",
    "exec": "执行可行性",
    "long_term": "长期价值",
}

DECISION_MODE_LABELS = {
    "multi_angle": "多角度分析",
    "debate": "正反辩论",
    "expert_consult": "专家会诊",
    "risk_review": "风险评审",
}
