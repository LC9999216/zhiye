"""Durable, conservative project-side budget reservations."""

from __future__ import annotations

import json
from decimal import Decimal
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BudgetExhaustedError
from app.models.budget_ledger import BudgetLedger
from app.models.job import Job
from app.models.query import Query
from app.models.answer import Answer


def _decode_usage_document(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _usage_records(document: dict[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        for key in ("llm_calls", "embedding_calls"):
            calls = answer.get(key, [])
            if isinstance(calls, list):
                records.extend(item for item in calls if isinstance(item, dict))
    graph = document.get("graph", [])
    if isinstance(graph, list):
        records.extend(item for item in graph if isinstance(item, dict))
    return records


def _ledger_usage_document_is_valid(document: dict[str, object]) -> bool:
    """Validate the shape of the persisted ledger usage snapshot."""
    answers = document.get("answers")
    graph = document.get("graph")
    if not isinstance(answers, list) or not isinstance(graph, list):
        return False
    for answer in answers:
        if not isinstance(answer, dict):
            return False
        for key in ("llm_calls", "embedding_calls"):
            calls = answer.get(key, [])
            if not isinstance(calls, list) or any(not isinstance(item, dict) for item in calls):
                return False
    return all(isinstance(item, dict) for item in graph)


def _answer_usage_document_is_valid(document: dict[str, object]) -> bool:
    """Validate one Answer's usage snapshot before using it as evidence."""
    return all(
        isinstance(document.get(key, []), list)
        and all(isinstance(item, dict) for item in document.get(key, []))
        for key in ("llm_calls", "embedding_calls")
    )


def _usage_record_is_valid(record: dict[str, object]) -> bool:
    if record.get("no_charge") is True:
        return True
    token_keys = [key for key in ("prompt_tokens", "completion_tokens", "total_tokens") if key in record]
    if not token_keys:
        return False
    for key in token_keys:
        value = record.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    if "prompt_tokens" in record and "completion_tokens" in record and "total_tokens" in record:
        if int(record["total_tokens"]) < int(record["prompt_tokens"]) + int(record["completion_tokens"]):
            return False
    return record.get("usage_available") is True


def estimate_job_reservation(answers: Sequence[Answer]) -> Decimal:
    """Compute a conservative upper bound for the actual model calls.

    The estimate is made after Zhihu search, when the answer count and
    returned ContentText sizes are known.  It includes the maximum JSON-format
    retry count, answer/claim embeddings, and the bounded concept list.
    """
    if not answers:
        return Decimal("0")
    rates = (
        settings.budget_llm_input_cny_per_1k,
        settings.budget_llm_output_cny_per_1k,
        settings.budget_embedding_cny_per_1k,
    )
    if any(rate <= 0 for rate in rates):
        raise BudgetExhaustedError("BUDGET_PRICING_NOT_CONFIGURED")
    if len(answers) > 10:
        raise BudgetExhaustedError("BUDGET_UPPER_BOUND_UNAVAILABLE")

    input_rate = Decimal(str(rates[0]))
    output_rate = Decimal(str(rates[1]))
    embedding_rate = Decimal(str(rates[2]))
    # The provider contract currently allows three LLM attempts and a 4096
    # token response.  Configured bounds may increase that estimate, but may
    # not lower it and thereby under-reserve a real call.
    attempts = max(3, settings.budget_llm_max_attempts)
    max_output = max(4096, settings.budget_llm_max_output_tokens)
    max_embedding = max(
        4096,
        settings.budget_embedding_max_tokens_per_input,
        max_output,
    )
    max_concept = max(
        256,
        settings.budget_concept_max_tokens_per_input,
        max_output,
    )
    max_concepts = max(5, settings.budget_max_concepts_per_claim)
    total = Decimal("0")
    for answer in answers:
        # UTF-8 bytes are an upper bound on token count (each token contains
        # at least one byte), plus prompt framing.  This stays conservative
        # for Chinese and unusual Unicode snippets.
        content_bytes = len((answer.content_text or "").encode("utf-8"))
        input_tokens = max(1024, content_bytes + 512)
        llm_calls = attempts
        total += (
            Decimal(input_tokens * llm_calls) / 1000 * input_rate
            + Decimal(max_output * llm_calls) / 1000 * output_rate
        )
        # The answer embedding receives the complete ContentText.  Claim
        # text is model output, bounded by the conservative output limit.
        answer_embedding_tokens = max(1024, content_bytes)
        total += Decimal(answer_embedding_tokens) / 1000 * embedding_rate
        total += Decimal(5 * max_embedding) / 1000 * embedding_rate
        # At most five claims × five bounded concept names per claim.
        total += Decimal(5 * max_concepts * max_concept) / 1000 * embedding_rate
    return total


async def reserve_job_budget(
    session: AsyncSession,
    job: Job,
    query: Query,
    *,
    answers: Sequence[Answer] | None = None,
) -> BudgetLedger | None:
    """Reserve the computed upper bound before the first model call."""
    if query.data_mode != "production":
        return None
    if answers is None:
        result = await session.execute(
            select(Answer).where(Answer.query_id == query.id)
        )
        answers = result.scalars().all()
    reservation = estimate_job_reservation(answers)
    limit = Decimal(str(settings.budget_reserve_limit_cny))
    if reservation <= 0:
        return None
    if reservation > limit or reservation > Decimal(str(settings.budget_limit_cny)):
        raise BudgetExhaustedError("BUDGET_UPPER_BOUND_EXCEEDS_RESERVE")

    outstanding_result = await session.execute(
        select(func.coalesce(func.sum(BudgetLedger.reserved_cny), 0)).where(
            BudgetLedger.status == "reserved"
        )
    )
    spent_result = await session.execute(
        select(func.coalesce(func.sum(BudgetLedger.actual_cny), 0)).where(
            BudgetLedger.status == "settled"
        )
    )
    outstanding = Decimal(str(outstanding_result.scalar_one() or 0))
    spent = Decimal(str(spent_result.scalar_one() or 0))
    if outstanding + reservation > limit or spent + outstanding + reservation > Decimal(
        str(settings.budget_limit_cny)
    ):
        raise BudgetExhaustedError("BUDGET_EXHAUSTED")

    ledger = BudgetLedger(
        job_id=job.id,
        query_id=query.id,
        reserved_cny=reservation,
        status="reserved",
    )
    session.add(ledger)
    await session.flush()
    return ledger


async def settle_job_budget(session: AsyncSession, job_id) -> None:
    """Settle a successful job when current pricing is configured.

    If pricing is intentionally unset, the reservation stays in ``reserved``
    state with usage retained, so the ledger never claims an unknown cost was
    free. This is also the safe path for failed or timed-out jobs.
    """
    rates = (
        settings.budget_llm_input_cny_per_1k,
        settings.budget_llm_output_cny_per_1k,
        settings.budget_embedding_cny_per_1k,
    )
    if any(rate <= 0 for rate in rates):
        return
    ledger_result = await session.execute(
        select(BudgetLedger).where(BudgetLedger.job_id == job_id)
    )
    ledger = ledger_result.scalar_one_or_none()
    if ledger is None:
        return
    if ledger.status != "reserved":
        return
    if not ledger.provider_usage_json:
        # No ledger snapshot means the job did not reach the point where all
        # calls were accounted for; keep the reservation conservatively.
        return
    document = _decode_usage_document(ledger.provider_usage_json)
    if not _ledger_usage_document_is_valid(document):
        return
    records = _usage_records(document)
    if any(not _usage_record_is_valid(record) for record in records):
        # A provider did not return trustworthy usage.  Keep the reservation
        # so a missing meter can never be treated as a free call.
        return
    input_tokens = sum(
        int(record.get("prompt_tokens") or 0)
        for record in records
        if not record.get("no_charge")
    )
    output_tokens = sum(
        int(record.get("completion_tokens") or 0)
        for record in records
        if not record.get("no_charge")
    )
    embedding_tokens = sum(
        int(record.get("total_tokens") or 0)
        for record in records
        if "total_tokens" in record
        and "completion_tokens" not in record
        and not record.get("no_charge")
    )
    actual = (
        Decimal(input_tokens) / 1000 * Decimal(str(rates[0]))
        + Decimal(output_tokens) / 1000 * Decimal(str(rates[1]))
        + Decimal(embedding_tokens) / 1000 * Decimal(str(rates[2]))
    )
    if actual > Decimal(str(settings.budget_limit_cny)):
        return
    ledger.actual_cny = actual
    ledger.status = "settled"
    await session.flush()


async def record_job_usage(
    session: AsyncSession,
    job_id,
    query_id,
    *,
    graph_usage: list[dict[str, object]] | None = None,
) -> None:
    """Persist every known per-call usage record for a job."""
    result = await session.execute(
        select(BudgetLedger).where(BudgetLedger.job_id == job_id)
    )
    ledger = result.scalar_one_or_none()
    if ledger is None:
        return
    answers_result = await session.execute(
        select(Answer.analysis_usage_json).where(Answer.query_id == query_id)
    )
    answer_documents = [
        document
        for (raw,) in answers_result.all()
        if (document := _decode_usage_document(raw))
    ]
    document = {
        "answers": answer_documents,
        "graph": list(graph_usage or []),
    }
    ledger.provider_usage_json = json.dumps(document, ensure_ascii=False)
    await session.flush()


async def release_job_budget_if_no_usage(
    session: AsyncSession,
    job_id,
    *,
    reason: str,
) -> bool:
    """Release a reservation only when no billable call was recorded."""
    result = await session.execute(
        select(BudgetLedger).where(BudgetLedger.job_id == job_id)
    )
    ledger = result.scalar_one_or_none()
    if ledger is None or ledger.status != "reserved":
        return False
    document = _decode_usage_document(ledger.provider_usage_json)
    if ledger.provider_usage_json and not _ledger_usage_document_is_valid(document):
        return False
    if _usage_records(document):
        return False
    # A failure can happen after an Answer provider call but before the final
    # job snapshot is written.  Inspect the durable per-answer snapshots too;
    # otherwise that call could be mistaken for a free, pre-provider failure.
    query_id = getattr(ledger, "query_id", None)
    if query_id is not None:
        answer_result = await session.execute(
            select(Answer.analysis_usage_json).where(Answer.query_id == query_id)
        )
        for (raw,) in answer_result.all():
            answer_document = _decode_usage_document(raw)
            if raw and not _answer_usage_document_is_valid(answer_document):
                return False
            if _usage_records({"answers": [answer_document]}):
                return False
    ledger.actual_cny = Decimal("0")
    ledger.status = "released"
    ledger.provider_usage_json = json.dumps(
        {"answers": [], "graph": [], "release_reason": reason},
        ensure_ascii=False,
    )
    await session.flush()
    return True


__all__ = [
    "estimate_job_reservation",
    "record_job_usage",
    "release_job_budget_if_no_usage",
    "reserve_job_budget",
    "settle_job_budget",
]
