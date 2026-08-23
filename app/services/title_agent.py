from __future__ import annotations

from typing import Any

from app.services.base_agent import BaseAgent
from app.utils.json_parser import json_dumps
from app.utils.title_tools import title_is_plot_summary


_SCORE_LIMITS = {
    "text_fidelity": 25,
    "core_change": 25,
    "character_action": 15,
    "outline_alignment": 15,
    "naturalness": 15,
    "novelty": 5,
}


class TitleAgent(BaseAgent):
    """Independent title editor used after a chapter's prose is settled."""

    agent_name = "title"
    prompt_file = "title_prompt.md"

    def judge(self, brief: dict[str, Any], candidates: list[str]) -> dict[str, Any]:
        clean_candidates = _clean_candidates(candidates)
        prompt = (
            "任务：judge\n"
            "请独立裁决候选标题。不要改写正文，也不要新拟标题。\n\n"
            f"标题资料：\n{json_dumps(brief)}\n\n"
            f"候选标题：\n{json_dumps(clean_candidates)}"
        )
        return self.complete_json(
            prompt,
            validator=lambda value: _validate_judgement(value, clean_candidates),
            default={},
            normalizer=_normalize_judgement,
            mock_hint={"task": "title_judge", "candidates": clean_candidates},
            repair_attempts=1,
        )

    def regenerate(self, brief: dict[str, Any], feedback: list[str]) -> dict[str, Any]:
        prompt = (
            "任务：regenerate\n"
            "现有候选未通过标题研判。请仅根据资料重新拟题，不要解释正文。\n\n"
            f"标题资料：\n{json_dumps(brief)}\n\n"
            f"淘汰原因：\n{json_dumps(feedback[:8])}"
        )
        return self.complete_json(
            prompt,
            validator=_validate_regeneration,
            default={},
            normalizer=_normalize_regeneration,
            mock_hint={"task": "title_regenerate", "feedback": feedback[:8]},
            repair_attempts=1,
        )

    def propose(self, brief: dict[str, Any]) -> dict[str, Any]:
        return self.regenerate(
            brief,
            ["首次拟题：标题必须概括正文已经发生的核心行动、变化、回报或代价。"],
        )


def _clean_title(value: Any) -> str:
    return str(value or "").strip().strip('"“”‘’')


def _clean_candidates(values: Any) -> list[str]:
    result: list[str] = []
    for item in values if isinstance(values, list) else []:
        title = _clean_title(item.get("title") if isinstance(item, dict) else item)
        if title and title not in result:
            result.append(title)
    return result[:8]


def _score(value: Any, maximum: int) -> int:
    try:
        return max(0, min(maximum, int(value)))
    except (TypeError, ValueError):
        return 0


def _normalize_judgement(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    fact_card = data.get("fact_card") if isinstance(data.get("fact_card"), dict) else {}
    normalized = {
        "fact_card": {
            "who_did_what": str(fact_card.get("who_did_what") or "").strip(),
            "main_action": str(fact_card.get("main_action") or "").strip(),
            "key_choice": str(fact_card.get("key_choice") or "").strip(),
            "core_change": str(fact_card.get("core_change") or "").strip(),
            "reader_payoff": str(fact_card.get("reader_payoff") or "").strip(),
            "cost_or_risk": str(fact_card.get("cost_or_risk") or "").strip(),
            "evidence": [str(item).strip() for item in fact_card.get("evidence", []) if str(item).strip()][:4],
        },
        "assessments": [],
        "recommended_title": _clean_title(data.get("recommended_title")),
        "reason": str(data.get("reason") or "").strip(),
    }
    for item in data.get("assessments", []) if isinstance(data.get("assessments"), list) else []:
        if not isinstance(item, dict):
            continue
        scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
        normalized_scores = {key: _score(scores.get(key), maximum) for key, maximum in _SCORE_LIMITS.items()}
        normalized_scores["total"] = sum(normalized_scores.values())
        inferred_summary = title_is_plot_summary(item.get("title"))
        normalized["assessments"].append(
            {
                "title": _clean_title(item.get("title")),
                "evidence": str(item.get("evidence") or "").strip(),
                "scores": normalized_scores,
                "is_plot_summary": item.get("is_plot_summary") if isinstance(item.get("is_plot_summary"), bool) else inferred_summary,
                "is_novel_title": item.get("is_novel_title") if isinstance(item.get("is_novel_title"), bool) else not inferred_summary,
                "style_type": str(item.get("style_type") or "other").strip() or "other",
                "hard_reject": bool(item.get("hard_reject")),
                "issues": [str(issue).strip() for issue in item.get("issues", []) if str(issue).strip()][:5],
                "accepted": bool(item.get("accepted")),
            }
        )
    return normalized


def _validate_judgement(value: Any, candidates: list[str]) -> list[str]:
    if not isinstance(value, dict):
        return ["标题研判结果必须是对象"]
    fact_card = value.get("fact_card")
    if not isinstance(fact_card, dict) or not str(fact_card.get("who_did_what") or "").strip() or not str(fact_card.get("core_change") or "").strip():
        return ["fact_card 必须说明核心行动和变化"]
    assessments = value.get("assessments")
    if not isinstance(assessments, list) or len(assessments) != len(candidates):
        return ["assessments 必须逐项覆盖全部候选标题"]
    seen: set[str] = set()
    for item in assessments:
        if not isinstance(item, dict):
            return ["assessment 必须是对象"]
        title = _clean_title(item.get("title"))
        if title not in candidates or title in seen:
            return ["assessment.title 必须与候选标题一一对应"]
        seen.add(title)
        if not str(item.get("evidence") or "").strip():
            return [f"标题《{title}》缺少正文证据"]
        if not isinstance(item.get("is_plot_summary"), bool) or not isinstance(item.get("is_novel_title"), bool):
            return [f"标题《{title}》必须明确判断摘要腔和小说标题感"]
        if not str(item.get("style_type") or "").strip():
            return [f"标题《{title}》缺少 style_type"]
        scores = item.get("scores")
        if not isinstance(scores, dict):
            return [f"标题《{title}》缺少 scores"]
        total = 0
        for key, maximum in _SCORE_LIMITS.items():
            score = scores.get(key)
            if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= maximum:
                return [f"标题《{title}》的 {key} 分数无效"]
            total += score
        if scores.get("total") != total:
            return [f"标题《{title}》的 total 必须等于各项分数之和"]
    accepted = [item for item in assessments if item.get("accepted")]
    recommended = _clean_title(value.get("recommended_title"))
    if accepted and recommended not in {_clean_title(item.get("title")) for item in accepted}:
        return ["recommended_title 必须是通过的候选标题"]
    if not accepted and recommended:
        return ["没有通过的标题时 recommended_title 必须为空"]
    return []


def _normalize_regeneration(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    candidates = []
    for item in data.get("candidates", []) if isinstance(data.get("candidates"), list) else []:
        item = item if isinstance(item, dict) else {"title": item}
        title = _clean_title(item.get("title"))
        anchor = str(item.get("anchor") or "").strip()
        if title and title not in {candidate["title"] for candidate in candidates}:
            candidates.append({"title": title, "anchor": anchor})
    return {"candidates": candidates[:6], "reason": str(data.get("reason") or "").strip()}


def _validate_regeneration(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["重新拟题结果必须是对象"]
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or not 4 <= len(candidates) <= 6:
        return ["重新拟题必须提供 4 到 6 个候选"]
    for item in candidates:
        if not isinstance(item, dict) or not _clean_title(item.get("title")) or not str(item.get("anchor") or "").strip():
            return ["每个候选必须包含 title 和 anchor"]
    return []
