"""ORM models — placeholder schemas; real columns arrive in Stages 3-8.

Importing this package registers every model on ``Base.metadata`` so that
``init_db()`` and Alembic autogenerate see the complete set of tables.
"""

from app.models.answer import Answer
from app.models.chat_message import ChatMessage
from app.models.claim import Claim
from app.models.concept import Concept
from app.models.job import Job
from app.models.query import Query

__all__ = ["Answer", "ChatMessage", "Claim", "Concept", "Job", "Query"]
