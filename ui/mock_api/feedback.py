from typing import List, Dict, Any

_feedback_db: List[Dict] = []

def submit_feedback(data: Dict[str, Any]) -> Dict[str, Any]:
    _feedback_db.append(data)
    # 仅返回文档约定的字段
    return {
        "task_id": data["task_id"],
        "chosen_type": data["chosen_type"],
        "chosen_agent_id": data.get("chosen_agent_id"),
        "comment": data.get("comment", "")
    }

def get_feedback_stats() -> Dict[str, Any]:
    agent_cnt = sum(1 for fb in _feedback_db if fb["chosen_type"] == "agent")
    summary_cnt = sum(1 for fb in _feedback_db if fb["chosen_type"] == "summary")
    none_cnt = sum(1 for fb in _feedback_db if fb["chosen_type"] == "none")
    return {
        "total_feedback": len(_feedback_db),
        "agent_count": agent_cnt,
        "summary_count": summary_cnt,
        "none_count": none_cnt
    }