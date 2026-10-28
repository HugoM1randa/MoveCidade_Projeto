"""Endpoints públicos (app do passageiro). Nenhum dado de localização é gravado ou registrado em log."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from .. import config, servicos
from ..repositorio import Repositorio

router = APIRouter(prefix="/api", tags=["passageiro"])


def repo_de(request: Request) -> Repositorio:
    return request.app.state.repo


@router.get("/status")
def status(request: Request) -> dict:
    repo = repo_de(request)
    return {"versao_cadastro": repo.versao_cadastro, "fator_tempo": config.FATOR_TEMPO,
            "agora": servicos.agora_local().isoformat(timespec="seconds")}


@router.get("/linhas")
def listar_linhas(request: Request) -> list:
    repo = repo_de(request)
    return [servicos.linha_publica(repo, l) for l in repo.linhas()]


@router.get("/linhas/{linha_id}")
def obter_linha(linha_id: str, request: Request) -> dict:
    repo = repo_de(request)
    linha = repo.linha(linha_id)
    if linha is None:
        raise HTTPException(404, "Linha não encontrada.")
    return servicos.linha_publica(repo, linha)


@router.get("/linhas/{linha_id}/detalhe")
def detalhe_linha(linha_id: str, request: Request, ponto: Optional[str] = None,
                  lat: Optional[float] = Query(None, ge=-90, le=90), lon: Optional[float] = Query(None, ge=-180, le=180),
                  acessivel: bool = False) -> dict:
    repo = repo_de(request)
    linha = repo.linha(linha_id)
    if linha is None:
        raise HTTPException(404, "Linha não encontrada.")
    if not ponto and lat is not None and lon is not None:
        perto = servicos.ponto_da_linha_mais_proximo(repo, linha, lat, lon)
        ponto = perto.id if perto else None
    return servicos.detalhe_linha(repo, linha, ponto, acessivel)


@router.get("/linhas/{linha_id}/tempo-planejado")
def tempo_planejado(linha_id: str, de: str, ate: str, request: Request) -> dict:
    repo = repo_de(request)
    linha = repo.linha(linha_id)
    if linha is None:
        raise HTTPException(404, "Linha não encontrada.")
    t = servicos.tempo_planejado_entre(repo, linha, de, ate)
    if t is None:
        raise HTTPException(404, "Um dos pontos não faz parte desta linha.")
    return {"segundos": round(t)}


@router.get("/pontos")
def listar_pontos(request: Request) -> list:
    repo = repo_de(request)
    return [servicos.ponto_publico(repo, p) for p in repo.pontos()]


@router.get("/pontos/proximos")
def pontos_proximos(request: Request,
                    lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
                    raio: float = Query(800, gt=0, le=5000), limite: int = Query(3, ge=1, le=10),
                    acessivel: bool = False, rampa: bool = False, piso_tatil: bool = False) -> dict:
    # LGPD: lat/lon só entram no cálculo; não são gravados nem registrados em log.
    return servicos.pontos_proximos(repo_de(request), lat, lon, raio, limite, acessivel, rampa, piso_tatil)


@router.get("/pontos/{ponto_id}")
def obter_ponto(ponto_id: str, request: Request, acessivel: bool = False) -> dict:
    repo = repo_de(request)
    ponto = repo.ponto(ponto_id)
    if ponto is None:
        raise HTTPException(404, "Ponto não encontrado.")
    return {**servicos.ponto_publico(repo, ponto), "linhas": servicos.chegadas_no_ponto(repo, ponto, acessivel)}


@router.get("/veiculos/mapa")
def veiculos_mapa(request: Request) -> dict:
    repo = repo_de(request)
    return {"versao_cadastro": repo.versao_cadastro, "veiculos": servicos.veiculos_no_mapa(repo)}


@router.post("/veiculos/{veiculo_id}/acessibilidade")
def acionar_acessibilidade(veiculo_id: str, request: Request) -> dict:
    repo = repo_de(request)
    veiculo = repo.veiculo(veiculo_id)
    if veiculo is None:
        raise HTTPException(404, "Ônibus não encontrado.")
    repo.pedir_acessibilidade(veiculo_id)
    linha = repo.linha(veiculo.linha_id)
    return {"ok": True, "mensagem": f"Pedido de acessibilidade enviado ao ônibus {veiculo_id}"
                                     f"{f' da linha {linha.numero}' if linha else ''}."}


@router.get("/busca")
def busca(request: Request, q: str = Query(..., min_length=1, max_length=80), tipo: str = "todos",
          lat: Optional[float] = Query(None, ge=-90, le=90), lon: Optional[float] = Query(None, ge=-180, le=180),
          acessivel: bool = False) -> dict:
    if tipo not in ("todos", "linhas", "pontos", "trajetos"):
        tipo = "todos"
    return servicos.buscar(repo_de(request), q, tipo, lat, lon, acessivel)
