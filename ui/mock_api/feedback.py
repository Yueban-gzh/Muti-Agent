from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

_feedback_db: List[Dict] = []
_feedback_id = 1

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def submit_feedback(task_id: int, user_id: int, chosen_type: str, chosen_agent_id: int = None, comment: str = "") -> Optional[Dict[str, Any]]:
    global _feedback_id
    fb = {
        "id": _feedback_id,
        "task_id": task_id,
        "user_id": user_id,
        "chosen_type": chosen_type,
        "chosen_agent_id": chosen_agent_id,
        "comment": comment,
        "created_at": _utcnow_iso()
    }
    _feedback_db.append(fb)
    _feedback_id += 1
    return fb

def get_feedback_stats() -> Dict[str, Any]:
    total = len(_feedback_db)
    agent_count = sum(1 for f in _feedback_db if f["chosen_type"] == "agent")
    summary_count = sum(1 for f in _feedback_db if f["chosen_type"] == "summary")
    none_count = sum(1 for f in _feedback_db if f["chosen_type"] == "none")
    return {
        "total_feedback_count": total,
        "agent_adoption_count": agent_count,
        "summary_adoption_count": summary_count,
        "none_count": none_count
    }