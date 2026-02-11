from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class StepRequest(BaseModel):
    scammer_input: str = Field(..., min_length=1, max_length=1200)


class ProposalRequest(BaseModel):
    proposal: str = Field(..., min_length=1, max_length=180)


class SelectChoicesRequest(BaseModel):
    proposals: Optional[List[str]] = None


class VoteRequest(BaseModel):
    winner_index: int = Field(..., ge=0, le=2)
