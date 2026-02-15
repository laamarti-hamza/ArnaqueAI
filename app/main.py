from __future__ import annotations

import json
from queue import Queue
from threading import Thread
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .schemas import ProposalRequest, SelectChoicesRequest, StepRequest, VictimVoiceRequest, VoteRequest
from .state import SimulationEngine
from .voice import VictimVoiceSynthesizer, VoiceSynthesisError

settings = get_settings()
engine = SimulationEngine(settings)
victim_voice = VictimVoiceSynthesizer(settings)
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
    voice_status = victim_voice.status()
    return {
        "status": "ok",
        "llm_enabled": llm_runtime_enabled,
        "llm_configured": settings.llm_enabled,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "victim_voice_enabled": voice_status.get("enabled", False),
        "victim_voice_model": voice_status.get("model", ""),
        "victim_voice_name": voice_status.get("voice", ""),
        "victim_voice_language": voice_status.get("language", ""),
        "victim_voice_reason": voice_status.get("reason", ""),
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


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/simulation/step/stream")
def simulation_step_stream(payload: StepRequest) -> StreamingResponse:
    def event_stream():
        queue: Queue[tuple[str, dict] | None] = Queue()

        def on_text_chunk(chunk: str) -> None:
            if chunk:
                queue.put(("chunk", {"text": chunk}))

        def run_step() -> None:
            try:
                snapshot = engine.step_stream(payload.scammer_input, on_text_chunk=on_text_chunk)
                queue.put(("done", {"state": snapshot}))
            except ValueError as exc:
                queue.put(("error", {"detail": str(exc)}))
            except Exception:
                queue.put(("error", {"detail": "Erreur interne pendant la reponse en streaming."}))
            finally:
                queue.put(None)

        worker = Thread(target=run_step, daemon=True)
        worker.start()

        while True:
            item = queue.get()
            if item is None:
                break
            event_name, event_payload = item
            yield _sse_event(event_name, event_payload)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.post("/api/voice/victim")
def synthesize_victim_voice(payload: VictimVoiceRequest) -> Response:
    try:
        audio_bytes, mime_type = victim_voice.synthesize(payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VoiceSynthesisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio_bytes, media_type=mime_type, headers={"Cache-Control": "no-store"})


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
