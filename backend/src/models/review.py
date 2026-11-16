from sqlalchemy import String, JSON, Double, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Review(Base):
    __tablename__ = 'reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    frozen_records: Mapped[list] = mapped_column(JSON, default=list)
    frozen_checksum: Mapped[str] = mapped_column(String(64))
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=86400)
    status: Mapped[str] = mapped_column(String(20), default='open')
    result_dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    closed_at: Mapped[float | None] = mapped_column(Double, nullable=True)
class ReviewItem(Base):
    __tablename__ = 'review_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('reviews.id'))
    idx: Mapped[int] = mapped_column(Integer)
    record: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='open')
    final_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rationale: Mapped[str] = mapped_column(String(1000), default='')
    resolved_at: Mapped[float | None] = mapped_column(Double, nullable=True)
class ReviewAssignment(Base):
    __tablename__ = 'review_assignments'
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('reviews.id'))
    item_id: Mapped[int] = mapped_column(ForeignKey('review_items.id'))
    kind: Mapped[str] = mapped_column(String(20), default='review')
    assignee_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(20), default='open')
    opinion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rationale: Mapped[str] = mapped_column(String(1000), default='')
    claimed_at: Mapped[float] = mapped_column(Double)
    due_at: Mapped[float] = mapped_column(Double)
    submitted_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    revoked_at: Mapped[float | None] = mapped_column(Double, nullable=True)
