"""Gateway de ingestão IoT: POST /api/iot/telemetria (contrato do protótipo, com validação)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/iot", tags=["IoT"])


@router.post("/telemetria")
async def receber(request: Request) -> JSONResponse:
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"erro": "O corpo da requisição precisa ser um JSON válido."}, status_code=422)
    if not isinstance(payload, dict):
        return JSONResponse({"erro": "O pacote de telemetria precisa ser um objeto JSON."}, status_code=422)
    tel = request.app.state.repo.ingerir(payload)   # ErroNegocio(422) tratado em main.py
    return JSONResponse({"status": "sucesso", "vehicle_id": tel.vehicle_id})
