"""ORM model registry — import all models to register with SQLAlchemy metadata."""
from app.models.audit_log import AuditLogModel
from app.models.embedding import EmbeddingModel
from app.models.feedback import FeedbackModel
from app.models.model_registry import ModelRegistryModel
from app.models.reranking import RerankingWeightModel
from app.models.ticket import JiraTicketModel
from app.models.user import UserModel

__all__ = [
    "UserModel",
    "JiraTicketModel",
    "EmbeddingModel",
    "FeedbackModel",
    "RerankingWeightModel",
    "ModelRegistryModel",
    "AuditLogModel",
]