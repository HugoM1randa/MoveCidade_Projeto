"""Endpoints do painel do gestor (todos exigem sessão) e o CRUD de linhas, pontos e veículos."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from .. import config, servicos
from ..cores import contraste, nome_da_cor, validar_cor
from ..eta import classificar_lotacao, para_relogio_usuario
from ..ia import turno_atual
from ..repositorio import Repositorio
from .auth import exigir_gestor

router = APIRouter(prefix="/api", tags=["gestor"], dependencies=[Depends(exigir_gestor)])


def repo_de(request: Request) -> Repositorio:
    return request.app.state.repo


def _veiculo_gestor(repo: Repositorio, vid: str) -> Dict[str, Any]:
    v = repo.veiculo(vid)
    tel = repo.telemetria(vid)
    linha = repo.linha(v.linha_id) if v else None
    desvio = repo.desvio_horario_s(vid)
    return {
        "id": vid, "linha_id": v.linha_id if v else None, "numero": linha.numero if linha else None,
        "cor": linha.cor if linha else None, "capacidade": v.capacidade if v else None,
        "acessivel": v.acessivel if v else False, "status": repo.status_veiculo(vid),
        "ao_vivo": repo.ao_vivo(vid), "lat": tel.latitude if tel else None, "lon": tel.longitude if tel else None,
        "ocupacao_pct": round(tel.occupancy_rate * 100) if tel else None,
        "lotacao": classificar_lotacao(tel.occupancy_rate) if tel else None,
        "proximo_ponto": tel.next_stop if tel else None,
        "atraso_min": round(para_relogio_usuario(desvio) / 60, 1) if desvio is not None else None,
    }


# ------------------------------------------------------------------ painel
@router.get("/gestor/painel")
def painel(request: Request) -> dict:
    repo = repo_de(request)
    frota = [_veiculo_gestor(repo, v.id) for v in repo.veiculos() if v.ativo]
    pendentes = repo.alertas.pendentes()
    return {
        "turno": turno_atual(),
        "veiculos_ativos": sum(1 for v in frota if v["ao_vivo"]),
        "veiculos_cadastrados": len(frota),
        "kpis": repo.kpis(),
        "frota": frota,
        "avisos": pendentes[:3],
        "alertas_pendentes": len(pendentes),
        "fator_tempo": config.FATOR_TEMPO,
    }


@router.get("/gestor/veiculos/{veiculo_id}")
def detalhe_veiculo(veiculo_id: str, request: Request) -> dict:
    """Detalhe técnico — só aparece ao gestor quando ele abre um veículo."""
    repo = repo_de(request)
    if repo.veiculo(veiculo_id) is None:
        raise HTTPException(404, "Ônibus não encontrado.")
    tel = repo.telemetria(veiculo_id)
    sinal = repo.segundos_desde_sinal(veiculo_id)
    return {
        **_veiculo_gestor(repo, veiculo_id),
        "ultimo_sinal_s": round(sinal) if sinal is not None else None,
        "tecnico": None if tel is None else {
            "velocidade_kmh": tel.speed_kmh, "temperatura_c": tel.internal_temperature_c,
            "portas": "abertas" if tel.door_status == "OPEN" else "fechadas",
            "passageiros": tel.passenger_count, "odometro_km": round(tel.odometer_m / 1000, 2),
            "ponto_atual": tel.current_stop, "velocidade_media_trecho_kmh": tel.segment_avg_speed_kmh,
            "eta_proximo_ponto_s": tel.eta_next_stop_s, "viagem": tel.trip_id,
        },
    }


@router.get("/telemetria/atual")
def telemetria_atual(request: Request) -> dict:
    repo = repo_de(request)
    pacotes = [t.model_dump() for t in (repo.telemetria(v.id) for v in repo.veiculos()) if t]
    return {"veiculos_ativos": sum(1 for v in repo.veiculos() if repo.ao_vivo(v.id)), "veiculos": pacotes,
            "recebidos": repo.pacotes_recebidos, "rejeitados": repo.pacotes_rejeitados}


# ------------------------------------------------------------------ alertas
@router.get("/gestor/alertas")
def alertas(request: Request) -> dict:
    repo = repo_de(request)
    return {"pendentes": repo.alertas.pendentes(), "decisoes": repo.banco.decisoes_recentes(15),
            "resumo": repo.resumo_turno()}


@router.post("/gestor/alertas/{alerta_id}/decisao")
def decidir(alerta_id: str, request: Request, dados: Dict[str, str] = Body(...)) -> dict:
    return repo_de(request).decidir_alerta(alerta_id, dados.get("decisao", ""))


# ------------------------------------------------------------------ linhas
@router.get("/gestor/linhas")
def linhas_gestor(request: Request) -> list:
    repo = repo_de(request)
    saida = []
    for l in repo.linhas():
        veiculos = repo.veiculos(l.id)
        saida.append({
            **servicos.linha_publica(repo, l), "status": repo.status_linha(l),
            "qtd_pontos": len(l.pontos), "qtd_veiculos": len(veiculos),
            "origem_tracado": l.origem_tracado,
            "veiculos": [_veiculo_gestor(repo, v.id) for v in veiculos],
        })
    return saida


@router.get("/gestor/cores/proxima")
def proxima_cor(request: Request) -> dict:
    return repo_de(request).proxima_cor_livre()


@router.post("/gestor/cores/validar")
def validar(request: Request, dados: Dict[str, Optional[str]] = Body(...)) -> dict:
    repo = repo_de(request)
    cor = (dados.get("cor") or "").strip()
    ok, motivo = validar_cor(cor, repo.cores_em_uso(exceto=dados.get("linha_id")))
    resposta: Dict[str, Any] = {"aprovada": ok, "mensagem": motivo}
    if ok:
        resposta.update(contraste=round(contraste(cor, "#FFFFFF"), 2), nome=nome_da_cor(cor))
    return resposta


@router.post("/linhas", status_code=201)
def criar_linha(request: Request, dados: Dict[str, Any] = Body(...)) -> dict:
    repo = repo_de(request)
    return servicos.linha_publica(repo, repo.salvar_linha(dados))


@router.put("/linhas/{linha_id}")
def editar_linha(linha_id: str, request: Request, dados: Dict[str, Any] = Body(...)) -> dict:
    repo = repo_de(request)
    return servicos.linha_publica(repo, repo.salvar_linha(dados, linha_id))


@router.delete("/linhas/{linha_id}")
def remover_linha(linha_id: str, request: Request) -> dict:
    repo_de(request).remover_linha(linha_id)
    return {"removido": True}


# ------------------------------------------------------------------ pontos
@router.post("/pontos", status_code=201)
def criar_ponto(request: Request, dados: Dict[str, Any] = Body(...)) -> dict:
    repo = repo_de(request)
    return servicos.ponto_publico(repo, repo.salvar_ponto(dados))


@router.put("/pontos/{ponto_id}")
def editar_ponto(ponto_id: str, request: Request, dados: Dict[str, Any] = Body(...)) -> dict:
    repo = repo_de(request)
    return servicos.ponto_publico(repo, repo.salvar_ponto(dados, ponto_id))


@router.delete("/pontos/{ponto_id}")
def remover_ponto(ponto_id: str, request: Request) -> dict:
    repo_de(request).remover_ponto(ponto_id)
    return {"removido": True}


# ------------------------------------------------------------------ veículos
@router.get("/veiculos")
def listar_veiculos(request: Request, linha_id: Optional[str] = None) -> List[dict]:
    repo = repo_de(request)
    return [_veiculo_gestor(repo, v.id) for v in repo.veiculos(linha_id)]


@router.post("/veiculos", status_code=201)
def criar_veiculo(request: Request, dados: Dict[str, Any] = Body(...)) -> dict:
    repo = repo_de(request)
    v = repo.criar_veiculo(dados)
    return _veiculo_gestor(repo, v.id)


@router.delete("/veiculos/{veiculo_id}")
def remover_veiculo(veiculo_id: str, request: Request) -> dict:
    repo_de(request).remover_veiculo(veiculo_id)
    return {"removido": True}
