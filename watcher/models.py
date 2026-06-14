"""
Pydantic models for Watcher API.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    created_at: str


class ListingSubmit(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=8192)
    price: float = Field(..., ge=0)


class ModerationResult(BaseModel):
    listing_id: str
    decision: str
    confidence: float
    reasons: List[str]
    latency_seconds: float
    next_step: str


class ReviewAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    moderator: Optional[str] = Field(None, max_length=128)
    notes: Optional[str] = Field(None, max_length=2048)


class ReviewItem(BaseModel):
    id: str
    listing_id: str
    title: str
    description: str
    price: float
    status: str
    priority: str
    ai_decision: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_reasons: Optional[List[str]] = None
    created_at: str


class StatsResponse(BaseModel):
    total_moderated: int
    auto_approved: int
    auto_rejected: int
    sent_to_review: int
    queue_depth: int
    avg_latency_seconds: float
    auto_approve_threshold: float
    review_threshold: float


class ImageData(BaseModel):
    id: str
    mime_type: str
    file_name: str
    created_at: str
