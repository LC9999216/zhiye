"""ORM models — Stage 3: Query, Answer, Job, Claim, Concept and association tables.

Importing this package registers every model on ``Base.metadata`` so that
``init_db()`` and Alembic autogenerate see the complete set of tables.
"""

from app.models.answer import Answer
from app.models.answer_similarity import AnswerSimilarity
from app.models.chat_message import ChatMessage
from app.models.claim import Claim
from app.models.claim_concept import ClaimConcept
from app.models.concept import Concept
from app.models.job import Job
from app.models.query import Query

__all__ = [
    "Answer",
    "AnswerSimilarity",
    "ChatMessage",
    "Claim",
    "ClaimConcept",
    "Concept",
    "Job",
    "Query",
]
