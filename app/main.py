from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .schemas import ProposalRequest, SelectChoicesRequest, StepRequest, VoteRequest
from .state import SimulationEngine

settings = get_settings()
engine = SimulationEngine(settings)
app = FastAPI(title="Simulateur d'Arnaque Dynamique")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    llm_runtime_enabled = bool(engine.director.chat and engine.moderator.chat and engine.victim.chat)
    return {
        "status": "ok",
        "llm_enabled": llm_runtime_enabled,
        "llm_configured": settings.llm_enabled,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
    }


@app.get("/api/simulation/state")
def get_state() -> dict:
    return engine.snapshot()


@app.post("/api/simulation/reset")
def reset_simulation() -> dict:
    return engine.reset()


@app.post("/api/simulation/step")
def simulation_step(payload: StepRequest) -> dict:
    try:
        return engine.step(payload.scammer_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audience/submit")
def submit_audience_proposal(payload: ProposalRequest) -> dict:
    try:
        return engine.submit_proposal(payload.proposal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audience/select")
def select_audience_choices(payload: SelectChoicesRequest) -> dict:
    try:
        return engine.select_choices(payload.proposals)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audience/vote")
def vote_audience_choice(payload: VoteRequest) -> dict:
    try:
        return engine.vote_choice(payload.winner_index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/audience/vote/simulate")
def simulate_vote() -> dict:
    try:
        return engine.simulate_vote()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
