"""
Consultas do app do passageiro: pontos próximos, chegadas por ponto, detalhe da linha e busca.

LGPD: as coordenadas do passageiro recebidas aqui são usadas só no cálculo da resposta.
Nada é gravado em banco nem em log.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .dominio import Linha, Ponto
from .eta import classificar_lotacao, eta_simulacao, para_relogio_usuario, tempo_planejado_simulacao
from .geo import haversine_m
from .repositorio import Repositorio

FUSO_MATAO = timezone(timedelta(hours=-3))   # America/Sao_Paulo (sem horário de verão desde 2019)
VELOCIDADE_A_PE_M_MIN = 80.0


def agora_local() -> datetime:
    return datetime.now(FUSO_MATAO)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def destino_da_linha(repo: Repositorio, linha: Linha) -> str:
    if "circular" in linha.nome.lower():
        return "Circular"
    ultimo = repo.ponto(linha.pontos[-1]) if linha.pontos else None
    return ultimo.nome if ultimo else linha.nome


def _indice(linha: Linha, ponto_id: str) -> Optional[int]:
    try:
        return linha.pontos.index(ponto_id)
    except ValueError:
        return None


# ============================================================ tabela programada
def horarios_programados(repo: Repositorio, linha: Linha, ponto_id: str, a_partir: Optional[datetime] = None,
                         quantidade: int = 6) -> List[datetime]:
    """Partidas a cada `intervalo_min` do primeiro ponto (05h–24h) + tempo planejado até o ponto."""
    k = _indice(linha, ponto_id)
    if k is None or linha.comprimento <= 0:
        return []
    ativos = repo.pontos_ativos_da_linha(linha)
    deslocamento = timedelta(seconds=para_relogio_usuario(
        tempo_planejado_simulacao(linha, ativos, 0.0, linha.s_pontos[k])))
    agora = a_partir or agora_local()
    saida: List[datetime] = []
    dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    for dia_offset in (0, 1):
        base = dia + timedelta(days=dia_offset)
        minuto = config.HORARIO_INICIO_OPERACAO * 60
        while minuto < config.HORARIO_FIM_OPERACAO * 60:
            chegada = base + timedelta(minutes=minuto) + deslocamento
            if chegada >= agora:
                saida.append(chegada)
                if len(saida) >= quantidade:
                    return saida
            minuto += linha.intervalo_min
    return saida


def tabela_horarios(repo: Repositorio, linha: Linha, ponto_id: str) -> List[str]:
    return [h.strftime("%H:%M") for h in horarios_programados(repo, linha, ponto_id, quantidade=8)]


# ============================================================ previsões
def previsoes_veiculos(repo: Repositorio, linha: Linha, ponto_id: str,
                       somente_acessiveis: bool = False) -> List[Dict[str, Any]]:
    """Todos os ônibus AO VIVO da linha, com o tempo (relógio do usuário) até o ponto, do mais cedo ao mais tarde."""
    k = _indice(linha, ponto_id)
    if k is None or linha.comprimento <= 0:
        return []
    ativos = repo.pontos_ativos_da_linha(linha)
    if not ativos[k]:
        return []
    s_ponto = linha.s_pontos[k]
    saida = []
    for v in repo.veiculos(linha.id):
        if somente_acessiveis and not v.acessivel:
            continue
        if not repo.ao_vivo(v.id):
            continue
        tel = repo.telemetria(v.id)
        s_v = repo.posicao_s(v.id, linha)
        if tel is None or s_v is None:
            continue
        eta = para_relogio_usuario(eta_simulacao(linha, repo.historico, ativos, s_v, tel.is_at_stop, s_ponto))
        saida.append({
            "veiculo_id": v.id, "eta_s": round(eta), "acessivel": v.acessivel,
            "lotacao": classificar_lotacao(tel.occupancy_rate), "ocupacao_pct": round(min(1.0, tel.occupancy_rate) * 100),
            "proximo_ponto": tel.next_stop, "no_ponto": tel.is_at_stop and abs(s_v - s_ponto) <= 15,
        })
    saida.sort(key=lambda x: x["eta_s"])
    return saida


def previsao_linha_no_ponto(repo: Repositorio, linha: Linha, ponto_id: str,
                            somente_acessiveis: bool = False) -> Dict[str, Any]:
    """Próximo ônibus e o seguinte desta linha neste ponto: ao vivo, programado ou sem previsão."""
    base = {
        "linha_id": linha.id, "numero": linha.numero, "nome": linha.nome, "cor": linha.cor,
        "cor_nome": linha.cor_nome, "padrao": linha.padrao, "destino": destino_da_linha(repo, linha),
    }
    vivos = previsoes_veiculos(repo, linha, ponto_id, somente_acessiveis)
    if vivos:
        primeiro = vivos[0]
        return {**base, "fonte": "ao_vivo", "eta_s": primeiro["eta_s"],
                "eta_seguinte_s": vivos[1]["eta_s"] if len(vivos) > 1 else None,
                "lotacao": primeiro["lotacao"], "acessivel": primeiro["acessivel"],
                "veiculo_id": primeiro["veiculo_id"], "horario": None}
    # sem telemetria recente → nunca "ao vivo": usa a tabela programada
    tem_frota = any(v.ativo and (v.acessivel or not somente_acessiveis) for v in repo.veiculos(linha.id))
    k = _indice(linha, ponto_id)
    ponto_operando = k is not None and repo.pontos_ativos_da_linha(linha)[k]
    if tem_frota and ponto_operando:
        horarios = horarios_programados(repo, linha, ponto_id, quantidade=2)
        if horarios:
            agora = agora_local()
            return {**base, "fonte": "programado",
                    "eta_s": round((horarios[0] - agora).total_seconds()),
                    "eta_seguinte_s": round((horarios[1] - agora).total_seconds()) if len(horarios) > 1 else None,
                    "lotacao": None, "acessivel": None, "veiculo_id": None,
                    "horario": horarios[0].strftime("%H:%M")}
    return {**base, "fonte": "sem_previsao", "eta_s": None, "eta_seguinte_s": None,
            "lotacao": None, "acessivel": None, "veiculo_id": None, "horario": None}


def _ordenar_previsoes(previsoes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(previsoes, key=lambda p: (p["eta_s"] is None, p["eta_s"] if p["eta_s"] is not None else 0, p["numero"]))


def ponto_publico(repo: Repositorio, ponto: Ponto) -> Dict[str, Any]:
    return ponto.to_dict([l.numero for l in repo.linhas_do_ponto(ponto.id)])


def chegadas_no_ponto(repo: Repositorio, ponto: Ponto, somente_acessiveis: bool = False) -> List[Dict[str, Any]]:
    return _ordenar_previsoes([previsao_linha_no_ponto(repo, l, ponto.id, somente_acessiveis)
                               for l in repo.linhas_do_ponto(ponto.id)])


def pontos_proximos(repo: Repositorio, lat: float, lon: float, raio: float = 800.0, limite: int = 3,
                    somente_acessiveis: bool = False, rampa: bool = False, piso_tatil: bool = False) -> Dict[str, Any]:
    candidatos: List[Tuple[float, Ponto]] = []
    for p in repo.pontos():
        if not p.operando or not repo.linhas_do_ponto(p.id):
            continue
        if rampa and not p.acessibilidade.get("rampa"):
            continue
        if piso_tatil and not p.acessibilidade.get("piso_tatil"):
            continue
        candidatos.append((haversine_m((lat, lon), p.coord), p))
    candidatos.sort(key=lambda x: x[0])
    dentro = [c for c in candidatos if c[0] <= raio][:limite]
    fora_do_raio = False
    if not dentro and candidatos:
        dentro, fora_do_raio = candidatos[:1], True
    itens = []
    for distancia, p in dentro:
        itens.append({
            **ponto_publico(repo, p),
            "distancia_m": round(distancia),
            "caminhada_min": max(1, round(distancia / VELOCIDADE_A_PE_M_MIN)),
            "linhas": chegadas_no_ponto(repo, p, somente_acessiveis),
        })
    return {"pontos": itens, "fora_do_raio": fora_do_raio, "raio_m": raio}


# ============================================================ detalhe da linha
def ponto_da_linha_mais_proximo(repo: Repositorio, linha: Linha, lat: float, lon: float) -> Optional[Ponto]:
    candidatos = [repo.ponto(pid) for pid in linha.pontos]
    candidatos = [p for p in candidatos if p and p.operando]
    if not candidatos:
        return None
    return min(candidatos, key=lambda p: haversine_m((lat, lon), p.coord))


def linha_publica(repo: Repositorio, linha: Linha, com_rota: bool = True) -> Dict[str, Any]:
    dados = {
        **linha.resumo(), "destino": destino_da_linha(repo, linha),
        "origem": (repo.ponto(linha.pontos[0]).nome if linha.pontos and repo.ponto(linha.pontos[0]) else ""),
        "pontos": list(linha.pontos), "comprimento_m": round(linha.comprimento),
    }
    if com_rota:
        dados["rota"] = [[round(a, 5), round(b, 5)] for a, b in linha.rota[::2]] + (
            [[round(linha.rota[-1][0], 5), round(linha.rota[-1][1], 5)]] if linha.rota else [])
    return dados


def detalhe_linha(repo: Repositorio, linha: Linha, ponto_id: Optional[str],
                  somente_acessiveis: bool = False) -> Dict[str, Any]:
    ponto = repo.ponto(ponto_id) if ponto_id and ponto_id in linha.pontos else None
    if ponto is None:
        ponto = next((repo.ponto(pid) for pid in linha.pontos if repo.ponto(pid) and repo.ponto(pid).operando), None)
    previsao = previsao_linha_no_ponto(repo, linha, ponto.id, somente_acessiveis) if ponto else None
    proximos = previsoes_veiculos(repo, linha, ponto.id, somente_acessiveis) if ponto else []
    vivos = {p["veiculo_id"] for p in proximos}
    sem_sinal = [{"veiculo_id": v.id, "acessivel": v.acessivel} for v in repo.veiculos(linha.id)
                 if v.ativo and v.id not in vivos and not repo.ao_vivo(v.id)]

    # trajeto: pontos em ordem e onde estão os ônibus agora (entre qual ponto e o seguinte)
    ativos = repo.pontos_ativos_da_linha(linha)
    onibus_por_trecho: Dict[int, List[Dict[str, Any]]] = {}
    for v in repo.veiculos(linha.id):
        if not repo.ao_vivo(v.id):
            continue
        s = repo.posicao_s(v.id, linha)
        tel = repo.telemetria(v.id)
        if s is None or tel is None:
            continue
        trecho = 0
        for i, sp in enumerate(linha.s_pontos):
            if s + 15 >= sp:
                trecho = i
        no_ponto = tel.is_at_stop and abs(s - linha.s_pontos[trecho]) <= 15
        onibus_por_trecho.setdefault(trecho, []).append({"veiculo_id": v.id, "no_ponto": no_ponto,
                                                         "acessivel": v.acessivel})
    trajeto = []
    for i, pid in enumerate(linha.pontos):
        p = repo.ponto(pid)
        if p is None:
            continue
        trajeto.append({"ordem": i + 1, "id": p.id, "nome": p.nome, "operando": ativos[i],
                        "acessibilidade": p.acessibilidade, "onibus": onibus_por_trecho.get(i, [])})

    return {
        "linha": linha_publica(repo, linha, com_rota=False),
        "ponto": ponto_publico(repo, ponto) if ponto else None,
        "previsao": previsao,
        "proximos": proximos,
        "sem_sinal": sem_sinal,
        "horarios": tabela_horarios(repo, linha, ponto.id) if ponto else [],
        "trajeto": trajeto,
        "intervalo_min": linha.intervalo_min,
    }


def tempo_planejado_entre(repo: Repositorio, linha: Linha, de: str, ate: str) -> Optional[float]:
    """Tempo planejado (relógio do usuário, s) entre dois pontos da linha, no sentido da viagem."""
    i, j = _indice(linha, de), _indice(linha, ate)
    if i is None or j is None:
        return None
    ativos = repo.pontos_ativos_da_linha(linha)
    s_i, s_j = linha.s_pontos[i], linha.s_pontos[j]
    if s_j >= s_i:
        t = tempo_planejado_simulacao(linha, ativos, s_i, s_j)
    else:
        t = (tempo_planejado_simulacao(linha, ativos, s_i, linha.comprimento + 1) + config.RETORNO_TERMINAL_S
             + tempo_planejado_simulacao(linha, ativos, 0.0, s_j))
    return para_relogio_usuario(t)


# ============================================================ mapa ao vivo
def veiculos_no_mapa(repo: Repositorio) -> List[Dict[str, Any]]:
    """Dados de posição para o mapa do passageiro — sem velocidade, temperatura nem códigos técnicos."""
    saida = []
    for v in repo.veiculos():
        if not v.ativo:
            continue
        tel = repo.telemetria(v.id)
        linha = repo.linha(v.linha_id)
        if tel is None or linha is None:
            continue
        ao_vivo = repo.ao_vivo(v.id)
        proximo_id = None
        atual_id = None
        eta_proximo = None
        if ao_vivo:
            s = repo.posicao_s(v.id, linha) or 0.0
            ativos = repo.pontos_ativos_da_linha(linha)
            alvo = next((i for i, sp in enumerate(linha.s_pontos) if ativos[i] and sp > s + 15), None)
            if alvo is None:
                alvo = 0
            proximo_id = linha.pontos[alvo]
            passados = [i for i, sp in enumerate(linha.s_pontos) if ativos[i] and sp <= s + 15]
            atual_id = linha.pontos[passados[-1]] if passados else None
            eta_proximo = round(para_relogio_usuario(
                eta_simulacao(linha, repo.historico, ativos, s, tel.is_at_stop, linha.s_pontos[alvo])))
        proximo = repo.ponto(proximo_id) if proximo_id else None
        saida.append({
            "id": v.id, "linha_id": linha.id, "numero": linha.numero, "cor": linha.cor, "cor_nome": linha.cor_nome,
            "lat": tel.latitude, "lon": tel.longitude, "ao_vivo": ao_vivo, "acessivel": v.acessivel,
            "lotacao": classificar_lotacao(tel.occupancy_rate) if ao_vivo else None,
            "no_ponto": tel.is_at_stop and ao_vivo,
            "proximo_ponto": proximo.nome if proximo else None, "proximo_ponto_id": proximo_id,
            "ponto_atual_id": atual_id,
            "eta_proximo_s": eta_proximo,
        })
    return saida


# ============================================================ busca
def buscar(repo: Repositorio, q: str, tipo: str = "todos", lat: Optional[float] = None,
           lon: Optional[float] = None, somente_acessiveis: bool = False) -> Dict[str, Any]:
    termos = [t for t in _sem_acento(q).replace("→", " ").replace("↔", " ").split() if t not in ("para", "ate", "-", "–")]
    resultados_linhas: List[Dict[str, Any]] = []
    resultados_pontos: List[Dict[str, Any]] = []
    if not termos:
        return {"linhas": [], "pontos": []}

    def texto_da_linha(l: Linha) -> str:
        nomes = " ".join(repo.ponto(p).nome + " " + repo.ponto(p).referencia for p in l.pontos if repo.ponto(p))
        return _sem_acento(f"{l.numero} {l.nome} {nomes}")

    for l in repo.linhas():
        texto = texto_da_linha(l)
        if tipo == "linhas":
            casa = any(l.numero.lower().startswith(t) for t in termos) or all(t in _sem_acento(l.nome) for t in termos)
        elif tipo == "trajetos":
            casa = len(termos) >= 1 and all(t in texto for t in termos)
        elif tipo == "pontos":
            casa = False
        else:
            casa = any(l.numero.lower().startswith(t) for t in termos) or all(t in texto for t in termos)
        if not casa:
            continue
        ponto_ref = None
        if lat is not None and lon is not None:
            ponto_ref = ponto_da_linha_mais_proximo(repo, l, lat, lon)
        if ponto_ref is None:
            ponto_ref = repo.ponto(l.pontos[0]) if l.pontos else None
        previsao = previsao_linha_no_ponto(repo, l, ponto_ref.id, somente_acessiveis) if ponto_ref else None
        resultados_linhas.append({**linha_publica(repo, l, com_rota=False), "previsao": previsao,
                                  "ponto_ref": {"id": ponto_ref.id, "nome": ponto_ref.nome} if ponto_ref else None})

    if tipo in ("todos", "pontos"):
        for p in repo.pontos():
            if not p.operando:
                continue
            texto = _sem_acento(f"{p.nome} {p.referencia}")
            if all(t in texto for t in termos):
                item = {**ponto_publico(repo, p), "linhas": chegadas_no_ponto(repo, p, somente_acessiveis)}
                if lat is not None and lon is not None:
                    item["distancia_m"] = round(haversine_m((lat, lon), p.coord))
                resultados_pontos.append(item)
    return {"linhas": resultados_linhas, "pontos": resultados_pontos}
