"""
MoveCidade — API (FastAPI) + simulador de telemetria + entrega do front-end compilado.

    uvicorn movecidade.main:app --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import auth, gestor, iot, publico
from .geo.tracado import CacheRotas
from .persistencia import Banco
from .repositorio import ErroNegocio, Repositorio


class _SemLocalizacaoNoLog(logging.Filter):
    """LGPD: remove a query string (lat/lon do passageiro) das linhas de log de acesso."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str):
            caminho = record.args[2]
            if "?" in caminho:
                record.args = (*record.args[:2], caminho.split("?", 1)[0] + "?[omitido]", *record.args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(_SemLocalizacaoNoLog())


def criar_app(repo: Optional[Repositorio] = None, iniciar_simulador: bool = True) -> FastAPI:
    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        if app.state.repo is None:
            banco = Banco(config.CAMINHO_BANCO)
            repositorio = Repositorio(banco, CacheRotas(config.CAMINHO_CACHE_ROTAS))
            repositorio.carregar()
            app.state.repo = repositorio
        if iniciar_simulador:
            app.state.repo.iniciar_frota()
        print(f"[MoveCidade] {len(app.state.repo.linhas())} linhas, {len(app.state.repo.pontos())} pontos, "
              f"{len(app.state.repo.veiculos())} ônibus · FATOR_TEMPO={config.FATOR_TEMPO}", flush=True)
        yield
        app.state.repo.parar_tudo()

    app = FastAPI(title="MoveCidade API", version="2.0", lifespan=ciclo_de_vida)
    app.state.repo = repo

    @app.exception_handler(ErroNegocio)
    async def _erro_negocio(_: Request, exc: ErroNegocio) -> JSONResponse:
        return JSONResponse({"erro": exc.mensagem}, status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def _erro_http(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"erro": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _erro_validacao(_: Request, exc: RequestValidationError) -> JSONResponse:
        campos = ", ".join(str(e.get("loc", ["?"])[-1]) for e in exc.errors()[:4])
        return JSONResponse({"erro": f"Dados inválidos na requisição ({campos})."}, status_code=422)

    app.include_router(iot.router)
    app.include_router(auth.router)
    app.include_router(publico.router)
    app.include_router(gestor.router)

    # Front-end compilado (npm run build). Em desenvolvimento quem serve é o Vite.
    dist = config.DIRETORIO_FRONTEND
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{caminho:path}", include_in_schema=False)
        async def spa(caminho: str):
            if caminho.startswith("api/"):
                return JSONResponse({"erro": "Recurso não encontrado."}, status_code=404)
            arquivo = (dist / caminho).resolve()
            if caminho and arquivo.is_file() and dist.resolve() in arquivo.parents:
                return FileResponse(arquivo)
            return FileResponse(dist / "index.html")

    return app


app = criar_app()
