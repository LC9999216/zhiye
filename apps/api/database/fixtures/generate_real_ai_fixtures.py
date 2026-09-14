"""Generate human-annotated AI fixtures from REAL Stage 0 responses.

Stage 4 close-out: the execution plan requires spot-checking real
answers (not just synthetic ones) to verify valid-claim coverage >= 60%.

Each fixture below is hand-annotated from the *actual* ``ContentText``
returned by the Zhihu search API (stored locally in
``.local/zhihu-fixtures/``).  ``evidence_text`` is always a verbatim
substring of the corresponding ``ContentText`` so the pipeline's
evidence-substring check passes.

Output: ``database/fixtures/ai_analysis/real-*.json`` (committed).
"""

from __future__ import annotations

import json
from pathlib import Path

# repo root: this file lives at apps/api/database/fixtures/
_REPO_ROOT = Path(__file__).resolve().parents[4]
_OUT = _REPO_ROOT / "database" / "fixtures" / "ai_analysis"

# content_id -> (summary, stance, [(claim_text, evidence_substring, concepts)])
# Evidence substrings are copied verbatim from the real ContentText.
ANNOTATIONS: dict[str, tuple[str, str, list[tuple[str, str, list[str]]]]] = {
    "-7195337369420344850": (
        "十年前进入互联网行业工作比读研更快成长",
        "support",
        [
            (
                "工作三年成长可达到研究生水平",
                "干得好工作三年之后可以面试研究生了",
                ["工作"],
            ),
            (
                "2016到2019年互联网飞速发展，大家普遍选择就业",
                "研究生保研基本都是学习成绩好的，代码写得好的朋友都拿大厂中厂小厂Offer满天跑",
                ["互联网", "就业"],
            ),
            (
                "读研毕业进大厂寥寥无几",
                "18-19年毕业的同学，进大厂寥寥无几",
                ["考研"],
            ),
        ],
    ),
    "-8695407326414892195": (
        "计算机专业就业需关注去初级化和硬科技趋势",
        "conditional",
        [
            (
                "就业市场去初级化，三年经验岗位占比超七成",
                "2026年春招要求3年以上工作经验的岗位占比超过70%",
                ["就业"],
            ),
            (
                "硬科技崛起，信息安全月薪7548元位列第四",
                "信息安全仍以7548元位列第四",
                ["信息安全"],
            ),
            (
                "企业看重算法与数据结构、真实项目经验和AI驾驭能力",
                "企业看计算机学生盯的是以下几个东西",
                ["计算机"],
            ),
        ],
    ),
    "1935523816803237707": (
        "两位计算机学生案例说明大厂就业与考研的现实差异",
        "neutral",
        [
            (
                "竞赛获奖学生直接就业收入可观",
                "大学参加各种竞赛，并且获得不少奖励，大学毕业时没有读研，直接去了大厂工作",
                ["竞赛"],
            ),
            (
                "读研学生发表论文获得国家奖学金",
                "在学期间获得了研究生国家奖学金",
                ["考研"],
            ),
            (
                "研究生毕业仍难进大厂因为招聘需求减弱和扩招",
                "那个大厂的员工需求减弱了，招聘的人数减少",
                ["大厂"],
            ),
        ],
    ),
    "7990294196239766632": (
        "计算机专业学生普遍面临考研与就业的纠结选择",
        "neutral",
        [
            (
                "几乎所有计算机专业学生都会遇到这个选择",
                "这个问题几乎每个计算机专业的学生都会遇到",
                ["计算机"],
            ),
            (
                "这是大家最纠结的选择之一",
                "也是大家最纠结的选择之一",
                ["选择"],
            ),
        ],
    ),
    "2739444777738949703": (
        "作者将就业困难与考研歧视都归因于学校背景",
        "support",
        [
            (
                "找到工作被裁员因为学校不好",
                "找到工作了被裁员，是因为学校不好",
                ["就业"],
            ),
            (
                "考研被歧视也因为学校不好",
                "考研被歧视，也是因为学校不好",
                ["考研"],
            ),
        ],
    ),
    "1958022176059271721": (
        "建议先就业，工作可以找到但期望不要太高",
        "support",
        [
            (
                "建议先就业",
                "建议还是先就业",
                ["就业"],
            ),
            (
                "工作肯定可以找到但不要期望太高",
                "工作肯定可以找到，但不要期望太高",
                ["工作"],
            ),
        ],
    ),
    "-4653801447369001239": (
        "考研辅导视角认为问题不只是简单选择",
        "conditional",
        [
            (
                "你的问题本身不是简单的选择问题",
                "你的问题本身不是简单的选择问题",
                ["选择"],
            ),
            (
                "所谓大环境差也要看具体情况",
                "所谓大环境差也是要看具体的",
                ["环境"],
            ),
        ],
    ),
    "6459050543321812416": (
        "DeepSeek官方回答展示了推理过程",
        "neutral",
        [
            (
                "首token响应时间为9.89秒",
                "首 token 响应时间： 9.89 秒",
                ["DeepSeek"],
            ),
        ],
    ),
}


def main() -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for cid, (summary, stance, claims) in ANNOTATIONS.items():
        payload = {
            "summary": summary,
            "stance": stance,
            "claims": [
                {
                    "text": text,
                    "evidence_text": evidence,
                    "confidence": 0.9,
                    "concepts": concepts,
                }
                for text, evidence, concepts in claims
            ],
        }
        out = _OUT / f"{cid}.json"
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written += 1
        print(f"wrote {out.name} ({len(claims)} claims)")
    print(f"total written: {written}")


if __name__ == "__main__":
    main()
