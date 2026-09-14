from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import settings
from app.core.exceptions import BudgetExhaustedError
from app.services.budget_service import (
    estimate_job_reservation,
    record_job_usage,
    release_job_budget_if_no_usage,
    reserve_job_budget,
    settle_job_budget,
)


def _session(*results):
    session = AsyncMock()
    session.execute.side_effect = list(results)
    session.flush = AsyncMock()
    session.add = Mock()
    return session


@pytest.mark.asyncio
async def test_reservation_blocks_when_upper_bound_exceeds_reserve(monkeypatch):
    monkeypatch.setattr(settings, "budget_llm_input_cny_per_1k", 1.0)
    monkeypatch.setattr(settings, "budget_llm_output_cny_per_1k", 1.0)
    monkeypatch.setattr(settings, "budget_embedding_cny_per_1k", 1.0)
    monkeypatch.setattr(settings, "budget_llm_max_attempts", 1)
    monkeypatch.setattr(settings, "budget_llm_max_output_tokens", 1)
    monkeypatch.setattr(settings, "budget_embedding_max_tokens_per_input", 1)
    monkeypatch.setattr(settings, "budget_concept_max_tokens_per_input", 1)
    monkeypatch.setattr(settings, "budget_max_concepts_per_claim", 1)
    monkeypatch.setattr(settings, "budget_reserve_limit_cny", 18.0)
    monkeypatch.setattr(settings, "budget_limit_cny", 20.0)
    outstanding = Mock(scalar_one=lambda: Decimal("0"))
    spent = Mock(scalar_one=lambda: Decimal("0"))
    session = _session(outstanding, spent)
    job = SimpleNamespace(id=uuid.uuid4())
    query = SimpleNamespace(id=uuid.uuid4(), data_mode="production")

    answer = SimpleNamespace(content_text="short answer")
    with pytest.raises(BudgetExhaustedError, match="BUDGET_UPPER_BOUND_EXCEEDS_RESERVE"):
        await reserve_job_budget(session, job, query, answers=[answer])


@pytest.mark.asyncio
async def test_reservation_blocks_when_project_budget_is_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "budget_llm_input_cny_per_1k", 0.000001)
    monkeypatch.setattr(settings, "budget_llm_output_cny_per_1k", 0.000001)
    monkeypatch.setattr(settings, "budget_embedding_cny_per_1k", 0.000001)
    monkeypatch.setattr(settings, "budget_reserve_limit_cny", 18.0)
    monkeypatch.setattr(settings, "budget_limit_cny", 20.0)
    outstanding = Mock(scalar_one=lambda: Decimal("17.999999"))
    spent = Mock(scalar_one=lambda: Decimal("0"))
    session = _session(outstanding, spent)
    job = SimpleNamespace(id=uuid.uuid4())
    query = SimpleNamespace(id=uuid.uuid4(), data_mode="production")

    with pytest.raises(BudgetExhaustedError, match="BUDGET_EXHAUSTED"):
        await reserve_job_budget(
            session, job, query, answers=[SimpleNamespace(content_text="short answer")]
        )


def test_reservation_estimate_is_zero_for_no_answers():
    assert estimate_job_reservation([]) == Decimal("0")


@pytest.mark.asyncio
async def test_unknown_usage_keeps_reservation(monkeypatch):
    monkeypatch.setattr(settings, "budget_llm_input_cny_per_1k", 1.0)
    monkeypatch.setattr(settings, "budget_llm_output_cny_per_1k", 1.0)
    monkeypatch.setattr(settings, "budget_embedding_cny_per_1k", 1.0)
    ledger = SimpleNamespace(
        status="reserved",
        provider_usage_json=json.dumps(
            {"answers": [{"llm_calls": [{"usage_available": False}]}]}
        ),
        actual_cny=None,
    )
    result = Mock(scalar_one_or_none=lambda: ledger)
    session = _session(result)

    await settle_job_budget(session, uuid.uuid4())

    assert ledger.status == "reserved"
    assert ledger.actual_cny is None


@pytest.mark.asyncio
async def test_complete_usage_settles_actual_cost(monkeypatch):
    monkeypatch.setattr(settings, "budget_llm_input_cny_per_1k", 1.0)
    monkeypatch.setattr(settings, "budget_llm_output_cny_per_1k", 2.0)
    monkeypatch.setattr(settings, "budget_embedding_cny_per_1k", 3.0)
    ledger = SimpleNamespace(
        status="reserved",
        provider_usage_json=None,
        actual_cny=None,
    )
    ledger_result = Mock(scalar_one_or_none=lambda: ledger)
    answers_result = Mock(
        all=lambda: [
            (
                json.dumps(
                    {
                        "llm_calls": [
                            {
                                "prompt_tokens": 100,
                                "completion_tokens": 20,
                                "usage_available": True,
                            }
                        ],
                        "embedding_calls": [
                            {"total_tokens": 50, "usage_available": True}
                        ],
                    }
                ),
            )
        ]
    )
    record_session = _session(ledger_result, answers_result)
    await record_job_usage(record_session, uuid.uuid4(), uuid.uuid4())
    settle_session = _session(Mock(scalar_one_or_none=lambda: ledger))
    await settle_job_budget(settle_session, uuid.uuid4())

    assert ledger.status == "settled"
    assert ledger.actual_cny == Decimal("0.290")


@pytest.mark.asyncio
async def test_release_without_any_provider_usage(monkeypatch):
    ledger = SimpleNamespace(status="reserved", provider_usage_json=None, actual_cny=None)
    result = Mock(scalar_one_or_none=lambda: ledger)
    session = _session(result)

    released = await release_job_budget_if_no_usage(
        session, uuid.uuid4(), reason="ZHIHU_AUTH_FAILED"
    )

    assert released is True
    assert ledger.status == "released"
    assert ledger.actual_cny == Decimal("0")


@pytest.mark.asyncio
async def test_release_keeps_reservation_when_answer_usage_was_persisted():
    ledger = SimpleNamespace(
        status="reserved",
        provider_usage_json=None,
        actual_cny=None,
        query_id=uuid.uuid4(),
    )
    ledger_result = Mock(scalar_one_or_none=lambda: ledger)
    answer_result = Mock(
        all=lambda: [
            (json.dumps({"llm_calls": [{"usage_available": False}]}),)
        ]
    )
    session = _session(ledger_result, answer_result)

    released = await release_job_budget_if_no_usage(
        session, uuid.uuid4(), reason="JOB_FAILED"
    )

    assert released is False
    assert ledger.status == "reserved"
