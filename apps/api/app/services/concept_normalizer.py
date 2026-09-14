"""Deterministic concept normalisation (Stage 5).

Maps a raw concept name (as produced by the LLM inside a claim) to a
stable, query-scoped normalized form used for the ``concepts`` table's
``(query_id, normalized_name)`` unique key.

Steps (in order, deterministic + idempotent):
1. NFKC — converts full-width/half-width and compatibility characters.
2. ``casefold()`` — English case folding (stricter than lower()).
3. Collapse all whitespace runs (incl. full-width space) to one space.
4. Trim leading/trailing whitespace.

Common alias handling happens at merge time (concept_merger), not here:
this module only guarantees the deterministic key.
"""

from __future__ import annotations

import re
import unicodedata

# Version of the normalisation contract (persisted with merged concepts).
CONCEPT_METHOD_VERSION = "concept-normalize-v1"

_WS_RUN = re.compile(r"\s+")

# Common alias map for deterministic concept merging (Stage 5).
# Cross-language abbreviations and synonyms that character-overlap or
# embedding similarity cannot reliably discover.  Values are normalised
# forms; every key maps to its canonical (first) value.
CONCEPT_ALIASES: dict[str, list[str]] = {
    "ai": ["人工智能", "artificial intelligence"],
    "人工智能": ["ai", "artificial intelligence"],
    "llm": ["大语言模型", "大模型", "large language model"],
    "大语言模型": ["llm", "大模型", "large language model"],
    "大模型": ["llm", "大语言模型", "large language model"],
    "ml": ["机器学习", "machine learning"],
    "机器学习": ["ml", "machine learning"],
    "dl": ["深度学习", "deep learning"],
    "深度学习": ["dl", "deep learning"],
    "os": ["操作系统"],
    "操作系统": ["os"],
    "cs": ["计算机科学", "计算机专业"],
    "计算机科学": ["cs", "计算机专业"],
    "程序员": ["开发者", "开发人员"],
    "开发者": ["程序员", "开发人员"],
    "就业": ["找工作", "工作机会"],
    "找工作": ["就业", "工作机会"],
    "考研": ["研究生考试", "读研"],
    "研究生考试": ["考研", "读研"],
    "面试": ["面试官", "求职面试"],
    "面试官": ["面试", "求职面试"],
    "实习": ["实习经历"],
    "实习经历": ["实习"],
    "算法": ["算法题"],
    "算法题": ["算法"],
    "互联网大厂": ["科技公司", "大厂"],
    "科技公司": ["互联网大厂", "大厂"],
    "编程语言": ["c语言", "programming language"],
    "c语言": ["编程语言", "programming language"],
    "数据结构": ["数据组织"],
    "数据组织": ["数据结构"],
}


def alias_group(normalized: str) -> str | None:
    """Return the canonical alias-group key for *normalized*, if any.

    Every entry in ``CONCEPT_ALIASES`` maps to a group; the group key is
    the first (canonical) name of the first list that contains it.
    """
    for canonical, aliases in CONCEPT_ALIASES.items():
        if normalized == canonical or normalized in aliases:
            return canonical
    return None


def normalize_concept_name(raw: str) -> str:
    """Return the deterministic normalised form of *raw*.

    Idempotent: ``normalize(normalize(x)) == normalize(x)``.
    """
    text = raw or ""
    text = unicodedata.normalize("NFKC", text)  # full-width → half-width
    text = _WS_RUN.sub(" ", text).strip()  # collapse + trim whitespace
    text = text.casefold()  # English case folding
    return text.strip()


__all__ = ["CONCEPT_METHOD_VERSION", "normalize_concept_name"]
