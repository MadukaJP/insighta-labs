from models.base import Base
from sqlalchemy import Column, ForeignKey, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from utils.generate_id import generate_id


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_id)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, index=True)

    key_hash = Column(String, nullable=False, unique=True)
    prefix = Column(String, nullable=False)  # for debugging (sk_live_xxx)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)