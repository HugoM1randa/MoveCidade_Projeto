#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MoveCidade - Plataforma de Telemetria e Inteligencia Operacional para Transporte
Publico Urbano (SmartCity Lab / Projeto 3).

Aplicacao autonoma em arquivo unico. Somente biblioteca padrao do Python 3.8+.

    python3 movecidade.py            # execucao normal
    python3 movecidade.py --offline  # nao consulta rede (usa cache ou malha local)
    python3 movecidade.py --test     # executa a suite de testes automatizados
    python3 movecidade.py --porta N  # altera a porta (padrao 8000)

Mapeamento com o Documento de Visao de Produto
----------------------------------------------
Secao 4.1 Gestao de rotas e paradas ........ CRUD REST /api/linhas e /api/veiculos
Secao 4.1 Rastreamento e previsao .......... telemetria 1,5-2,0 s + ETA por trecho
Secao 4.1 Historico e acessibilidade ....... /api/historico/* + botao do passageiro
Secao 4.1 Painel operacional ............... visao Gestor com KPIs da secao 6
Secao 4.1 Integracao IoT ................... centrais embarcadas -> gateway HTTP
Secao 4.2 Previsao de horarios ............. Kharon.estimar_chegadas (EWMA + dwell)
Secao 4.2 Deteccao de anomalias ............ Kharon.analisar (atraso, lotacao, bunching)
Secao 4.2 Sumarizacao analitica ............ Kharon.sumarizar / KPIs consolidados
Secao 4.2 Suporte a decisao ................ Hermes.avisos / Hermes.resumo_de_turno
Secao 5   Limites e riscos de IA ........... faixa de confianca no ETA + rotulo de
                                             sugestao nao vinculante em todo aviso
Secao 6   Indicadores ...................... Indicadores.instantaneo (5 KPIs)
Secao 8   Papeis dos agentes ............... secoes 5 a 10 deste arquivo

Nota de honestidade tecnica
---------------------------
Nao ha LLM nem modelo treinado embarcado. Kharon e Hermes sao implementacoes
deterministicas e auditaveis (media movel exponencial, limiares calibrados e
regras de headway). O documento de visao preve XGBoost / Isolation Forest em
producao; aqui a camada analitica e explicita e inspecionavel, o que e o
comportamento adequado para um prototipo academico. Toda sugestao gerada vem
rotulada como nao vinculante, conforme a Secao 5 do documento.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
import queue
import re
import random
import statistics
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import webbrowser
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

# =============================================================================
# 1. CONFIGURACAO
# =============================================================================

HOST: str = "localhost"
PORTA_PADRAO: int = 8000

INTERVALO_MIN_S: float = 1.5          # janela de emissao de telemetria por veiculo
INTERVALO_MAX_S: float = 2.0
FATOR_TEMPO: float = 5.0              # aceleracao do tempo simulado (1.0 = tempo real)

ESPACAMENTO_ROTA_M: float = 12.0      # reamostragem do tracado
RAIO_CHEGADA_PARADA_M: float = 12.0   # tolerancia de chegada ao ponto
DWELL_MIN_S: float = 12.0             # tempo minimo de porta aberta
DWELL_MAX_S: float = 34.0
VELOCIDADE_PROJETO_KMH: float = 21.0  # velocidade comercial medida na simulacao, base do horario planejado

LIMITE_ALERTA_OCUPACAO: float = 0.70  # Secao 6: limite de conforto operacional
LIMITE_LOTACAO_CRITICA: float = 0.95
TOLERANCIA_PONTUALIDADE_S: float = 120.0
LIMITE_ATRASO_S: float = 180.0        # desvio acima disto gera anomalia de atraso
# Taxas por SEGUNDO simulado, nao por ciclo: o intervalo de emissao varia e a
# fisica do transito nao pode depender da frequencia com que ela e amostrada.
TAXA_CONGESTIONAMENTO_POR_S: float = 1 / 420.0  # uma retencao a cada ~7 min de percurso
TAXA_RETENCAO_PONTUAL_POR_S: float = 1 / 45.0   # semaforo, travessia, conversao
CONGESTIONAMENTO_MIN_S: float = 45.0            # duracao da retencao, em tempo simulado
CONGESTIONAMENTO_MAX_S: float = 160.0
DISTANCIA_MINIMA_TRECHO_M: float = 50.0  # abaixo disto o trecho nao alimenta o historico
FATOR_BUNCHING: float = 0.40          # headway abaixo deste fator do planejado = comboiamento

TAMANHO_BUFFER_LOG: int = 80
TAMANHO_HISTORICO_POSICOES: int = 900 # ~30 min de trilha por veiculo
TAMANHO_HISTORICO_CHEGADAS: int = 600
TAMANHO_BUFFER_OFFLINE: int = 120     # store-and-forward da central embarcada

OSRM_ENDPOINT: str = "https://router.project-osrm.org/route/v1/driving/"
OSRM_TIMEOUT_S: float = 8.0
ARQUIVO_CACHE_ROTAS: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "movecidade_rotas_cache.json"
)

Coordenada = Tuple[float, float]  # (latitude, longitude)

# Pasta do projeto (passageiro.html, gestor.html, vendor/).
APP_DIR: str = os.path.dirname(os.path.abspath(__file__))
# Token PUBLICO do Mapbox (pk.*), feito para uso no navegador. Nao fica no codigo:
# defina MOVECIDADE_MAPBOX_TOKEN no .env. Sem token, o painel usa o Leaflet local.
MAPBOX_TOKEN: str = os.environ.get("MOVECIDADE_MAPBOX_TOKEN", "")

RAIO_TERRA_M: float = 6_371_008.8
METROS_POR_GRAU_LAT: float = 111_320.0


# =============================================================================
# 2. GEOMETRIA
# =============================================================================

def haversine_m(a: Coordenada, b: Coordenada) -> float:
    """Distancia geodesica em metros entre duas coordenadas (lat, lon)."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(min(1.0, h)))


def distancias_acumuladas(rota: Sequence[Coordenada]) -> List[float]:
    """Distancia acumulada (m) do inicio do tracado ate cada vertice."""
    acumulado: List[float] = [0.0]
    for i in range(len(rota) - 1):
        acumulado.append(acumulado[-1] + haversine_m(rota[i], rota[i + 1]))
    return acumulado


def probabilidade_no_intervalo(taxa_por_s: float, dt_s: float) -> float:
    """
    Converte uma taxa de ocorrencia por segundo na probabilidade de o evento
    acontecer ao menos uma vez em `dt_s` (processo de Poisson).

    Sem esta conversao, um evento declarado "por ciclo" ficaria mais ou menos
    frequente conforme o intervalo de emissao da telemetria - a fisica passaria a
    depender da taxa de amostragem, o que invalidaria qualquer indicador.
    """
    if taxa_por_s <= 0.0 or dt_s <= 0.0:
        return 0.0
    return 1.0 - math.exp(-taxa_por_s * dt_s)


def deslocar(origem: Coordenada, leste_m: float, norte_m: float) -> Coordenada:
    """Desloca uma coordenada por um vetor em metros no plano local."""
    lat, lon = origem
    dlat = norte_m / METROS_POR_GRAU_LAT
    dlon = leste_m / (METROS_POR_GRAU_LAT * math.cos(math.radians(lat)))
    return (lat + dlat, lon + dlon)


def reamostrar(caminho: Sequence[Coordenada],
               espacamento_m: float = ESPACAMENTO_ROTA_M) -> List[Coordenada]:
    """
    Densifica o tracado inserindo pontos a cada `espacamento_m`.

    Os vertices originais sao SEMPRE preservados na saida, de modo que esquinas e
    curvas permanecem exatas: a densificacao ocorre apenas dentro de segmentos ja
    adjacentes da via, nunca entre pontos distantes.
    """
    if len(caminho) < 2 or espacamento_m <= 0:
        return [tuple(p) for p in caminho]  # type: ignore[misc]

    acumulado = distancias_acumuladas(caminho)
    total = acumulado[-1]
    if total <= 0.0:
        return [tuple(caminho[0])]  # type: ignore[misc]

    # Uniao entre multiplos do espacamento e os vertices originais.
    alvos = {round(v, 4) for v in acumulado}
    passo = 0.0
    while passo < total:
        alvos.add(round(passo, 4))
        passo += espacamento_m
    ordenados = sorted(alvos)

    saida: List[Coordenada] = []
    j = 0
    for s in ordenados:
        while j < len(acumulado) - 2 and acumulado[j + 1] < s:
            j += 1
        comprimento = acumulado[j + 1] - acumulado[j]
        t = 0.0 if comprimento <= 0 else (s - acumulado[j]) / comprimento
        t = max(0.0, min(1.0, t))
        p, q = caminho[j], caminho[j + 1]
        saida.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return saida


def posicao_em(rota: Sequence[Coordenada], acumulado: Sequence[float], s: float) -> Coordenada:
    """Converte posicao curvilinea (m) em coordenada, interpolando no segmento atual."""
    if not rota:
        return (0.0, 0.0)
    if len(rota) == 1:
        return rota[0]
    s = max(0.0, min(s, acumulado[-1]))
    i = max(0, min(bisect.bisect_right(acumulado, s) - 1, len(rota) - 2))
    comprimento = acumulado[i + 1] - acumulado[i]
    t = 0.0 if comprimento <= 0 else (s - acumulado[i]) / comprimento
    p, q = rota[i], rota[i + 1]
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def projetar_na_rota(rota: Sequence[Coordenada], acumulado: Sequence[float],
                     alvo: Coordenada) -> float:
    """Posicao curvilinea (m) do vertice da rota mais proximo de `alvo`."""
    if not rota:
        return 0.0
    melhor_i, melhor_d = 0, float("inf")
    for i, ponto in enumerate(rota):
        d = haversine_m(ponto, alvo)
        if d < melhor_d:
            melhor_i, melhor_d = i, d
    return acumulado[melhor_i]


# =============================================================================
# 3. ROTEAMENTO: OSRM COM CACHE EM DISCO E MALHA VIARIA LOCAL
# =============================================================================
#
# Ordem de resolucao do tracado de cada linha:
#   1. cache em disco (movecidade_rotas_cache.json) - determinista e offline;
#   2. API publica OSRM, que devolve a geometria real das vias (e grava no cache);
#   3. malha viaria ortogonal local, gerada por deslocamentos em metros ao longo
#      de dois eixos perpendiculares rotacionados segundo o azimute real do
#      arruamento. Produz esquinas em angulo reto, nunca uma diagonal continua.
#
# A terceira opcao existe para que a apresentacao nunca dependa de rede. Ela e
# sintetica e o sistema a rotula como tal na interface (campo origem_tracado).
# =============================================================================

class CacheRotas:
    """Cache de geometrias em disco, chaveado pelo hash dos waypoints."""

    def __init__(self, caminho: str) -> None:
        self._caminho = caminho
        self._lock = threading.Lock()
        self._dados: Dict[str, List[List[float]]] = {}
        self._carregar()

    @staticmethod
    def chave(waypoints: Sequence[Coordenada]) -> str:
        bruto = ";".join(f"{lat:.5f},{lon:.5f}" for lat, lon in waypoints)
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]

    def _carregar(self) -> None:
        try:
            with open(self._caminho, "r", encoding="utf-8") as arq:
                conteudo = json.load(arq)
            if isinstance(conteudo, dict):
                self._dados = conteudo
        except (OSError, ValueError):
            self._dados = {}

    def obter(self, waypoints: Sequence[Coordenada]) -> Optional[List[Coordenada]]:
        with self._lock:
            bruto = self._dados.get(self.chave(waypoints))
        if not bruto or len(bruto) < 2:
            return None
        return [(float(p[0]), float(p[1])) for p in bruto]

    def guardar(self, waypoints: Sequence[Coordenada], geometria: Sequence[Coordenada]) -> None:
        with self._lock:
            self._dados[self.chave(waypoints)] = [[round(a, 6), round(b, 6)] for a, b in geometria]
            try:
                with open(self._caminho, "w", encoding="utf-8") as arq:
                    json.dump(self._dados, arq)
            except OSError:
                pass  # cache e otimizacao, nunca requisito


CACHE_ROTAS = CacheRotas(ARQUIVO_CACHE_ROTAS)


def buscar_rota_osrm(waypoints: Sequence[Coordenada]) -> Optional[List[Coordenada]]:
    """Consulta a demo publica do OSRM. Devolve None em qualquer falha."""
    if len(waypoints) < 2:
        return None
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    url = f"{OSRM_ENDPOINT}{coords}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MoveCidade-SmartCityLab/2.0"})
        with urllib.request.urlopen(req, timeout=OSRM_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if payload.get("code") != "Ok" or not payload.get("routes"):
        return None
    try:
        linha = payload["routes"][0]["geometry"]["coordinates"]
    except (KeyError, IndexError, TypeError):
        return None
    return [(float(lat), float(lon)) for lon, lat in linha]


def tracado_em_malha(origem: Coordenada,
                     movimentos: Sequence[Tuple[str, float]],
                     azimute_graus: float) -> List[Coordenada]:
    """
    Constroi um itinerario sobre uma malha viaria ortogonal.

    `movimentos` e uma sequencia de (eixo, metros), com eixo em {"A", "B"}. O eixo
    A aponta no azimute informado e o eixo B e perpendicular a ele; metros
    negativos invertem o sentido. Cada troca de eixo e uma esquina em 90 graus, o
    que reproduz a geometria de quarteirao em vez de uma diagonal.
    """
    rad = math.radians(azimute_graus)
    eixo_a = (math.sin(rad), math.cos(rad))    # (leste, norte)
    eixo_b = (math.cos(rad), -math.sin(rad))

    pontos: List[Coordenada] = [origem]
    atual = origem
    for eixo, metros in movimentos:
        vetor = eixo_a if eixo.upper() == "A" else eixo_b
        atual = deslocar(atual, vetor[0] * metros, vetor[1] * metros)
        pontos.append(atual)
    return pontos


def resolver_tracado(waypoints: Sequence[Coordenada],
                     fallback: Optional[Sequence[Coordenada]] = None,
                     offline: bool = False) -> Tuple[List[Coordenada], str]:
    """Resolve o tracado final. Devolve (rota_densificada, origem_do_tracado)."""
    em_cache = CACHE_ROTAS.obter(waypoints)
    if em_cache:
        return reamostrar(em_cache), "CACHE"

    if not offline:
        geometria = buscar_rota_osrm(waypoints)
        if geometria and len(geometria) >= 2:
            CACHE_ROTAS.guardar(waypoints, geometria)
            return reamostrar(geometria), "OSRM"

    base = fallback if fallback and len(fallback) >= 2 else waypoints
    return reamostrar(base), "MALHA-LOCAL"


# =============================================================================
# 4. MODELO DE DOMINIO
# =============================================================================

@dataclass
class Parada:
    """Ponto de embarque e desembarque associado a uma linha."""
    id: str
    nome: str
    latitude: float
    longitude: float
    posicao_m: float = 0.0        # posicao curvilinea sobre o tracado
    chegada_planejada_s: float = 0.0  # segundos desde a partida do terminal
    rampa: bool = False
    piso_tatil: bool = False

    def publico(self) -> Dict[str, Any]:
        return {"id": self.id, "nome": self.nome,
                "latitude": self.latitude, "longitude": self.longitude,
                "rampa": self.rampa, "piso_tatil": self.piso_tatil}


@dataclass
class Linha:
    """Linha de transporte: identidade, tracado denso, paradas e horario planejado."""
    id: str
    nome: str
    rota: List[Coordenada]
    paradas: List[Parada]
    cor: str = "#38bdf8"
    origem_tracado: str = "MALHA-LOCAL"
    headway_planejado_s: float = 600.0

    @property
    def extensao_m(self) -> float:
        return distancias_acumuladas(self.rota)[-1] if len(self.rota) > 1 else 0.0

    def tempo_planejado_em(self, posicao_m: float) -> float:
        """
        Horario planejado (s desde a partida) para uma posicao qualquer do
        itinerario, interpolado entre as paradas que a cercam.

        Sem isto, o desvio so poderia ser medido nos pontos, e qualquer leitura
        intermediaria ficaria sistematicamente negativa - o veiculo ainda nao
        chegou ao proximo ponto, logo pareceria sempre adiantado. O indicador de
        pontualidade e a anomalia de atraso dependem desta referencia continua.
        """
        if not self.paradas:
            return 0.0
        primeira = self.paradas[0]
        if posicao_m <= primeira.posicao_m:
            return primeira.chegada_planejada_s

        for anterior, seguinte in zip(self.paradas, self.paradas[1:]):
            if posicao_m <= seguinte.posicao_m:
                trecho = seguinte.posicao_m - anterior.posicao_m
                if trecho <= 0:
                    return seguinte.chegada_planejada_s
                fracao = (posicao_m - anterior.posicao_m) / trecho
                return (anterior.chegada_planejada_s +
                        fracao * (seguinte.chegada_planejada_s - anterior.chegada_planejada_s))

        return self.paradas[-1].chegada_planejada_s

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "cor": self.cor,
            "origem_tracado": self.origem_tracado,
            "total_vertices": len(self.rota),
            "extensao_km": round(self.extensao_m / 1000.0, 2),
            "headway_planejado_min": round(self.headway_planejado_s / 60.0, 1),
            "rota": [[round(lat, 6), round(lon, 6)] for lat, lon in self.rota],
            "paradas": [
                {**p.publico(),
                 "posicao_m": round(p.posicao_m, 1),
                 "chegada_planejada_s": round(p.chegada_planejada_s, 1)}
                for p in self.paradas
            ],
        }


@dataclass
class Veiculo:
    """Veiculo operacional vinculado a uma linha."""
    id: str
    linha_id: str
    capacidade: int
    acessivel: bool = True
    ativo: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Telemetria:
    """
    Contrato unico de telemetria, trafegado em POST /api/iot/telemetria.
    Qualquer alteracao aqui exige atualizar ESQUEMA_TELEMETRIA (secao 5).
    """
    timestamp: str
    vehicle_id: str
    route_id: str
    trip_id: str
    latitude: float
    longitude: float
    speed_kmh: float
    door_status: str              # OPEN | CLOSED
    passenger_count: int
    passenger_capacity: int
    occupancy_rate: float
    occupancy_alert: bool         # regra independente: occupancy_rate > 0.70
    internal_temperature_c: float
    accessibility_button: bool
    accessible_vehicle: bool
    is_at_stop: bool
    current_stop: str
    next_stop: str
    next_stop_index: int
    distance_next_stop_m: float
    position_m: float
    route_progress: float         # 0.0 .. 1.0
    odometer_m: float
    trip_elapsed_s: float
    schedule_deviation_s: float   # positivo = atrasado
    segment_avg_speed_kmh: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Anomalia:
    """Diagnostico emitido por Kharon sobre um veiculo."""
    codigo: str
    severidade: str   # INFO | ATENCAO | CRITICO
    titulo: str
    detalhe: str
    vehicle_id: str
    route_id: str
    detectado_em: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Chegada:
    """Evento historico de chegada a uma parada."""
    vehicle_id: str
    route_id: str
    stop_id: str
    stop_name: str
    instante: str
    desvio_s: float
    ocupacao: float
    passageiros_embarcados: int
    passageiros_desembarcados: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# 5. AEGIS - VALIDACAO DE CONTRATO E PRIVACIDADE (LGPD)
# =============================================================================
#
# Responsabilidades (Secao 8.1 do documento de visao):
#   - validar o payload de telemetria antes de qualquer persistencia;
#   - pseudonimizar identificadores na superficie publica do passageiro;
#   - mascarar o console de pacotes brutos exibido na interface.
# =============================================================================

class ErroValidacao(ValueError):
    """Payload de telemetria fora do contrato."""


ESQUEMA_TELEMETRIA: Dict[str, Tuple[type, ...]] = {
    "timestamp": (str,),
    "vehicle_id": (str,),
    "route_id": (str,),
    "trip_id": (str,),
    "latitude": (int, float),
    "longitude": (int, float),
    "speed_kmh": (int, float),
    "door_status": (str,),
    "passenger_count": (int,),
    "passenger_capacity": (int,),
    "occupancy_rate": (int, float),
    "occupancy_alert": (bool,),
    "internal_temperature_c": (int, float),
    "accessibility_button": (bool,),
    "accessible_vehicle": (bool,),
    "is_at_stop": (bool,),
    "current_stop": (str,),
    "next_stop": (str,),
    "next_stop_index": (int,),
    "distance_next_stop_m": (int, float),
    "position_m": (int, float),
    "route_progress": (int, float),
    "odometer_m": (int, float),
    "trip_elapsed_s": (int, float),
    "schedule_deviation_s": (int, float),
    "segment_avg_speed_kmh": (int, float),
}


def validar_telemetria(payload: Dict[str, Any]) -> Telemetria:
    """
    Valida presenca, tipo e faixa de cada campo. Falha cedo e com mensagem util,
    em vez de deixar dado invalido contaminar o historico e os indicadores.
    """
    if not isinstance(payload, dict):
        raise ErroValidacao("payload deve ser um objeto JSON")

    faltando = sorted(set(ESQUEMA_TELEMETRIA) - set(payload))
    if faltando:
        raise ErroValidacao(f"campos ausentes: {', '.join(faltando)}")
    excedentes = sorted(set(payload) - set(ESQUEMA_TELEMETRIA))
    if excedentes:
        raise ErroValidacao(f"campos nao previstos no contrato: {', '.join(excedentes)}")

    for campo, tipos in ESQUEMA_TELEMETRIA.items():
        valor = payload[campo]
        # bool e subclasse de int em Python: checar explicitamente.
        if bool in tipos and not isinstance(valor, bool):
            raise ErroValidacao(f"campo '{campo}' deve ser booleano")
        if bool not in tipos and isinstance(valor, bool):
            raise ErroValidacao(f"campo '{campo}' nao aceita booleano")
        if not isinstance(valor, tipos):
            esperado = " ou ".join(t.__name__ for t in tipos)
            raise ErroValidacao(f"campo '{campo}' deve ser {esperado}")

    if not -90.0 <= float(payload["latitude"]) <= 90.0:
        raise ErroValidacao("latitude fora de faixa")
    if not -180.0 <= float(payload["longitude"]) <= 180.0:
        raise ErroValidacao("longitude fora de faixa")
    if float(payload["speed_kmh"]) < 0.0:
        raise ErroValidacao("velocidade nao pode ser negativa")
    if payload["door_status"] not in ("OPEN", "CLOSED"):
        raise ErroValidacao("door_status deve ser OPEN ou CLOSED")
    if int(payload["passenger_capacity"]) <= 0:
        raise ErroValidacao("capacidade deve ser positiva")
    if int(payload["passenger_count"]) < 0:
        raise ErroValidacao("contagem de passageiros nao pode ser negativa")
    if not 0.0 <= float(payload["route_progress"]) <= 1.0:
        raise ErroValidacao("route_progress deve estar entre 0 e 1")
    if payload["door_status"] == "OPEN" and float(payload["speed_kmh"]) > 0.5:
        raise ErroValidacao("porta aberta com veiculo em movimento: leitura inconsistente")

    return Telemetria(**payload)


def pseudonimizar(identificador: str) -> str:
    """
    Identificador estavel e nao reversivel para exposicao publica.
    Mantem rastreabilidade dentro de uma execucao sem revelar a placa/prefixo.
    """
    digest = hashlib.sha256(identificador.encode("utf-8")).hexdigest()
    return f"V-{digest[:6].upper()}"


CAMPOS_MASCARADOS = ("trip_id",)


def mascarar_pacote(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Versao do pacote segura para exibicao no console da interface."""
    copia = dict(payload)
    for campo in CAMPOS_MASCARADOS:
        if campo in copia:
            copia[campo] = "***"
    if "vehicle_id" in copia:
        copia["vehicle_id"] = pseudonimizar(str(copia["vehicle_id"]))
    return copia


def faixa_ocupacao(taxa: float) -> str:
    """
    Ocupacao em faixa qualitativa para o passageiro.
    Expor a contagem exata de pessoas a bordo nao traz beneficio ao usuario e
    amplia a superficie de dados; a faixa resolve a necessidade real.
    """
    if taxa < 0.35:
        return "VAZIO"
    if taxa < 0.70:
        return "MODERADO"
    if taxa < LIMITE_LOTACAO_CRITICA:
        return "CHEIO"
    return "LOTADO"


# =============================================================================
# 6. KHARON - DATA & AI ENGINEERING
# =============================================================================
#
# Previsao de chegada, deteccao de anomalias e sumarizacao analitica. Tudo
# deterministico e auditavel. Cada funcao devolve tambem a base de calculo, de
# modo que a interface possa explicar ao gestor de onde veio o numero.
# =============================================================================

class HistoricoTrechos:
    """
    Velocidade media por trecho (parada -> parada), por linha, via media movel
    exponencial. E a base da previsao de chegada: o ETA usa o comportamento
    observado daquele trecho especifico, nao uma velocidade fixa de catalogo.
    """

    ALFA: float = 0.30  # peso da amostra nova

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._medias: Dict[Tuple[str, int], float] = {}
        self._amostras: Dict[Tuple[str, int], int] = defaultdict(int)

    def registrar(self, route_id: str, indice_trecho: int, velocidade_kmh: float) -> None:
        if velocidade_kmh <= 0.5:
            return
        chave = (route_id, indice_trecho)
        with self._lock:
            anterior = self._medias.get(chave)
            self._medias[chave] = (velocidade_kmh if anterior is None
                                   else anterior * (1 - self.ALFA) + velocidade_kmh * self.ALFA)
            self._amostras[chave] += 1

    def media(self, route_id: str, indice_trecho: int) -> Tuple[float, int]:
        """Devolve (velocidade_kmh, numero_de_amostras). Zero amostras = sem historico."""
        chave = (route_id, indice_trecho)
        with self._lock:
            return self._medias.get(chave, 0.0), self._amostras.get(chave, 0)


class Kharon:
    """Camada analitica: previsao, deteccao e sumarizacao."""

    def __init__(self, historico: HistoricoTrechos) -> None:
        self._historico = historico

    # ------------------------------------------------------------------ ETA
    def estimar_chegadas(self, tel: Telemetria, linha: Linha,
                         quantas: int = 4) -> List[Dict[str, Any]]:
        """
        Previsao de chegada para as proximas paradas.

        O ETA acumula, para cada trecho a frente:
            tempo de percurso = distancia / velocidade media observada do trecho
            + tempo de permanencia previsto nas paradas intermediarias.

        Secao 5 do documento de visao: a previsao e probabilistica. A faixa de
        confianca aqui e derivada do numero de amostras ja observadas naquele
        trecho - pouca observacao produz faixa larga, e isso e exibido ao usuario
        em vez de escondido atras de um numero unico.
        """
        resultados: List[Dict[str, Any]] = []
        if not linha.paradas:
            return resultados

        acumulado_s = 0.0
        confianca_min = 1.0
        posicao = tel.position_m
        dwell_medio = (DWELL_MIN_S + DWELL_MAX_S) / 2.0

        indice = max(0, tel.next_stop_index)
        for passo in range(quantas):
            i = indice + passo
            if i >= len(linha.paradas):
                break
            parada = linha.paradas[i]
            distancia = max(0.0, parada.posicao_m - posicao)

            media, amostras = self._historico.media(linha.id, i)
            if amostras >= 3 and media > 1.0:
                referencia = media
                confianca = min(1.0, 0.55 + 0.05 * amostras)
            else:
                referencia = VELOCIDADE_PROJETO_KMH
                confianca = 0.45
            confianca_min = min(confianca_min, confianca)

            acumulado_s += distancia / max(1.0, referencia / 3.6)
            if passo > 0:
                acumulado_s += dwell_medio
            if passo == 0 and tel.is_at_stop:
                acumulado_s += dwell_medio * 0.5

            margem = acumulado_s * (1.0 - confianca_min) * 0.6
            resultados.append({
                "stop_id": parada.id,
                "stop_name": parada.nome,
                "eta_s": round(acumulado_s, 1),
                "eta_min_s": round(max(0.0, acumulado_s - margem), 1),
                "eta_max_s": round(acumulado_s + margem, 1),
                "confianca": round(confianca_min, 2),
                "base": ("media observada do trecho" if amostras >= 3
                         else "velocidade de projeto (sem historico suficiente)"),
                "velocidade_referencia_kmh": round(referencia, 1),
                "amostras": amostras,
            })
            posicao = parada.posicao_m
        return resultados

    # ------------------------------------------------------------ ANOMALIAS
    def analisar(self, tel: Telemetria, linha: Linha,
                 frota_da_linha: Sequence[Telemetria]) -> List[Anomalia]:
        """
        Deteccao de anomalias a partir do estado observado - nao por sorteio.

        Tres familias, conforme Secao 8.1 (Kharon):
          LOTACAO_CRITICA  ocupacao acima do limite critico;
          ATRASO_OPERACIONAL  desvio em relacao ao horario planejado da viagem;
          COMBOIAMENTO  headway real muito abaixo do planejado para a linha.
        """
        agora = datetime.now(timezone.utc).isoformat()
        encontradas: List[Anomalia] = []

        if tel.occupancy_rate >= LIMITE_LOTACAO_CRITICA:
            encontradas.append(Anomalia(
                codigo="LOTACAO_CRITICA",
                severidade="CRITICO",
                titulo="Lotacao critica",
                detalhe=(f"Veiculo com {tel.passenger_count} de {tel.passenger_capacity} lugares "
                         f"({tel.occupancy_rate * 100:.0f}%), acima da capacidade recomendada."),
                vehicle_id=tel.vehicle_id, route_id=tel.route_id, detectado_em=agora))

        if tel.schedule_deviation_s > LIMITE_ATRASO_S:
            minutos = tel.schedule_deviation_s / 60.0
            encontradas.append(Anomalia(
                codigo="ATRASO_OPERACIONAL",
                severidade="CRITICO" if minutos >= 8 else "ATENCAO",
                titulo="Atraso em relacao ao planejado",
                detalhe=(f"Viagem {minutos:.1f} min atras do horario previsto na altura de "
                         f"{tel.next_stop}."),
                vehicle_id=tel.vehicle_id, route_id=tel.route_id, detectado_em=agora))

        bunching = self._detectar_comboiamento(tel, linha, frota_da_linha)
        if bunching is not None:
            encontradas.append(bunching)

        return encontradas

    def _detectar_comboiamento(self, tel: Telemetria, linha: Linha,
                               frota: Sequence[Telemetria]) -> Optional[Anomalia]:
        """
        Comboiamento (bunching): dois veiculos da mesma linha rodando colados.

        Converte a distancia ao veiculo da frente em headway temporal usando a
        velocidade comercial da linha e compara com o headway planejado.
        """
        if len(frota) < 2 or linha.headway_planejado_s <= 0:
            return None

        a_frente = [outro for outro in frota
                    if outro.vehicle_id != tel.vehicle_id
                    and 0 < (outro.position_m - tel.position_m)]
        if not a_frente:
            return None

        proximo = min(a_frente, key=lambda t: t.position_m - tel.position_m)
        distancia = proximo.position_m - tel.position_m
        headway_real = distancia / max(1.0, VELOCIDADE_PROJETO_KMH / 3.6)
        if headway_real >= linha.headway_planejado_s * FATOR_BUNCHING:
            return None

        return Anomalia(
            codigo="COMBOIAMENTO",
            severidade="ATENCAO",
            titulo="Comboiamento de veiculos",
            detalhe=(f"Intervalo de {headway_real / 60:.1f} min ate "
                     f"{pseudonimizar(proximo.vehicle_id)}, contra "
                     f"{linha.headway_planejado_s / 60:.0f} min planejados "
                     f"({distancia:.0f} m de separacao)."),
            vehicle_id=tel.vehicle_id, route_id=tel.route_id,
            detectado_em=datetime.now(timezone.utc).isoformat())

    # --------------------------------------------------------- SUMARIZACAO
    def sumarizar(self, estado: Sequence[Telemetria], linhas: Dict[str, Linha],
                  anomalias: Sequence[Anomalia]) -> Dict[str, Any]:
        """Sintese analitica da operacao: por linha e global."""
        por_linha: Dict[str, List[Telemetria]] = defaultdict(list)
        for tel in estado:
            por_linha[tel.route_id].append(tel)

        anomalias_por_linha: Dict[str, int] = defaultdict(int)
        for anomalia in anomalias:
            anomalias_por_linha[anomalia.route_id] += 1

        resumo_linhas: List[Dict[str, Any]] = []
        for route_id, veiculos in sorted(por_linha.items()):
            linha = linhas.get(route_id)
            ocupacoes = [v.occupancy_rate for v in veiculos]
            desvios = [v.schedule_deviation_s for v in veiculos]
            resumo_linhas.append({
                "route_id": route_id,
                "nome": linha.nome if linha else route_id,
                "veiculos": len(veiculos),
                "ocupacao_media": round(statistics.fmean(ocupacoes), 3) if ocupacoes else 0.0,
                "ocupacao_maxima": round(max(ocupacoes), 3) if ocupacoes else 0.0,
                "desvio_medio_s": round(statistics.fmean(desvios), 1) if desvios else 0.0,
                "velocidade_media_kmh": round(
                    statistics.fmean([v.speed_kmh for v in veiculos]), 1) if veiculos else 0.0,
                "anomalias": anomalias_por_linha.get(route_id, 0),
            })

        todas_ocupacoes = [v.occupancy_rate for v in estado]
        return {
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "linhas": resumo_linhas,
            "global": {
                "veiculos_em_operacao": len(estado),
                "ocupacao_media": round(statistics.fmean(todas_ocupacoes), 3) if todas_ocupacoes else 0.0,
                "veiculos_acima_do_conforto": sum(1 for v in estado if v.occupancy_alert),
                "anomalias_ativas": len(anomalias),
            },
        }


# =============================================================================
# 7. INDICADORES - SECAO 6 DO DOCUMENTO DE VISAO
# =============================================================================

class Indicadores:
    """
    Os cinco indicadores da Secao 6, calculados sobre o historico real de
    operacao. Cada um expoe a definicao operacional junto do valor, para que o
    painel possa explicar o numero em vez de apenas exibi-lo.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chegadas: Deque[Chegada] = deque(maxlen=TAMANHO_HISTORICO_CHEGADAS)
        self._viagens_concluidas: Deque[float] = deque(maxlen=200)
        self._ocupacao_por_hora: Dict[int, List[float]] = defaultdict(list)

    def registrar_chegada(self, chegada: Chegada) -> None:
        with self._lock:
            self._chegadas.append(chegada)

    def registrar_viagem(self, duracao_s: float) -> None:
        with self._lock:
            self._viagens_concluidas.append(duracao_s)

    def registrar_ocupacao(self, taxa: float, hora: int) -> None:
        with self._lock:
            amostras = self._ocupacao_por_hora[hora]
            amostras.append(taxa)
            if len(amostras) > 400:
                del amostras[:200]

    def chegadas_recentes(self, limite: int = 40,
                          vehicle_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            itens = list(self._chegadas)
        if vehicle_id:
            itens = [c for c in itens if c.vehicle_id == vehicle_id]
        return [c.to_dict() for c in reversed(itens[-limite:])]

    def instantaneo(self, veiculos_cadastrados: int, veiculos_ativos: int,
                    headway_medio_s: float) -> Dict[str, Any]:
        with self._lock:
            chegadas = list(self._chegadas)
            viagens = list(self._viagens_concluidas)
            ocupacao_hora = {h: list(v) for h, v in self._ocupacao_por_hora.items()}

        pontuais = [c for c in chegadas if abs(c.desvio_s) <= TOLERANCIA_PONTUALIDADE_S]
        pontualidade = (len(pontuais) / len(chegadas)) if chegadas else None
        desvio_medio = statistics.fmean([c.desvio_s for c in chegadas]) if chegadas else None

        return {
            "pontualidade": {
                "titulo": "Pontualidade",
                "definicao": (f"Proporcao de chegadas dentro de "
                              f"{int(TOLERANCIA_PONTUALIDADE_S)} s do horario planejado."),
                "valor": round(pontualidade, 3) if pontualidade is not None else None,
                "formato": "percentual",
                "detalhe": (f"{len(pontuais)} de {len(chegadas)} chegadas no prazo"
                            if chegadas else "aguardando primeiras chegadas"),
                "desvio_medio_s": round(desvio_medio, 1) if desvio_medio is not None else None,
            },
            "tempo_espera": {
                "titulo": "Tempo de espera",
                "definicao": "Espera media no ponto, estimada como metade do intervalo entre veiculos.",
                "valor": round(headway_medio_s / 2.0, 1) if headway_medio_s > 0 else None,
                "formato": "segundos",
                "detalhe": (f"intervalo medio entre veiculos de {headway_medio_s / 60:.1f} min"
                            if headway_medio_s > 0 else "frota insuficiente para calcular"),
            },
            "ocupacao_por_horario": {
                "titulo": "Ocupacao por horario",
                "definicao": "Distribuicao da lotacao media ao longo das faixas horarias.",
                "valor": {str(h): round(statistics.fmean(v), 3)
                          for h, v in sorted(ocupacao_hora.items()) if v},
                "formato": "serie",
                "detalhe": f"{sum(len(v) for v in ocupacao_hora.values())} leituras agregadas",
            },
            "duracao_viagem": {
                "titulo": "Duracao da viagem",
                "definicao": "Tempo medio para cumprimento integral do itinerario.",
                "valor": round(statistics.fmean(viagens), 1) if viagens else None,
                "formato": "segundos",
                "detalhe": (f"{len(viagens)} viagens concluidas"
                            if viagens else "nenhuma viagem concluida ainda"),
            },
            "disponibilidade_frota": {
                "titulo": "Disponibilidade da frota",
                "definicao": "Veiculos transmitindo em relacao ao total planejado.",
                "valor": (round(veiculos_ativos / veiculos_cadastrados, 3)
                          if veiculos_cadastrados else None),
                "formato": "percentual",
                "detalhe": f"{veiculos_ativos} de {veiculos_cadastrados} veiculos ativos",
            },
        }


# =============================================================================
# 8. HERMES - COPILOTO DO GESTOR
# =============================================================================

class Hermes:
    """
    Traduz anomalias e indicadores em avisos acionaveis e no resumo de turno.

    Secao 5 do documento de visao: a decisao e do gestor humano. Todo aviso
    carrega o campo `vinculante: false` e e redigido como sugestao, nunca como
    ordem de remanejamento.
    """

    SUGESTOES: Dict[str, str] = {
        "LOTACAO_CRITICA": ("Avaliar reforco na linha ou antecipacao do proximo veiculo; "
                            "verificar se ha evento gerando demanda atipica."),
        "ATRASO_OPERACIONAL": ("Checar condicoes da via no trecho atual; considerar ajuste de "
                               "intervalo para nao propagar o atraso a frota."),
        "COMBOIAMENTO": ("Considerar retencao breve do veiculo de tras no ponto para "
                         "restabelecer o intervalo regular da linha."),
    }

    def avisos(self, anomalias: Sequence[Anomalia]) -> List[Dict[str, Any]]:
        ordem = {"CRITICO": 0, "ATENCAO": 1, "INFO": 2}
        ordenadas = sorted(anomalias, key=lambda a: (ordem.get(a.severidade, 3), a.vehicle_id))
        return [{
            "codigo": a.codigo,
            "severidade": a.severidade,
            "titulo": a.titulo,
            "detalhe": a.detalhe,
            "vehicle_id": a.vehicle_id,
            "vehicle_id_publico": pseudonimizar(a.vehicle_id),
            "route_id": a.route_id,
            "sugestao": self.SUGESTOES.get(a.codigo, "Acompanhar a evolucao do indicador."),
            "vinculante": False,
            "detectado_em": a.detectado_em,
        } for a in ordenadas]

    def resumo_de_turno(self, sintese: Dict[str, Any], kpis: Dict[str, Any],
                        anomalias: Sequence[Anomalia]) -> Dict[str, Any]:
        """Resumo executivo em linguagem natural, montado a partir dos numeros."""
        glob = sintese.get("global", {})
        frases: List[str] = []

        veiculos = glob.get("veiculos_em_operacao", 0)
        frases.append(f"{veiculos} veiculo(s) em operacao no momento.")

        pontualidade = kpis.get("pontualidade", {}).get("valor")
        if pontualidade is not None:
            qualificador = ("dentro do esperado" if pontualidade >= 0.8
                            else "abaixo do desejavel" if pontualidade >= 0.6
                            else "critica")
            frases.append(f"Pontualidade de {pontualidade * 100:.0f}%, {qualificador}.")
        else:
            frases.append("Pontualidade ainda sem amostras suficientes.")

        acima = glob.get("veiculos_acima_do_conforto", 0)
        if acima:
            frases.append(f"{acima} veiculo(s) acima do limite de conforto de 70%.")
        else:
            frases.append("Nenhum veiculo acima do limite de conforto.")

        contagem: Dict[str, int] = defaultdict(int)
        for anomalia in anomalias:
            contagem[anomalia.codigo] += 1
        if contagem:
            partes = ", ".join(f"{n}x {c.replace('_', ' ').lower()}" for c, n in sorted(contagem.items()))
            frases.append(f"Anomalias ativas: {partes}.")
        else:
            frases.append("Nenhuma anomalia ativa.")

        linhas_criticas = sorted(sintese.get("linhas", []),
                                 key=lambda l: l.get("desvio_medio_s", 0.0), reverse=True)
        if linhas_criticas and linhas_criticas[0].get("desvio_medio_s", 0) > 60:
            pior = linhas_criticas[0]
            frases.append(f"Maior desvio medio na {pior['nome']} "
                          f"({pior['desvio_medio_s'] / 60:.1f} min).")

        return {
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "texto": " ".join(frases),
            "itens": frases,
            "vinculante": False,
            "observacao": ("Resumo gerado por regras deterministicas sobre a telemetria "
                           "do periodo. A decisao operacional permanece com o gestor."),
        }


# =============================================================================
# 9. REPOSITORIO THREAD-SAFE
# =============================================================================

def alerta_id(vehicle_id: str, codigo: str) -> str:
    """Identificador estavel de um alerta (mesmo veiculo + mesmo tipo)."""
    return hashlib.sha1(f"{vehicle_id}|{codigo}".encode("utf-8")).hexdigest()[:10]


class Repositorio:
    """
    Estado compartilhado entre as threads de simulacao e as do servidor HTTP.
    Todo acesso a colecao mutavel e serializado por lock. Metodos que disparam
    efeitos externos (encerrar simulador) fazem isso FORA da secao critica, para
    nao segurar o lock durante operacoes de I/O.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._linhas: Dict[str, Linha] = {}
        self._veiculos: Dict[str, Veiculo] = {}
        self._telemetria: Dict[str, Telemetria] = {}
        self._anomalias: Dict[str, List[Anomalia]] = {}
        self._trilhas: Dict[str, Deque[Tuple[float, float, float]]] = {}
        self._log: Deque[Dict[str, Any]] = deque(maxlen=TAMANHO_BUFFER_LOG)
        self._simuladores: Dict[str, "CentralTelemetria"] = {}
        self._assinantes: List["queue.Queue[str]"] = []
        self._pacotes_recebidos: int = 0
        self._pacotes_rejeitados: int = 0
        self._decisoes: Dict[str, Dict[str, str]] = {}
        self._log_decisoes: Deque[Dict[str, Any]] = deque(maxlen=100)
        self._atendimentos: Dict[str, float] = {}

        self.historico_trechos = HistoricoTrechos()
        self.indicadores = Indicadores()
        self.kharon = Kharon(self.historico_trechos)
        self.hermes = Hermes()

    # ------------------------------------------------------------- LINHAS
    def listar_linhas(self) -> List[Linha]:
        with self._lock:
            return list(self._linhas.values())

    def obter_linha(self, linha_id: str) -> Optional[Linha]:
        with self._lock:
            return self._linhas.get(linha_id)

    def salvar_linha(self, linha: Linha) -> None:
        with self._lock:
            self._linhas[linha.id] = linha

    def remover_linha(self, linha_id: str) -> bool:
        with self._lock:
            if linha_id not in self._linhas:
                return False
            del self._linhas[linha_id]
            afetados = [v.id for v in self._veiculos.values() if v.linha_id == linha_id]
        for vid in afetados:
            self.remover_veiculo(vid)
        return True

    # ------------------------------------------------------------ VEICULOS
    def listar_veiculos(self) -> List[Veiculo]:
        with self._lock:
            return list(self._veiculos.values())

    def obter_veiculo(self, veiculo_id: str) -> Optional[Veiculo]:
        with self._lock:
            return self._veiculos.get(veiculo_id)

    def salvar_veiculo(self, veiculo: Veiculo) -> None:
        with self._lock:
            self._veiculos[veiculo.id] = veiculo

    def remover_veiculo(self, veiculo_id: str) -> bool:
        with self._lock:
            simulador = self._simuladores.pop(veiculo_id, None)
            existia = self._veiculos.pop(veiculo_id, None) is not None
            self._telemetria.pop(veiculo_id, None)
            self._anomalias.pop(veiculo_id, None)
            self._trilhas.pop(veiculo_id, None)
        if simulador is not None:
            simulador.encerrar()
        return existia

    # --------------------------------------------------------- SIMULADORES
    def registrar_simulador(self, simulador: "CentralTelemetria") -> None:
        with self._lock:
            self._simuladores[simulador.veiculo.id] = simulador

    def simulador_de(self, veiculo_id: str) -> Optional["CentralTelemetria"]:
        with self._lock:
            return self._simuladores.get(veiculo_id)

    def encerrar_simuladores(self) -> None:
        with self._lock:
            ativos = list(self._simuladores.values())
            self._simuladores.clear()
        for sim in ativos:
            sim.encerrar()

    # ---------------------------------------------------------- TELEMETRIA
    def ingerir(self, payload: Dict[str, Any]) -> Telemetria:
        """Valida (Aegis), persiste, analisa (Kharon) e notifica assinantes SSE."""
        try:
            telemetria = validar_telemetria(payload)
        except ErroValidacao:
            with self._lock:
                self._pacotes_rejeitados += 1
            raise

        linha = self.obter_linha(telemetria.route_id)
        with self._lock:
            self._telemetria[telemetria.vehicle_id] = telemetria
            self._pacotes_recebidos += 1
            trilha = self._trilhas.setdefault(
                telemetria.vehicle_id, deque(maxlen=TAMANHO_HISTORICO_POSICOES))
            trilha.append((telemetria.latitude, telemetria.longitude, time.time()))
            self._log.appendleft({
                "recebido_em": datetime.now().strftime("%H:%M:%S"),
                "payload": mascarar_pacote(payload),
            })
            frota_da_linha = [t for t in self._telemetria.values()
                              if t.route_id == telemetria.route_id]

        if linha is not None:
            anomalias = self.kharon.analisar(telemetria, linha, frota_da_linha)
            with self._lock:
                self._anomalias[telemetria.vehicle_id] = anomalias

        self.indicadores.registrar_ocupacao(telemetria.occupancy_rate, datetime.now().hour)
        self._publicar({"tipo": "telemetria", "vehicle_id": telemetria.vehicle_id})
        return telemetria

    def telemetria_atual(self) -> List[Telemetria]:
        with self._lock:
            return list(self._telemetria.values())

    def anomalias_ativas(self) -> List[Anomalia]:
        with self._lock:
            return [a for lista in self._anomalias.values() for a in lista]

    def anomalias_de(self, veiculo_id: str) -> List[Anomalia]:
        with self._lock:
            return list(self._anomalias.get(veiculo_id, []))

    def trilha_de(self, veiculo_id: str, limite: int = 400) -> List[List[float]]:
        with self._lock:
            trilha = list(self._trilhas.get(veiculo_id, []))
        return [[round(lat, 6), round(lon, 6)] for lat, lon, _ in trilha[-limite:]]

    def log_recente(self, limite: int = 12) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._log)[:limite]

    def estatisticas_ingestao(self) -> Dict[str, int]:
        with self._lock:
            return {"recebidos": self._pacotes_recebidos, "rejeitados": self._pacotes_rejeitados}

    # ------------------------------------------------------- HEADWAY / KPI
    def headway_medio_s(self) -> float:
        """Intervalo medio real entre veiculos consecutivos, em todas as linhas."""
        with self._lock:
            estado = list(self._telemetria.values())
            linhas = dict(self._linhas)

        intervalos: List[float] = []
        por_linha: Dict[str, List[Telemetria]] = defaultdict(list)
        for tel in estado:
            por_linha[tel.route_id].append(tel)

        for route_id, veiculos in por_linha.items():
            linha = linhas.get(route_id)
            if linha is None or len(veiculos) < 2:
                continue
            ordenados = sorted(veiculos, key=lambda t: t.position_m)
            for anterior, seguinte in zip(ordenados, ordenados[1:]):
                distancia = seguinte.position_m - anterior.position_m
                intervalos.append(distancia / max(1.0, VELOCIDADE_PROJETO_KMH / 3.6))
            # fecha o ciclo: do ultimo de volta ao primeiro
            volta = linha.extensao_m - (ordenados[-1].position_m - ordenados[0].position_m)
            intervalos.append(max(0.0, volta) / max(1.0, VELOCIDADE_PROJETO_KMH / 3.6))

        return statistics.fmean(intervalos) if intervalos else 0.0

    def kpis(self) -> Dict[str, Any]:
        with self._lock:
            cadastrados = len(self._veiculos)
            ativos = len(self._telemetria)
        return self.indicadores.instantaneo(cadastrados, ativos, self.headway_medio_s())

    def sintese(self) -> Dict[str, Any]:
        with self._lock:
            estado = list(self._telemetria.values())
            linhas = dict(self._linhas)
        return self.kharon.sumarizar(estado, linhas, self.anomalias_ativas())

    # ------------------------------------------------- ALERTAS E DECISOES
    def alertas(self) -> List[Dict[str, Any]]:
        """
        Alertas que pedem decisao do gestor: anomalias detectadas pelo Kharon e
        pedidos de rampa feitos pelos passageiros. Cada um tem um id estavel.
        """
        with self._lock:
            telemetria = list(self._telemetria.values())
            anomalias = [a for lista in self._anomalias.values() for a in lista]
            decisoes = dict(self._decisoes)

        saida: List[Dict[str, Any]] = []
        for a in anomalias:
            aid = alerta_id(a.vehicle_id, a.codigo)
            saida.append({
                "id": aid, "tipo": "ANOMALIA", "codigo": a.codigo,
                "severidade": a.severidade, "titulo": a.titulo, "detalhe": a.detalhe,
                "vehicle_id": a.vehicle_id, "vehicle_id_publico": pseudonimizar(a.vehicle_id),
                "route_id": a.route_id,
                "sugestao": Hermes.SUGESTOES.get(a.codigo, "Acompanhar a evolucao do indicador."),
                "status": decisoes.get(aid, {}).get("acao", "pendente"),
            })
        for t in telemetria:
            if t.accessibility_button:
                aid = alerta_id(t.vehicle_id, "PEDIDO_RAMPA")
                saida.append({
                    "id": aid, "tipo": "RAMPA", "codigo": "PEDIDO_RAMPA",
                    "severidade": "ATENCAO", "titulo": "Pedido de rampa",
                    "detalhe": f"Passageiro pediu rampa no ponto {t.next_stop}.",
                    "vehicle_id": t.vehicle_id, "vehicle_id_publico": pseudonimizar(t.vehicle_id),
                    "route_id": t.route_id,
                    "sugestao": "Confirmar o atendimento quando o veiculo chegar ao ponto.",
                    "status": decisoes.get(aid, {}).get("acao", "pendente"),
                })
        ordem = {"CRITICO": 0, "ATENCAO": 1, "INFO": 2}
        saida.sort(key=lambda x: (ordem.get(x["severidade"], 3), x["vehicle_id"]))
        return saida

    def decidir(self, aid: str, acao: str) -> Dict[str, Any]:
        """Registra a decisao do gestor. A IA sugere; quem decide e o gestor."""
        alvo = next((a for a in self.alertas() if a["id"] == aid), None)
        if alvo is None:
            raise KeyError(aid)
        if acao == "aceitar" and alvo["tipo"] == "RAMPA":
            self.confirmar_atendimento(alvo["vehicle_id"])
        registro = {
            "alerta": aid, "titulo": alvo["titulo"],
            "vehicle_id_publico": alvo["vehicle_id_publico"], "acao": acao,
            "instante": datetime.now().strftime("%H:%M:%S"),
        }
        with self._lock:
            self._decisoes[aid] = {"acao": acao}
            self._log_decisoes.appendleft(registro)
        self._publicar({"tipo": "decisao", "alerta": aid})
        return registro

    def log_decisoes(self, limite: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._log_decisoes)[:limite]

    def confirmar_atendimento(self, vehicle_id: str) -> None:
        simulador = self.simulador_de(vehicle_id)
        if simulador is not None:
            simulador.atender_acessibilidade()
        with self._lock:
            self._atendimentos[vehicle_id] = time.time()

    def atendimento_de(self, vehicle_id: str, validade_s: float = 600.0) -> Optional[str]:
        """Usado pelo app do passageiro: mostra que o motorista foi avisado."""
        with self._lock:
            instante = self._atendimentos.get(vehicle_id)
        if instante is not None and time.time() - instante <= validade_s:
            return "confirmado"
        return None

    # ------------------------------------------------------------ SSE
    def assinar(self) -> "queue.Queue[str]":
        fila: "queue.Queue[str]" = queue.Queue(maxsize=50)
        with self._lock:
            self._assinantes.append(fila)
        return fila

    def cancelar_assinatura(self, fila: "queue.Queue[str]") -> None:
        with self._lock:
            if fila in self._assinantes:
                self._assinantes.remove(fila)

    def _publicar(self, evento: Dict[str, Any]) -> None:
        mensagem = json.dumps(evento, ensure_ascii=False)
        with self._lock:
            filas = list(self._assinantes)
        for fila in filas:
            try:
                fila.put_nowait(mensagem)
            except queue.Full:
                pass  # assinante lento perde o tick; o proximo o realinha


REPO = Repositorio()


# =============================================================================
# 10. VULCAN - CENTRAL DE TELEMETRIA EMBARCADA (uma thread daemon por veiculo)
# =============================================================================

class CentralTelemetria(threading.Thread):
    """
    Emula o computador de bordo de um onibus.

    Modelo fisico:
      - avanco longitudinal sobre o tracado, com suavizacao de velocidade;
      - em parada, velocidade zero libera a porta e o fluxo estocastico de
        passageiros; em transito a porta permanece fechada;
      - tempo de permanencia proporcional ao volume de embarque/desembarque;
      - temperatura interna sobe com porta aberta e cai com climatizacao ativa;
      - demanda de embarque modulada pela faixa horaria, para que a lotacao
        critica emerja do fluxo de passageiros em vez de ser sorteada.

    A cada ciclo publica no gateway HTTP via POST, como faria um modulo celular
    embarcado. Falha de rede nao descarta o pacote: ele vai para um buffer local
    de store-and-forward e e reenviado no ciclo seguinte.
    """

    def __init__(self, veiculo: Veiculo, linha: Linha, repositorio: Repositorio,
                 base_url: str) -> None:
        super().__init__(name=f"IoT-{veiculo.id}", daemon=True)
        self.veiculo = veiculo
        self.linha = linha
        self._repo = repositorio
        self._base_url = base_url
        self._parar = threading.Event()
        self._lock = threading.Lock()

        self._rota = linha.rota
        self._acumulado = distancias_acumuladas(self._rota)
        self._extensao = self._acumulado[-1] if self._acumulado else 0.0

        self._s = 0.0
        self._odometro = 0.0
        self._idx_parada = 0
        self._dwell_restante_s = 0.0
        self._passageiros = max(2, int(veiculo.capacidade * random.uniform(0.10, 0.30)))
        self._temperatura = round(random.uniform(22.0, 25.0), 1)
        self._portas = "CLOSED"
        self._velocidade = 0.0
        self._acessibilidade_solicitada = False
        self._pedido_parada_idx: Optional[int] = None
        self._tempo_viagem_s = 0.0
        self._trip_id = self._novo_trip_id()
        self._amostras_trecho: List[float] = []
        self._distancia_trecho_m = 0.0
        self._congestionamento_restante_s = 0.0
        self._embarcados = 0
        self._desembarcados = 0
        self._buffer_offline: Deque[Dict[str, Any]] = deque(maxlen=TAMANHO_BUFFER_OFFLINE)

    # ----------------------------------------------------------- auxiliares
    def _novo_trip_id(self) -> str:
        return f"TRIP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self.veiculo.id[-3:]}"

    def _parada(self, indice: int) -> Optional[Parada]:
        if not self.linha.paradas:
            return None
        return self.linha.paradas[max(0, min(indice, len(self.linha.paradas) - 1))]

    def atender_acessibilidade(self) -> None:
        """Motorista confirmou o atendimento: encerra o pedido ativo."""
        with self._lock:
            self._acessibilidade_solicitada = False
            self._pedido_parada_idx = None

    def solicitar_acessibilidade(self) -> None:
        """
        Acionado pelo passageiro via API. E atendido no desembarque da parada
        seguinte: se o veiculo ja esta parado (portas abertas), a parada em curso
        nao conta mais e o pedido vale para a proxima.
        """
        with self._lock:
            self._acessibilidade_solicitada = True
            self._pedido_parada_idx = self._idx_parada + (1 if self._dwell_restante_s > 0.0 else 0)

    @staticmethod
    def _fator_demanda() -> float:
        """Demanda relativa de embarque por faixa horaria (picos manha e fim de tarde)."""
        hora = datetime.now().hour
        if hora in (6, 7, 8, 17, 18, 19):
            return 1.9
        if hora in (9, 10, 11, 12, 16, 20):
            return 1.1
        if 0 <= hora <= 4:
            return 0.3
        return 0.7

    # --------------------------------------------------------- ciclo de vida
    def encerrar(self) -> None:
        self._parar.set()

    def run(self) -> None:
        # Partida escalonada: evita rajada simultanea de todos os veiculos.
        self._parar.wait(random.uniform(0.2, 1.6))
        anterior = time.monotonic()
        while not self._parar.is_set():
            intervalo = random.uniform(INTERVALO_MIN_S, INTERVALO_MAX_S)
            agora = time.monotonic()
            dt_real = min(agora - anterior, INTERVALO_MAX_S * 2)
            anterior = agora
            pacote = self.passo(dt_real * FATOR_TEMPO)
            self._transmitir(pacote.to_dict())
            self._parar.wait(intervalo)

    # ------------------------------------------------------------- dinamica
    def passo(self, dt_s: float) -> Telemetria:
        """Avanca a simulacao em `dt_s` segundos de tempo simulado."""
        with self._lock:
            capacidade = self.veiculo.capacidade
            self._tempo_viagem_s += dt_s
            parada_alvo = self._parada(self._idx_parada)
            alvo_m = parada_alvo.posicao_m if parada_alvo else self._extensao
            em_parada = False
            chegada_registrada: Optional[Chegada] = None

            if self._dwell_restante_s > 0.0:
                em_parada = True
                self._velocidade = 0.0
                self._portas = "OPEN"
                self._temperatura += 0.35 * (dt_s / 10.0)
                self._dwell_restante_s -= dt_s
                if self._dwell_restante_s <= 0.0:
                    self._dwell_restante_s = 0.0
                    self._concluir_parada()
            else:
                self._portas = "CLOSED"
                # o pedido de rampa persiste durante todo o trajeto ate o proximo
                # desembarque (ou ate o gestor atender); so entao e consumido

                # Retencao de via: congestionamento, obra ou ocorrencia. E a CAUSA
                # que se sorteia, nunca o diagnostico. O atraso resultante e
                # medido pelo desvio de horario e so entao Kharon o classifica
                # como anomalia - do contrario a deteccao seria encenacao.
                if self._congestionamento_restante_s > 0.0:
                    self._congestionamento_restante_s -= dt_s
                elif random.random() < probabilidade_no_intervalo(
                        TAXA_CONGESTIONAMENTO_POR_S, dt_s):
                    self._congestionamento_restante_s = random.uniform(
                        CONGESTIONAMENTO_MIN_S, CONGESTIONAMENTO_MAX_S)

                if self._congestionamento_restante_s > 0.0:
                    alvo_velocidade = random.uniform(0.0, 9.0)
                else:
                    # Perfil de trafego urbano com suavizacao (evita saltos irreais).
                    alvo_velocidade = random.uniform(16.0, 38.0)
                    if random.random() < probabilidade_no_intervalo(
                            TAXA_RETENCAO_PONTUAL_POR_S, dt_s):
                        alvo_velocidade = random.uniform(0.0, 7.0)

                # Suavizacao exponencial com constante de tempo fixa (~6 s): a
                # inercia do veiculo e a mesma qualquer que seja o passo.
                peso = 1.0 - math.exp(-dt_s / 6.0)
                self._velocidade = round(
                    max(0.0, self._velocidade * (1.0 - peso) + alvo_velocidade * peso), 1)

                avanco = (self._velocidade / 3.6) * dt_s
                self._s += avanco
                self._odometro += avanco
                self._distancia_trecho_m += avanco
                if self._velocidade > 0.5:
                    self._amostras_trecho.append(self._velocidade)
                self._temperatura -= 0.18 * (dt_s / 10.0) if self._temperatura > 22.5 else -0.05

                if self._s >= alvo_m - RAIO_CHEGADA_PARADA_M:
                    self._s = alvo_m
                    chegada_registrada = self._iniciar_parada()
                    em_parada = True
                elif self._s >= self._extensao:
                    self._concluir_viagem()

            self._temperatura = round(max(19.0, min(32.0, self._temperatura)), 1)
            ocupacao = round(self._passageiros / capacidade, 3) if capacidade else 0.0

            # Regra independente da deteccao de anomalia: avaliada em TODO ciclo.
            alerta_ocupacao = ocupacao > LIMITE_ALERTA_OCUPACAO

            parada_atual = self._parada(self._idx_parada - 1) if self._idx_parada > 0 else self._parada(0)
            proxima = self._parada(self._idx_parada)
            distancia_restante = max(0.0, alvo_m - self._s)

            # Desvio medido contra o horario planejado para a POSICAO atual, nao
            # para o proximo ponto: a comparacao precisa ser entre grandezas do
            # mesmo instante do itinerario.
            desvio_s = self._tempo_viagem_s - self.linha.tempo_planejado_em(self._s)

            media_trecho, _ = self._repo.historico_trechos.media(self.linha.id, self._idx_parada)
            referencia = media_trecho if media_trecho > 1.0 else VELOCIDADE_PROJETO_KMH

            lat, lon = posicao_em(self._rota, self._acumulado, self._s)
            telemetria = Telemetria(
                timestamp=datetime.now(timezone.utc).isoformat(),
                vehicle_id=self.veiculo.id,
                route_id=self.linha.id,
                trip_id=self._trip_id,
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                speed_kmh=float(self._velocidade),
                door_status=self._portas,
                passenger_count=int(self._passageiros),
                passenger_capacity=int(capacidade),
                occupancy_rate=float(ocupacao),
                occupancy_alert=bool(alerta_ocupacao),
                internal_temperature_c=float(self._temperatura),
                accessibility_button=bool(self._acessibilidade_solicitada),
                accessible_vehicle=bool(self.veiculo.acessivel),
                is_at_stop=bool(em_parada),
                current_stop=parada_atual.nome if parada_atual else "-",
                next_stop=proxima.nome if proxima else "-",
                next_stop_index=int(self._idx_parada),
                distance_next_stop_m=round(distancia_restante, 1),
                position_m=round(self._s, 1),
                route_progress=round(min(1.0, self._s / self._extensao), 4) if self._extensao else 0.0,
                odometer_m=round(self._odometro, 1),
                trip_elapsed_s=round(self._tempo_viagem_s, 1),
                schedule_deviation_s=round(desvio_s, 1),
                segment_avg_speed_kmh=round(referencia, 1),
            )

        if chegada_registrada is not None:
            self._repo.indicadores.registrar_chegada(chegada_registrada)
        return telemetria

    def _iniciar_parada(self) -> Optional[Chegada]:
        """Chegada ao ponto: consolida o trecho, move passageiros e abre as portas."""
        capacidade = self.veiculo.capacidade
        parada = self._parada(self._idx_parada)

        # Um trecho curto demais (caso tipico: a parada de origem, na posicao
        # zero) nao produz amostra representativa e contaminaria o ETA daquele
        # ponto com uma velocidade artificialmente baixa.
        if self._amostras_trecho and self._distancia_trecho_m >= DISTANCIA_MINIMA_TRECHO_M:
            media = statistics.fmean(self._amostras_trecho)
            self._repo.historico_trechos.registrar(self.linha.id, self._idx_parada, media)
        self._amostras_trecho = []
        self._distancia_trecho_m = 0.0

        demanda = self._fator_demanda()
        self._desembarcados = random.randint(0, max(1, int(self._passageiros * 0.35)))
        espaco = max(0, capacidade - (self._passageiros - self._desembarcados))
        candidatos = int(random.expovariate(1 / max(1.0, 5.0 * demanda)))
        self._embarcados = min(candidatos, espaco + 6)  # +6: passageiros em pe acima do nominal
        self._passageiros = max(0, self._passageiros - self._desembarcados + self._embarcados)

        movimento = self._desembarcados + self._embarcados
        self._dwell_restante_s = min(DWELL_MAX_S, DWELL_MIN_S + movimento * 0.9)
        self._velocidade = 0.0
        self._portas = "OPEN"

        if parada is None:
            return None
        return Chegada(
            vehicle_id=self.veiculo.id,
            route_id=self.linha.id,
            stop_id=parada.id,
            stop_name=parada.nome,
            instante=datetime.now(timezone.utc).isoformat(),
            desvio_s=round(self._tempo_viagem_s - parada.chegada_planejada_s, 1),
            ocupacao=round(self._passageiros / capacidade, 3) if capacidade else 0.0,
            passageiros_embarcados=self._embarcados,
            passageiros_desembarcados=self._desembarcados,
        )

    def _concluir_parada(self) -> None:
        # so atende o pedido se ele era para esta parada (e nao para a seguinte)
        if self._pedido_parada_idx == self._idx_parada:
            self._acessibilidade_solicitada = False
            self._pedido_parada_idx = None
        self._idx_parada += 1
        if self._idx_parada >= len(self.linha.paradas):
            self._concluir_viagem()

    def _concluir_viagem(self) -> None:
        """Fim do itinerario: registra a duracao e reinicia a partir do terminal."""
        if self._tempo_viagem_s > 60.0:
            self._repo.indicadores.registrar_viagem(self._tempo_viagem_s)
        self._s = 0.0
        self._idx_parada = 0
        self._tempo_viagem_s = 0.0
        self._amostras_trecho = []
        self._distancia_trecho_m = 0.0
        self._congestionamento_restante_s = 0.0
        self._trip_id = self._novo_trip_id()

    # ---------------------------------------------------------- transmissao
    def _transmitir(self, pacote: Dict[str, Any]) -> None:
        """
        Store-and-forward: em falha de rede o pacote fica no buffer local e e
        reenviado no ciclo seguinte, na ordem original. Nenhuma leitura e
        descartada em silencio - comportamento esperado de um modulo embarcado.
        """
        self._buffer_offline.append(pacote)
        while self._buffer_offline:
            proximo = self._buffer_offline[0]
            if not self._enviar(proximo):
                return  # rede indisponivel: mantem a fila e tenta no proximo ciclo
            self._buffer_offline.popleft()

    def _enviar(self, pacote: Dict[str, Any]) -> bool:
        corpo = json.dumps(pacote).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/iot/telemetria",
                data=corpo,
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as exc:
            # 4xx e erro de contrato, nao de rede: reenviar nao resolve.
            return 400 <= exc.code < 500
        except (urllib.error.URLError, TimeoutError, OSError):
            return False


# =============================================================================
# 11. FABRICAS DE RECURSOS
# =============================================================================

def montar_paradas(rota: Sequence[Coordenada], prefixo: str,
                   nomes: Sequence[str]) -> List[Parada]:
    """
    Distribui as paradas ao longo do tracado e calcula o horario planejado de
    cada uma a partir da velocidade de projeto somada ao tempo medio de
    permanencia nos pontos anteriores. Esse horario e a referencia do KPI de
    pontualidade - sem ele, "atraso" nao teria contra o que ser medido.
    """
    quantidade = max(2, min(len(nomes), len(rota)))
    acumulado = distancias_acumuladas(rota)
    dwell_medio = (DWELL_MIN_S + DWELL_MAX_S) / 2.0
    velocidade_ms = VELOCIDADE_PROJETO_KMH / 3.6

    paradas: List[Parada] = []
    for i in range(quantidade):
        indice = round(i * (len(rota) - 1) / (quantidade - 1))
        lat, lon = rota[indice]
        posicao = acumulado[indice]
        planejado = posicao / velocidade_ms + i * dwell_medio
        paradas.append(Parada(
            id=f"{prefixo}-P{i:02d}",
            nome=nomes[i],
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            posicao_m=round(posicao, 1),
            chegada_planejada_s=round(planejado, 1)))
    return paradas


def nomes_genericos(quantidade: int) -> List[str]:
    nomes = ["Terminal de origem"]
    nomes += [f"Parada {i:02d}" for i in range(1, quantidade - 1)]
    nomes.append("Terminal de destino")
    return nomes


PALETA_LINHAS: List[str] = ["#38bdf8", "#a78bfa", "#f472b6", "#34d399",
                            "#fbbf24", "#fb7185", "#60a5fa", "#4ade80"]
COR_VALIDA = re.compile(r"^#[0-9a-fA-F]{6}$")


def proxima_cor_livre() -> str:
    """Primeira cor da paleta ainda nao usada por nenhuma linha (sem sorteio)."""
    usadas = {l.cor.lower() for l in REPO.listar_linhas()}
    for cor in PALETA_LINHAS:
        if cor.lower() not in usadas:
            return cor
    return PALETA_LINHAS[len(usadas) % len(PALETA_LINHAS)]


def _cor_ou_padrao(valor: Any) -> str:
    """Aceita apenas #RRGGBB; qualquer outra coisa cai na proxima cor livre."""
    texto = str(valor or "").strip()
    return texto if COR_VALIDA.match(texto) else proxima_cor_livre()


def criar_linha_do_payload(payload: Dict[str, Any], offline: bool) -> Linha:
    """Valida e materializa uma Linha vinda de POST /api/linhas."""
    nome = str(payload.get("nome") or "").strip()
    if not nome:
        raise ValueError("campo 'nome' e obrigatorio")

    brutas = payload.get("coordenadas") or []
    if not isinstance(brutas, list):
        raise ValueError("'coordenadas' deve ser uma lista de pares [lat, lon]")

    pontos: List[Coordenada] = []
    for item in brutas:
        try:
            lat, lon = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise ValueError("cada coordenada deve ser um par [latitude, longitude]")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"coordenada fora de faixa: {lat}, {lon}")
        pontos.append((lat, lon))

    if len(pontos) < 2:
        raise ValueError("informe ao menos 2 coordenadas para a rota")

    # Simulacao offline: o tracado e a malha local a partir dos pontos informados.
    rota, origem = resolver_tracado(pontos, fallback=pontos, offline=True)

    linha_id = str(payload.get("id") or f"LINHA-{int(time.time()) % 100000}")
    quantidade = max(2, min(int(payload.get("qtd_paradas", 6)), 40))
    headway = float(payload.get("headway_min", 10.0)) * 60.0

    return Linha(
        id=linha_id,
        nome=nome,
        rota=rota,
        paradas=montar_paradas(rota, linha_id.split("-")[-1], nomes_genericos(quantidade)),
        cor=_cor_ou_padrao(payload.get("cor")),
        origem_tracado=origem,
        headway_planejado_s=max(60.0, headway))


def criar_veiculo_do_payload(payload: Dict[str, Any], base_url: str) -> Veiculo:
    """Valida, registra e coloca em operacao um veiculo vindo de POST /api/veiculos."""
    linha_id = str(payload.get("linha_id") or "").strip()
    linha = REPO.obter_linha(linha_id)
    if linha is None:
        raise ValueError("linha_id inexistente")

    veiculo_id = str(payload.get("id") or f"BUS-{random.randint(100, 999)}").strip()
    if REPO.obter_veiculo(veiculo_id) is not None:
        raise ValueError("ja existe veiculo com este id")

    try:
        capacidade = int(payload.get("capacidade", 70))
    except (TypeError, ValueError):
        raise ValueError("capacidade deve ser um numero inteiro")
    if not 1 <= capacidade <= 300:
        raise ValueError("capacidade deve estar entre 1 e 300")

    veiculo = Veiculo(id=veiculo_id, linha_id=linha_id, capacidade=capacidade,
                      acessivel=bool(payload.get("acessivel", True)))
    REPO.salvar_veiculo(veiculo)
    iniciar_simulador(veiculo, linha, base_url)
    return veiculo


def iniciar_simulador(veiculo: Veiculo, linha: Linha, base_url: str) -> CentralTelemetria:
    simulador = CentralTelemetria(veiculo, linha, REPO, base_url)
    REPO.registrar_simulador(simulador)
    simulador.start()
    return simulador


# =============================================================================
# 12. IRIS - INTERFACE (PWA: passageiro + gestor)
# =============================================================================

MANIFEST = {
    "name": "MoveCidade",
    "short_name": "MoveCidade",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0b1220",
    "theme_color": "#0b1220",
    "description": "Mobilidade urbana em tempo real",
    "icons": [{
        "src": "/icone.svg",
        "sizes": "any",
        "type": "image/svg+xml",
        "purpose": "any maskable",
    }],
}

ICONE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
<rect width="192" height="192" rx="36" fill="#0b1220"/>
<rect x="46" y="38" width="100" height="98" rx="16" fill="#38bdf8"/>
<rect x="58" y="54" width="76" height="40" rx="8" fill="#0b1220"/>
<circle cx="70" cy="146" r="13" fill="#e2e8f0"/><circle cx="122" cy="146" r="13" fill="#e2e8f0"/>
</svg>"""

SERVICE_WORKER = """
const CACHE = 'movecidade-v2';
const ESTATICOS = ['/', '/manifest.json', '/icone.svg'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ESTATICOS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) =>
    Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Dados ao vivo nunca saem do cache: telemetria obsoleta e pior que ausente.
  if (url.pathname.startsWith('/api/')) return;
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
"""

# Paginas (passageiro.html e gestor.html) e vendor/ ficam em arquivos separados.

# 12b. PONTOS DE PARADA (CRUD do gestor)
# ---------------------------------------------------------------------------
def _veiculos_publicos() -> List[Dict[str, Any]]:
    """
    Posicao dos veiculos para o app do passageiro. Sem identificador real, sem
    contagem exata de passageiros e sem trip_id: apenas o necessario para ver o
    onibus no mapa e decidir se vale esperar.
    """
    linhas = {l.id: l for l in REPO.listar_linhas()}
    saida: List[Dict[str, Any]] = []
    for tel in REPO.telemetria_atual():
        linha = linhas.get(tel.route_id)
        saida.append({
            "vehicle_id_publico": pseudonimizar(tel.vehicle_id),
            "route_id": tel.route_id,
            "cor": linha.cor if linha else "#94a3b8",
            "latitude": tel.latitude,
            "longitude": tel.longitude,
            "proxima_parada": tel.next_stop,
            "lotacao": faixa_ocupacao(tel.occupancy_rate),
            "acessivel": tel.accessible_vehicle,
            "solicitacao_ativa": tel.accessibility_button,
            "atendimento": REPO.atendimento_de(tel.vehicle_id),
            "instante": tel.timestamp,
        })
    return saida


def recalcular_horarios(linha: Linha) -> None:
    """Horario planejado de cada ponto, na mesma regra usada em montar_paradas."""
    velocidade_ms = VELOCIDADE_PROJETO_KMH / 3.6
    dwell = (DWELL_MIN_S + DWELL_MAX_S) / 2.0
    for i, p in enumerate(linha.paradas):
        p.chegada_planejada_s = round(p.posicao_m / velocidade_ms + i * dwell, 1)


def _coordenada(payload: Dict[str, Any]) -> Coordenada:
    try:
        lat, lon = float(payload["latitude"]), float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("latitude e longitude sao obrigatorias")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordenada fora de faixa")
    return (lat, lon)


def _posicionar(linha: Linha, p: Parada, coord: Coordenada) -> None:
    acumulado = distancias_acumuladas(linha.rota)
    p.latitude, p.longitude = round(coord[0], 6), round(coord[1], 6)
    p.posicao_m = round(projetar_na_rota(linha.rota, acumulado, coord), 1)


def localizar_ponto(ponto_id: str) -> Optional[Tuple[Linha, Parada]]:
    for linha in REPO.listar_linhas():
        for p in linha.paradas:
            if p.id == ponto_id:
                return linha, p
    return None


def inserir_ponto(payload: Dict[str, Any]) -> Parada:
    linha = REPO.obter_linha(str(payload.get("linha_id") or ""))
    if linha is None:
        raise ValueError("linha_id inexistente")
    nome = str(payload.get("nome") or "").strip()
    if not nome:
        raise ValueError("nome e obrigatorio")
    coord = _coordenada(payload)

    base = linha.id.split("-")[-1]
    existentes = {p.id for p in linha.paradas}
    n = len(linha.paradas)
    pid = f"{base}-P{n:02d}"
    while pid in existentes:
        n += 1
        pid = f"{base}-P{n:02d}"

    p = Parada(id=pid, nome=nome, latitude=0.0, longitude=0.0,
               rampa=bool(payload.get("rampa")), piso_tatil=bool(payload.get("piso_tatil")))
    _posicionar(linha, p, coord)
    linha.paradas.append(p)
    linha.paradas.sort(key=lambda q: q.posicao_m)
    recalcular_horarios(linha)
    return p


def editar_ponto(ponto_id: str, payload: Dict[str, Any]) -> Parada:
    achado = localizar_ponto(ponto_id)
    if achado is None:
        raise KeyError(ponto_id)
    linha, p = achado
    if "nome" in payload:
        nome = str(payload.get("nome") or "").strip()
        if not nome:
            raise ValueError("nome nao pode ser vazio")
        p.nome = nome
    if "rampa" in payload:
        p.rampa = bool(payload["rampa"])
    if "piso_tatil" in payload:
        p.piso_tatil = bool(payload["piso_tatil"])
    if "latitude" in payload or "longitude" in payload:
        _posicionar(linha, p, _coordenada(payload))
        linha.paradas.sort(key=lambda q: q.posicao_m)
    recalcular_horarios(linha)
    return p


def remover_ponto(ponto_id: str) -> bool:
    achado = localizar_ponto(ponto_id)
    if achado is None:
        return False
    linha, p = achado
    if len(linha.paradas) <= 2:
        raise ValueError("a linha precisa manter ao menos 2 pontos")
    linha.paradas.remove(p)
    recalcular_horarios(linha)
    return True


def todos_os_pontos() -> List[Dict[str, Any]]:
    saida: List[Dict[str, Any]] = []
    for linha in REPO.listar_linhas():
        for p in linha.paradas:
            saida.append({
                "id": p.id, "nome": p.nome, "latitude": p.latitude, "longitude": p.longitude,
                "rampa": p.rampa, "piso_tatil": p.piso_tatil,
                "linha_id": linha.id, "linha_nome": linha.nome, "linha_cor": linha.cor,
            })
    return saida


def _definir_acessibilidade_inicial() -> None:
    """Dados de demonstracao: parte dos pontos com rampa e piso tatil."""
    for linha in REPO.listar_linhas():
        for i, p in enumerate(linha.paradas):
            p.rampa = (i % 2 == 0)
            p.piso_tatil = (i % 3 == 0)


# =============================================================================
# 13. GATEWAY HTTP
# =============================================================================

class Gateway(BaseHTTPRequestHandler):
    """
    Handler REST + SSE.

    Nao herda de SimpleHTTPRequestHandler de proposito: servir o diretorio de
    trabalho exporia arquivos locais sem necessidade alguma.
    """

    server_version = "MoveCidade-Gateway/2.0"
    protocol_version = "HTTP/1.1"
    offline: bool = False
    base_url: str = f"http://{HOST}:{PORTA_PADRAO}"

    # ---------------------------------------------------------- utilitarios
    def _enviar(self, corpo: bytes, tipo: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(corpo)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, dados: Any, status: int = 200) -> None:
        self._enviar(json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8", status)

    def _erro(self, mensagem: str, status: int) -> None:
        self._json({"erro": mensagem}, status)

    def _ler_json(self) -> Dict[str, Any]:
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if tamanho <= 0 or tamanho > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, OSError):
            return {}

    @staticmethod
    def _segmentos(caminho: str) -> List[str]:
        return [s for s in urlparse(caminho).path.split("/") if s]

    def _parametros(self) -> Dict[str, str]:
        consulta = urlparse(self.path).query
        saida: Dict[str, str] = {}
        for par in consulta.split("&"):
            if "=" in par:
                chave, _, valor = par.partition("=")
                saida[chave] = urllib.parse.unquote_plus(valor)
        return saida

    def _pagina(self, nome: str) -> None:
        """Entrega passageiro.html / gestor.html com o token do Mapbox injetado."""
        try:
            with open(os.path.join(APP_DIR, nome), "r", encoding="utf-8") as arq:
                conteudo = arq.read()
        except OSError:
            self._erro(f"pagina {nome} nao encontrada", 404); return
        self._enviar(conteudo.replace("__MAPBOX_TOKEN__", MAPBOX_TOKEN).encode("utf-8"),
                     "text/html; charset=utf-8")

    def _arquivo_vendor(self, nome: str) -> None:
        """Serve apenas arquivos da pasta vendor/ (sem sair do diretorio)."""
        if nome != os.path.basename(nome) or nome.startswith("."):
            self._erro("recurso nao encontrado", 404); return
        caminho = os.path.join(APP_DIR, "vendor", nome)
        tipo = "text/css; charset=utf-8" if nome.endswith(".css") else "application/javascript; charset=utf-8"
        try:
            with open(caminho, "rb") as arq:
                self._enviar(arq.read(), tipo)
        except OSError:
            self._erro("recurso nao encontrado", 404)

    def log_message(self, formato: str, *args: Any) -> None:
        return  # o console da aplicacao ja informa o que importa

    # -------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        seg = self._segmentos(self.path)

        if not seg or seg == ["index.html"] or seg == ["passageiro.html"]:
            self._pagina("passageiro.html"); return
        if seg in (["gestor"], ["gestor.html"]):
            self._pagina("gestor.html"); return
        if len(seg) == 2 and seg[0] == "vendor":
            self._arquivo_vendor(seg[1]); return
        if seg == ["api", "alertas"]:
            self._json({"alertas": REPO.alertas()}); return
        if seg == ["api", "decisoes"]:
            self._json({"decisoes": REPO.log_decisoes()}); return
        if seg == ["api", "pontos"]:
            self._json({"pontos": todos_os_pontos()}); return
        if seg == ["manifest.json"]:
            self._json(MANIFEST); return
        if seg == ["icone.svg"]:
            self._enviar(ICONE_SVG.encode("utf-8"), "image/svg+xml"); return
        if seg == ["sw.js"]:
            self._enviar(SERVICE_WORKER.encode("utf-8"),
                         "application/javascript; charset=utf-8"); return
        if seg == ["api", "saude"]:
            self._json({"status": "ok", **REPO.estatisticas_ingestao()}); return
        if seg == ["api", "stream"]:
            self._stream(); return
        if seg == ["api", "telemetria", "atual"]:
            self._json(self._estado_consolidado()); return
        if seg == ["api", "kpis"]:
            self._json(REPO.kpis()); return
        if seg == ["api", "resumo"]:
            self._json(REPO.hermes.resumo_de_turno(
                REPO.sintese(), REPO.kpis(), REPO.anomalias_ativas())); return
        if seg == ["api", "sintese"]:
            self._json(REPO.sintese()); return
        if seg == ["api", "avisos"]:
            self._json(REPO.hermes.avisos(REPO.anomalias_ativas())); return
        if seg == ["api", "historico", "chegadas"]:
            vid = self._parametros().get("veiculo")
            # identificador real nunca sai do servidor: troca-se pelo pseudonimo
            itens = []
            for c in REPO.indicadores.chegadas_recentes(40, vid):
                item = {k: v for k, v in c.items() if k != "vehicle_id"}
                item["vehicle_id_publico"] = pseudonimizar(c.get("vehicle_id", ""))
                itens.append(item)
            self._json({"chegadas": itens}); return
        if seg == ["api", "historico", "trilha"]:
            vid = self._parametros().get("veiculo", "")
            self._json({"vehicle_id_publico": pseudonimizar(vid),
                        "pontos": REPO.trilha_de(vid)}); return
        if seg == ["api", "passageiro", "chegadas"]:
            self._chegadas_para_passageiro(); return
        if seg == ["api", "passageiro", "veiculos"]:
            self._json({"veiculos": _veiculos_publicos(), "gerado_em": datetime.now(timezone.utc).isoformat()})
            return
        if seg == ["api", "linhas"]:
            self._json([l.to_dict() for l in REPO.listar_linhas()]); return
        if len(seg) == 3 and seg[:2] == ["api", "linhas"]:
            linha = REPO.obter_linha(seg[2])
            if linha is None: self._erro("linha inexistente", 404)
            else: self._json(linha.to_dict())
            return
        if seg == ["api", "veiculos"]:
            self._json([v.to_dict() for v in REPO.listar_veiculos()]); return
        if len(seg) == 3 and seg[:2] == ["api", "veiculos"]:
            veiculo = REPO.obter_veiculo(seg[2])
            if veiculo is None: self._erro("veiculo inexistente", 404)
            else: self._json(veiculo.to_dict())
            return

        self._erro("recurso nao encontrado", 404)

    # ------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        seg = self._segmentos(self.path)
        corpo = self._ler_json()

        if len(seg) == 4 and seg[:2] == ["api", "alertas"] and seg[3] == "decisao":
            acao = str(corpo.get("acao") or "")
            if acao not in ("aceitar", "ignorar"):
                self._erro("acao deve ser 'aceitar' ou 'ignorar'", 400); return
            try:
                registro = REPO.decidir(seg[2], acao)
            except KeyError:
                self._erro("alerta nao encontrado ou ja encerrado", 404); return
            print(f"[DECISAO] {registro['titulo']} ({registro['vehicle_id_publico']}): {acao}", flush=True)
            self._json(registro, 201); return

        if len(seg) == 4 and seg[:2] == ["api", "linhas"] and seg[3] == "paradas":
            corpo["linha_id"] = seg[2]
            try:
                p = inserir_ponto(corpo)
            except ValueError as exc:
                self._erro(str(exc), 400); return
            self._json(p.publico(), 201); return

        if seg == ["api", "pontos"]:
            try:
                p = inserir_ponto(corpo)
            except ValueError as exc:
                self._erro(str(exc), 400); return
            self._json(p.publico(), 201); return

        if seg == ["api", "iot", "telemetria"]:
            try:
                tel = REPO.ingerir(corpo)
            except ErroValidacao as exc:
                self._erro(f"payload fora do contrato: {exc}", 422); return
            if tel.occupancy_alert:
                print(f"[GATEWAY] {tel.vehicle_id} ocupacao {tel.occupancy_rate * 100:.0f}% "
                      f"acima do limite de conforto", flush=True)
            self._json({"status": "aceito", "vehicle_id": tel.vehicle_id}); return

        if seg == ["api", "linhas"]:
            try:
                linha = criar_linha_do_payload(corpo, self.offline)
            except ValueError as exc:
                self._erro(str(exc), 400); return
            REPO.salvar_linha(linha)
            print(f"[CRUD] linha criada: {linha.id} "
                  f"({linha.origem_tracado}, {len(linha.rota)} vertices)", flush=True)
            self._json(linha.to_dict(), 201); return

        if seg == ["api", "veiculos"]:
            try:
                veiculo = criar_veiculo_do_payload(corpo, self.base_url)
            except ValueError as exc:
                self._erro(str(exc), 400); return
            print(f"[CRUD] veiculo em operacao: {veiculo.id} -> {veiculo.linha_id}", flush=True)
            self._json(veiculo.to_dict(), 201); return

        if seg == ["api", "passageiro", "acessibilidade"]:
            self._solicitar_acessibilidade(corpo); return

        self._erro("recurso nao encontrado", 404)

    # -------------------------------------------------------------- PUT
    def do_PUT(self) -> None:  # noqa: N802
        seg = self._segmentos(self.path)
        corpo = self._ler_json()

        if len(seg) == 3 and seg[:2] == ["api", "pontos"]:
            try:
                p = editar_ponto(seg[2], corpo)
            except KeyError:
                self._erro("ponto inexistente", 404); return
            except ValueError as exc:
                self._erro(str(exc), 400); return
            self._json(p.publico()); return

        if len(seg) == 3 and seg[:2] == ["api", "linhas"]:
            linha = REPO.obter_linha(seg[2])
            if linha is None: self._erro("linha inexistente", 404); return
            linha.nome = str(corpo.get("nome", linha.nome))
            linha.cor = str(corpo.get("cor", linha.cor))
            try:
                linha.headway_planejado_s = max(
                    60.0, float(corpo.get("headway_min", linha.headway_planejado_s / 60.0)) * 60.0)
            except (TypeError, ValueError):
                self._erro("headway_min deve ser numerico", 400); return
            REPO.salvar_linha(linha)
            self._json(linha.to_dict()); return

        if len(seg) == 3 and seg[:2] == ["api", "veiculos"]:
            veiculo = REPO.obter_veiculo(seg[2])
            if veiculo is None: self._erro("veiculo inexistente", 404); return
            try:
                capacidade = int(corpo.get("capacidade", veiculo.capacidade))
            except (TypeError, ValueError):
                self._erro("capacidade deve ser inteira", 400); return
            if not 1 <= capacidade <= 300:
                self._erro("capacidade deve estar entre 1 e 300", 400); return
            veiculo.capacidade = capacidade
            veiculo.acessivel = bool(corpo.get("acessivel", veiculo.acessivel))
            REPO.salvar_veiculo(veiculo)
            self._json(veiculo.to_dict()); return

        self._erro("recurso nao encontrado", 404)

    # ----------------------------------------------------------- DELETE
    def do_DELETE(self) -> None:  # noqa: N802
        seg = self._segmentos(self.path)
        if len(seg) == 3 and seg[:2] == ["api", "pontos"]:
            try:
                ok = remover_ponto(seg[2])
            except ValueError as exc:
                self._erro(str(exc), 400); return
            self._json({"removido": ok}, 200 if ok else 404); return
        if len(seg) == 3 and seg[:2] == ["api", "linhas"]:
            ok = REPO.remover_linha(seg[2])
            self._json({"removido": ok}, 200 if ok else 404); return
        if len(seg) == 3 and seg[:2] == ["api", "veiculos"]:
            ok = REPO.remover_veiculo(seg[2])
            self._json({"removido": ok}, 200 if ok else 404); return
        self._erro("recurso nao encontrado", 404)

    # --------------------------------------------------------- handlers
    def _estado_consolidado(self) -> Dict[str, Any]:
        """Estado completo para o painel do gestor."""
        estado = REPO.telemetria_atual()
        linhas = {l.id: l for l in REPO.listar_linhas()}
        veiculos: List[Dict[str, Any]] = []

        for tel in estado:
            linha = linhas.get(tel.route_id)
            registro = tel.to_dict()
            registro["vehicle_id_publico"] = pseudonimizar(tel.vehicle_id)
            registro["lotacao"] = faixa_ocupacao(tel.occupancy_rate)
            registro["anomalias"] = [a.to_dict() for a in REPO.anomalias_de(tel.vehicle_id)]
            registro["chegadas"] = (REPO.kharon.estimar_chegadas(tel, linha, 3)
                                    if linha else [])
            veiculos.append(registro)

        veiculos.sort(key=lambda v: v["vehicle_id"])
        return {
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "veiculos_ativos": len(veiculos),
            "veiculos": veiculos,
            "avisos": REPO.hermes.avisos(REPO.anomalias_ativas()),
            "log": REPO.log_recente(),
            "ingestao": REPO.estatisticas_ingestao(),
        }

    def _chegadas_para_passageiro(self) -> None:
        """
        Superficie publica: so o necessario para decidir se vale esperar o onibus.
        Sem trip_id, sem contagem exata de passageiros, sem prefixo real do veiculo.
        """
        parametros = self._parametros()
        linha = REPO.obter_linha(parametros.get("linha", ""))
        parada_id = parametros.get("parada", "")
        if linha is None:
            self._erro("linha inexistente", 404); return

        indice_parada = next((i for i, p in enumerate(linha.paradas) if p.id == parada_id), None)
        if indice_parada is None:
            self._erro("parada inexistente nesta linha", 404); return

        chegadas: List[Dict[str, Any]] = []
        for tel in REPO.telemetria_atual():
            if tel.route_id != linha.id or tel.next_stop_index > indice_parada:
                continue  # ja passou pelo ponto nesta viagem
            previsao = REPO.kharon.estimar_chegadas(
                tel, linha, quantas=indice_parada - tel.next_stop_index + 1)
            if not previsao:
                continue
            destino = previsao[-1]
            if destino["stop_id"] != parada_id:
                continue
            chegadas.append({
                "vehicle_id_publico": pseudonimizar(tel.vehicle_id),
                "eta_s": destino["eta_s"],
                "eta_min_s": destino["eta_min_s"],
                "eta_max_s": destino["eta_max_s"],
                "confianca": destino["confianca"],
                "base": destino["base"],
                "amostras": destino["amostras"],
                "lotacao": faixa_ocupacao(tel.occupancy_rate),
                "ocupacao": round(tel.occupancy_rate, 3),
                "acessivel": tel.accessible_vehicle,
                "solicitacao_ativa": tel.accessibility_button,
                "atendimento": REPO.atendimento_de(tel.vehicle_id),
            })

        chegadas.sort(key=lambda c: c["eta_s"])

        # Pontos seguintes ao escolhido, no itinerario do veiculo mais proximo.
        # Apenas o que vem DEPOIS da parada selecionada: um ponto ja ultrapassado
        # nao ajuda a planejar o desembarque e confunde a leitura.
        proximos: List[Dict[str, Any]] = []
        if chegadas:
            lider = next((t for t in REPO.telemetria_atual()
                          if pseudonimizar(t.vehicle_id) == chegadas[0]["vehicle_id_publico"]), None)
            if lider is not None:
                adiante = len(linha.paradas) - lider.next_stop_index
                todas = REPO.kharon.estimar_chegadas(lider, linha, quantas=max(1, adiante))
                posteriores = {p.id for p in linha.paradas[indice_parada + 1:]}
                proximos = [{"stop_name": p["stop_name"], "eta_s": p["eta_s"]}
                            for p in todas if p["stop_id"] in posteriores][:4]

        self._json({
            "linha": {"id": linha.id, "nome": linha.nome, "cor": linha.cor},
            "parada": linha.paradas[indice_parada].publico(),
            "chegadas": chegadas,
            "proximos_pontos": proximos,
            "observacao": ("Previsao sujeita a variacao por transito, clima e bloqueios. "
                           "A faixa exibida reflete a incerteza do modelo."),
        })

    def _solicitar_acessibilidade(self, corpo: Dict[str, Any]) -> None:
        """
        O passageiro conhece apenas o identificador pseudonimizado. A resolucao
        para o veiculo real acontece aqui, no servidor, e nunca trafega de volta.
        """
        publico = str(corpo.get("vehicle_id_publico") or "")
        alvo = next((v for v in REPO.listar_veiculos() if pseudonimizar(v.id) == publico), None)
        if alvo is None:
            self._erro("veiculo nao encontrado", 404); return
        simulador = REPO.simulador_de(alvo.id)
        if simulador is None:
            self._erro("veiculo nao esta em operacao", 409); return
        simulador.solicitar_acessibilidade()
        print(f"[ACESSIBILIDADE] solicitacao registrada para {alvo.id}", flush=True)
        self._json({"status": "registrado", "vehicle_id_publico": publico})

    def _stream(self) -> None:
        """
        Server-Sent Events: empurra um tick a cada pacote ingerido, substituindo o
        polling cego de 1,5 s. A interface cai automaticamente para polling se o
        stream falhar, de modo que a perda do SSE nunca quebra o painel.
        """
        fila = REPO.assinar()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            while True:
                try:
                    mensagem = fila.get(timeout=15.0)
                except queue.Empty:
                    mensagem = json.dumps({"tipo": "keepalive"})
                self.wfile.write(f"data: {mensagem}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
            pass  # cliente fechou a aba
        finally:
            REPO.cancelar_assinatura(fila)


# =============================================================================
# 14. CATALOGO DE LINHAS SEMENTE
# =============================================================================
#
# Waypoints reais de Matao/SP para o OSRM. O itinerario de malha e a alternativa
# offline: movimentos ortogonais ao longo do azimute do arruamento local.
# =============================================================================

ORIGEM_101: Coordenada = (-21.61840, -48.37460)
ORIGEM_202: Coordenada = (-21.59320, -48.37820)
AZIMUTE_MATAO: float = 38.0  # orientacao aproximada do arruamento local

WAYPOINTS_101: List[Coordenada] = [
    (-21.61840, -48.37460), (-21.61120, -48.36650), (-21.60480, -48.36830),
    (-21.60000, -48.36470), (-21.59600, -48.36020), (-21.59200, -48.35570),
]
WAYPOINTS_202: List[Coordenada] = [
    (-21.59320, -48.37820), (-21.59950, -48.37190), (-21.60440, -48.36620),
    (-21.61040, -48.35960), (-21.61640, -48.35360), (-21.61940, -48.35060),
]

MOVIMENTOS_101: List[Tuple[str, float]] = [
    ("A", 420), ("B", 260), ("A", 380), ("B", -180), ("A", 300), ("B", 340),
    ("A", 260), ("B", -220), ("A", 440), ("B", 300), ("A", 380), ("B", -260),
    ("A", 320), ("B", 240), ("A", 500),
]
MOVIMENTOS_202: List[Tuple[str, float]] = [
    ("B", 380), ("A", 300), ("B", 260), ("A", -200), ("B", 420), ("A", 340),
    ("B", 280), ("A", -160), ("B", 460), ("A", 320), ("B", 300), ("A", 260),
    ("B", 400),
]

NOMES_101 = ["Terminal Centro", "Praca Matriz", "Av. Brasil", "Hospital Municipal",
             "Escola Estadual", "Parque Municipal", "Terminal Nova Matao"]
NOMES_202 = ["Terminal Norte", "Rodoviaria", "Centro Comercial", "Distrito Industrial",
             "Portaria Fabril", "Terminal Industrial"]

# Geometria das ruas gerada uma vez pelo OSRM (dados abertos OpenStreetMap).
# Embutida para a simulacao rodar sem internet e com o trajeto sobre as vias.
ROTAS_RUAS: Dict[str, List[List[float]]] = {"LINHA-101": [[-21.61834, -48.37456], [-21.6185, -48.37428], [-21.61883, -48.37373], [-21.61895, -48.37352], [-21.61903, -48.37318], [-21.61914, -48.37272], [-21.61919, -48.37256], [-21.6194, -48.37158], [-21.61951, -48.37123], [-21.6196, -48.3711], [-21.61965, -48.37107], [-21.61969, -48.37101], [-21.6197, -48.37095], [-21.61968, -48.37089], [-21.61944, -48.37081], [-21.61928, -48.37076], [-21.61878, -48.37062], [-21.61864, -48.37057], [-21.61854, -48.37054], [-21.61751, -48.37022], [-21.61562, -48.36923], [-21.61461, -48.3687], [-21.61496, -48.36793], [-21.61506, -48.36771], [-21.61506, -48.36764], [-21.61504, -48.36757], [-21.615, -48.3675], [-21.61488, -48.36742], [-21.61482, -48.36739], [-21.61476, -48.36735], [-21.61468, -48.36729], [-21.61462, -48.36722], [-21.6146, -48.36714], [-21.61457, -48.36703], [-21.61453, -48.36691], [-21.61447, -48.36679], [-21.61441, -48.36666], [-21.61434, -48.36656], [-21.61427, -48.36646], [-21.61418, -48.36636], [-21.61406, -48.36625], [-21.61404, -48.36623], [-21.61394, -48.36616], [-21.61383, -48.36609], [-21.61374, -48.36601], [-21.61367, -48.36595], [-21.61363, -48.3659], [-21.61352, -48.36582], [-21.61343, -48.36577], [-21.6129, -48.36576], [-21.61284, -48.36576], [-21.61276, -48.36576], [-21.61272, -48.3658], [-21.61271, -48.36586], [-21.61271, -48.36593], [-21.61272, -48.36597], [-21.61277, -48.36618], [-21.61261, -48.36652], [-21.61199, -48.36621], [-21.61176, -48.36608], [-21.61149, -48.36666], [-21.6114, -48.36684], [-21.61107, -48.36757], [-21.61072, -48.36833], [-21.61038, -48.36907], [-21.60955, -48.36864], [-21.60897, -48.36832], [-21.60893, -48.36838], [-21.6089, -48.36845], [-21.60848, -48.36935], [-21.60808, -48.37021], [-21.60771, -48.37103], [-21.6069, -48.37062], [-21.60674, -48.37053], [-21.60623, -48.37027], [-21.60558, -48.36994], [-21.60507, -48.36968], [-21.60423, -48.36925], [-21.60422, -48.36924], [-21.60463, -48.36838], [-21.60469, -48.36824], [-21.60503, -48.36751], [-21.6042, -48.36706], [-21.60339, -48.36663], [-21.60337, -48.36662], [-21.60254, -48.36618], [-21.6017, -48.36572], [-21.60089, -48.36529], [-21.59997, -48.36478], [-21.60001, -48.36471], [-21.6004, -48.36388], [-21.60081, -48.363], [-21.60078, -48.36299], [-21.60067, -48.36294], [-21.60062, -48.36292], [-21.59993, -48.36253], [-21.59887, -48.36198], [-21.59868, -48.36206], [-21.59857, -48.36206], [-21.59852, -48.36206], [-21.59848, -48.36205], [-21.59844, -48.36203], [-21.5984, -48.362], [-21.59834, -48.36188], [-21.59833, -48.36179], [-21.59829, -48.36167], [-21.59818, -48.36158], [-21.59756, -48.36127], [-21.59675, -48.36084], [-21.59591, -48.36039], [-21.59575, -48.3603], [-21.59493, -48.35986], [-21.59526, -48.35903], [-21.59554, -48.35834], [-21.5959, -48.35744], [-21.59564, -48.3573], [-21.59517, -48.35705], [-21.59507, -48.357], [-21.59445, -48.35666], [-21.59378, -48.35629], [-21.59347, -48.35615], [-21.59324, -48.35605], [-21.59294, -48.35588], [-21.59238, -48.35557], [-21.59213, -48.35543]], "LINHA-202": [[-21.59315, -48.37844], [-21.59355, -48.37855], [-21.59329, -48.38003], [-21.59327, -48.38017], [-21.59322, -48.38029], [-21.59316, -48.38042], [-21.59313, -48.38052], [-21.59311, -48.38061], [-21.59312, -48.38073], [-21.59317, -48.38088], [-21.59327, -48.38093], [-21.59331, -48.38094], [-21.59348, -48.38097], [-21.59352, -48.38098], [-21.59361, -48.381], [-21.59372, -48.38084], [-21.59375, -48.38073], [-21.59375, -48.38063], [-21.59373, -48.38048], [-21.5937, -48.38038], [-21.59369, -48.38029], [-21.5937, -48.38007], [-21.594, -48.37807], [-21.59469, -48.37525], [-21.59471, -48.37517], [-21.59529, -48.37288], [-21.59571, -48.37215], [-21.59606, -48.37235], [-21.59658, -48.37256], [-21.5971, -48.37262], [-21.59808, -48.37261], [-21.59852, -48.37261], [-21.59875, -48.37261], [-21.59895, -48.37259], [-21.59926, -48.37258], [-21.5995, -48.37259], [-21.59958, -48.37262], [-21.59969, -48.37265], [-21.6003, -48.37291], [-21.60042, -48.37296], [-21.60049, -48.37296], [-21.60052, -48.37295], [-21.60056, -48.37293], [-21.60057, -48.37291], [-21.60057, -48.37284], [-21.60053, -48.37277], [-21.60038, -48.37272], [-21.60022, -48.37265], [-21.60008, -48.37241], [-21.59992, -48.37209], [-21.59988, -48.37203], [-21.59952, -48.37186], [-21.5993, -48.37176], [-21.59923, -48.37172], [-21.59895, -48.37157], [-21.59922, -48.37107], [-21.60012, -48.3715], [-21.59996, -48.37188], [-21.59988, -48.37203], [-21.59968, -48.37243], [-21.59957, -48.37245], [-21.59955, -48.37247], [-21.59954, -48.3725], [-21.59954, -48.37254], [-21.59955, -48.37257], [-21.59958, -48.37262], [-21.59969, -48.37265], [-21.6003, -48.37291], [-21.60042, -48.37296], [-21.60049, -48.37296], [-21.60052, -48.37295], [-21.60056, -48.37293], [-21.60057, -48.37291], [-21.60057, -48.37284], [-21.60053, -48.37277], [-21.60098, -48.37189], [-21.60134, -48.371], [-21.60176, -48.37015], [-21.60217, -48.36926], [-21.60257, -48.36838], [-21.60297, -48.3675], [-21.60339, -48.36663], [-21.6034, -48.3666], [-21.60376, -48.36577], [-21.6038, -48.3657], [-21.6038, -48.36569], [-21.60389, -48.36574], [-21.60429, -48.36596], [-21.60447, -48.36606], [-21.60463, -48.36614], [-21.60546, -48.36658], [-21.6058, -48.36589], [-21.60594, -48.36576], [-21.60638, -48.36489], [-21.6068, -48.36401], [-21.60717, -48.3632], [-21.60723, -48.36315], [-21.60732, -48.36313], [-21.6074, -48.36312], [-21.60743, -48.3631], [-21.60748, -48.36308], [-21.60751, -48.36304], [-21.60753, -48.36298], [-21.60753, -48.36291], [-21.60754, -48.36267], [-21.60812, -48.36143], [-21.6085, -48.36064], [-21.60855, -48.36051], [-21.60893, -48.35971], [-21.60956, -48.36003], [-21.61019, -48.36035], [-21.61023, -48.36026], [-21.61051, -48.35966], [-21.61086, -48.3589], [-21.61175, -48.357], [-21.61259, -48.35522], [-21.61344, -48.3534], [-21.61406, -48.35373], [-21.61467, -48.35406], [-21.6153, -48.35439], [-21.61592, -48.35472], [-21.61596, -48.35471], [-21.616, -48.35469], [-21.61604, -48.35467], [-21.61607, -48.35463], [-21.6161, -48.35459], [-21.61611, -48.35454], [-21.61612, -48.35449], [-21.61611, -48.35444], [-21.61609, -48.3544], [-21.61607, -48.35436], [-21.61614, -48.35423], [-21.61637, -48.35369], [-21.61641, -48.35361], [-21.61667, -48.35305], [-21.61699, -48.35237], [-21.61729, -48.35173], [-21.6176, -48.35108], [-21.6179, -48.35044], [-21.61818, -48.34984], [-21.61944, -48.3505]]}

CATALOGO = [
    {"id": "LINHA-101", "nome": "Linha simulada 101 - Centro", "cor": "#38bdf8",
     "waypoints": WAYPOINTS_101, "origem": ORIGEM_101, "movimentos": MOVIMENTOS_101,
     "nomes": NOMES_101, "headway_min": 10.0},
    {"id": "LINHA-202", "nome": "Linha simulada 202 - Distrito", "cor": "#a78bfa",
     "waypoints": WAYPOINTS_202, "origem": ORIGEM_202, "movimentos": MOVIMENTOS_202,
     "nomes": NOMES_202, "headway_min": 14.0},
]

FROTA_INICIAL = [
    ("BUS-MATAO-042", "LINHA-101", 70, True),
    ("BUS-MATAO-077", "LINHA-101", 54, False),
    ("BUS-MATAO-113", "LINHA-202", 62, True),
    ("BUS-MATAO-128", "LINHA-202", 70, True),
]


def bootstrap(offline: bool, base_url: str) -> None:
    """Resolve os tracados, cadastra as linhas-semente e poe a frota em operacao."""
    for item in CATALOGO:
        print(f"[BOOT] resolvendo tracado de {item['id']} ...", flush=True)
        if item["id"] in ROTAS_RUAS:
            # Trajeto real sobre as vias, pre-gerado: sem internet e sem diagonais.
            rota = reamostrar([(p[0], p[1]) for p in ROTAS_RUAS[item["id"]]])
            origem = "RUAS-PRE-GERADAS"
        else:
            fallback = tracado_em_malha(item["origem"], item["movimentos"], AZIMUTE_MATAO)
            rota, origem = resolver_tracado(item["waypoints"], fallback=fallback, offline=offline)
        linha = Linha(
            id=item["id"], nome=item["nome"], rota=rota,
            paradas=montar_paradas(rota, item["id"].split("-")[-1], item["nomes"]),
            cor=item["cor"], origem_tracado=origem,
            headway_planejado_s=item["headway_min"] * 60.0)
        REPO.salvar_linha(linha)

        descricao = {
            "OSRM": "geometria real das vias (OSRM)",
            "CACHE": "geometria real das vias (cache local)",
            "MALHA-LOCAL": "malha viaria ortogonal sintetica (sem rede)",
            "RUAS-PRE-GERADAS": "trajeto real sobre as ruas (OpenStreetMap, embutido)",
        }[origem]
        print(f"       {len(rota)} vertices · {linha.extensao_m / 1000:.2f} km · {descricao}")

    _definir_acessibilidade_inicial()
    for veiculo_id, linha_id, capacidade, acessivel in FROTA_INICIAL:
        linha = REPO.obter_linha(linha_id)
        if linha is None:
            continue
        veiculo = Veiculo(id=veiculo_id, linha_id=linha_id,
                          capacidade=capacidade, acessivel=acessivel)
        REPO.salvar_veiculo(veiculo)
        iniciar_simulador(veiculo, linha, base_url)
        print(f"[BOOT] central embarcada ativa: {veiculo_id} "
              f"({linha_id}, capacidade {capacidade}"
              f"{', acessivel' if acessivel else ''})")


# =============================================================================
# 15. AEGIS - TESTES AUTOMATIZADOS
# =============================================================================

def _linha_de_teste(n_paradas: int = 4, extensao_m: float = 2000.0) -> Linha:
    origem = (-21.6000, -48.3600)
    rota = reamostrar([origem, deslocar(origem, 0.0, extensao_m)], 50.0)
    nomes = nomes_genericos(n_paradas)
    return Linha(id="T-1", nome="Teste", rota=rota,
                 paradas=montar_paradas(rota, "T", nomes),
                 headway_planejado_s=600.0)


def _telemetria_de_teste(**ajustes: Any) -> Telemetria:
    base: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "vehicle_id": "BUS-1", "route_id": "T-1", "trip_id": "TRIP-1",
        "latitude": -21.6, "longitude": -48.36, "speed_kmh": 25.0,
        "door_status": "CLOSED", "passenger_count": 30, "passenger_capacity": 60,
        "occupancy_rate": 0.5, "occupancy_alert": False, "internal_temperature_c": 23.0,
        "accessibility_button": False, "accessible_vehicle": True, "is_at_stop": False,
        "current_stop": "A", "next_stop": "B", "next_stop_index": 1,
        "distance_next_stop_m": 300.0, "position_m": 400.0, "route_progress": 0.2,
        "odometer_m": 400.0, "trip_elapsed_s": 60.0, "schedule_deviation_s": 0.0,
        "segment_avg_speed_kmh": 22.0,
    }
    base.update(ajustes)
    return Telemetria(**base)


class TesteGeometria(unittest.TestCase):

    def test_haversine_conhecido(self) -> None:
        """Um grau de latitude equivale a aproximadamente 111 km."""
        d = haversine_m((0.0, 0.0), (1.0, 0.0))
        self.assertAlmostEqual(d, 111_195.0, delta=400.0)

    def test_deslocar_preserva_distancia(self) -> None:
        origem = (-21.6, -48.36)
        destino = deslocar(origem, 300.0, 400.0)
        self.assertAlmostEqual(haversine_m(origem, destino), 500.0, delta=2.0)

    def test_reamostrar_preserva_vertices(self) -> None:
        """Esquinas nao podem ser perdidas na densificacao."""
        origem = (-21.6, -48.36)
        caminho = tracado_em_malha(origem, [("A", 300), ("B", 300)], 38.0)
        denso = reamostrar(caminho, 12.0)
        for vertice in caminho:
            self.assertTrue(
                any(haversine_m(vertice, p) < 0.5 for p in denso),
                f"vertice {vertice} desapareceu apos a reamostragem")

    def test_reamostrar_espacamento(self) -> None:
        origem = (-21.6, -48.36)
        denso = reamostrar([origem, deslocar(origem, 0.0, 600.0)], 12.0)
        passos = [haversine_m(a, b) for a, b in zip(denso, denso[1:])]
        self.assertTrue(all(p <= 12.5 for p in passos), max(passos))

    def test_malha_gera_angulos_retos(self) -> None:
        """A malha de fallback nao pode degenerar em diagonal continua."""
        origem = (-21.6, -48.36)
        pontos = tracado_em_malha(origem, [("A", 300), ("B", 300), ("A", 300)], 38.0)

        def em_metros(p: Coordenada, q: Coordenada) -> Tuple[float, float]:
            """
            Vetor entre dois pontos no plano local, em metros.

            O angulo precisa ser medido em metros, e nao em graus: nesta latitude
            um grau de longitude vale cerca de 93% de um grau de latitude, de modo
            que segmentos perpendiculares no terreno nao produzem produto escalar
            nulo em coordenadas geograficas.
            """
            leste = (q[1] - p[1]) * METROS_POR_GRAU_LAT * math.cos(math.radians(p[0]))
            norte = (q[0] - p[0]) * METROS_POR_GRAU_LAT
            return (leste, norte)

        for i in range(len(pontos) - 2):
            a, b, c = pontos[i], pontos[i + 1], pontos[i + 2]
            v1, v2 = em_metros(a, b), em_metros(b, c)
            escalar = v1[0] * v2[0] + v1[1] * v2[1]
            norma = math.hypot(*v1) * math.hypot(*v2)
            self.assertLess(abs(escalar / norma), 0.02,
                            "segmentos consecutivos da malha deixaram de ser perpendiculares")

    def test_posicao_em_extremos(self) -> None:
        linha = _linha_de_teste()
        acumulado = distancias_acumuladas(linha.rota)
        self.assertEqual(posicao_em(linha.rota, acumulado, 0.0), linha.rota[0])
        fim = posicao_em(linha.rota, acumulado, acumulado[-1])
        self.assertAlmostEqual(haversine_m(fim, linha.rota[-1]), 0.0, delta=0.5)


class TesteValidacao(unittest.TestCase):

    def test_payload_valido(self) -> None:
        tel = validar_telemetria(_telemetria_de_teste().to_dict())
        self.assertEqual(tel.vehicle_id, "BUS-1")

    def test_campo_ausente(self) -> None:
        payload = _telemetria_de_teste().to_dict()
        del payload["speed_kmh"]
        with self.assertRaises(ErroValidacao):
            validar_telemetria(payload)

    def test_campo_extra(self) -> None:
        payload = _telemetria_de_teste().to_dict()
        payload["campo_injetado"] = "x"
        with self.assertRaises(ErroValidacao):
            validar_telemetria(payload)

    def test_velocidade_negativa(self) -> None:
        with self.assertRaises(ErroValidacao):
            validar_telemetria(_telemetria_de_teste(speed_kmh=-5.0).to_dict())

    def test_porta_aberta_em_movimento(self) -> None:
        """Leitura fisicamente impossivel deve ser rejeitada na ingestao."""
        payload = _telemetria_de_teste(door_status="OPEN", speed_kmh=30.0).to_dict()
        with self.assertRaises(ErroValidacao):
            validar_telemetria(payload)

    def test_booleano_em_campo_numerico(self) -> None:
        payload = _telemetria_de_teste().to_dict()
        payload["speed_kmh"] = True
        with self.assertRaises(ErroValidacao):
            validar_telemetria(payload)


class TestePrivacidade(unittest.TestCase):

    def test_pseudonimo_estavel_e_nao_reversivel(self) -> None:
        a = pseudonimizar("BUS-MATAO-042")
        self.assertEqual(a, pseudonimizar("BUS-MATAO-042"))
        self.assertNotIn("042", a)
        self.assertNotEqual(a, pseudonimizar("BUS-MATAO-043"))

    def test_mascaramento_do_console(self) -> None:
        payload = _telemetria_de_teste().to_dict()
        mascarado = mascarar_pacote(payload)
        self.assertEqual(mascarado["trip_id"], "***")
        self.assertNotEqual(mascarado["vehicle_id"], payload["vehicle_id"])
        self.assertEqual(payload["trip_id"], "TRIP-1")  # original intacto

    def test_faixas_de_ocupacao(self) -> None:
        self.assertEqual(faixa_ocupacao(0.10), "VAZIO")
        self.assertEqual(faixa_ocupacao(0.50), "MODERADO")
        self.assertEqual(faixa_ocupacao(0.80), "CHEIO")
        self.assertEqual(faixa_ocupacao(0.99), "LOTADO")


class TesteKharon(unittest.TestCase):

    def setUp(self) -> None:
        self.historico = HistoricoTrechos()
        self.kharon = Kharon(self.historico)
        self.linha = _linha_de_teste()

    def test_eta_cresce_com_a_distancia(self) -> None:
        tel = _telemetria_de_teste(position_m=0.0, next_stop_index=1)
        previsao = self.kharon.estimar_chegadas(tel, self.linha, 3)
        self.assertGreaterEqual(len(previsao), 2)
        tempos = [p["eta_s"] for p in previsao]
        self.assertEqual(tempos, sorted(tempos))

    def test_faixa_de_confianca_encapsula_a_estimativa(self) -> None:
        tel = _telemetria_de_teste(position_m=0.0, next_stop_index=1)
        p = self.kharon.estimar_chegadas(tel, self.linha, 1)[0]
        self.assertLessEqual(p["eta_min_s"], p["eta_s"])
        self.assertGreaterEqual(p["eta_max_s"], p["eta_s"])

    def test_historico_estreita_a_faixa(self) -> None:
        tel = _telemetria_de_teste(position_m=0.0, next_stop_index=1)
        sem = self.kharon.estimar_chegadas(tel, self.linha, 1)[0]
        for _ in range(8):
            self.historico.registrar(self.linha.id, 1, 24.0)
        com = self.kharon.estimar_chegadas(tel, self.linha, 1)[0]
        self.assertGreater(com["confianca"], sem["confianca"])

    def test_lotacao_critica_detectada(self) -> None:
        tel = _telemetria_de_teste(passenger_count=59, passenger_capacity=60,
                                   occupancy_rate=0.98, occupancy_alert=True)
        codigos = [a.codigo for a in self.kharon.analisar(tel, self.linha, [tel])]
        self.assertIn("LOTACAO_CRITICA", codigos)

    def test_operacao_normal_sem_anomalia(self) -> None:
        tel = _telemetria_de_teste()
        self.assertEqual(self.kharon.analisar(tel, self.linha, [tel]), [])

    def test_atraso_detectado(self) -> None:
        tel = _telemetria_de_teste(schedule_deviation_s=400.0)
        codigos = [a.codigo for a in self.kharon.analisar(tel, self.linha, [tel])]
        self.assertIn("ATRASO_OPERACIONAL", codigos)

    def test_comboiamento_detectado(self) -> None:
        atras = _telemetria_de_teste(vehicle_id="BUS-A", position_m=1000.0)
        frente = _telemetria_de_teste(vehicle_id="BUS-B", position_m=1150.0)
        codigos = [a.codigo for a in self.kharon.analisar(atras, self.linha, [atras, frente])]
        self.assertIn("COMBOIAMENTO", codigos)

    def test_sem_comboiamento_com_intervalo_regular(self) -> None:
        atras = _telemetria_de_teste(vehicle_id="BUS-A", position_m=0.0)
        frente = _telemetria_de_teste(vehicle_id="BUS-B", position_m=5000.0)
        codigos = [a.codigo for a in self.kharon.analisar(atras, self.linha, [atras, frente])]
        self.assertNotIn("COMBOIAMENTO", codigos)

    def test_sumarizacao_agrega_por_linha(self) -> None:
        tels = [_telemetria_de_teste(vehicle_id="A", occupancy_rate=0.4),
                _telemetria_de_teste(vehicle_id="B", occupancy_rate=0.8)]
        sintese = self.kharon.sumarizar(tels, {"T-1": self.linha}, [])
        self.assertEqual(sintese["global"]["veiculos_em_operacao"], 2)
        self.assertAlmostEqual(sintese["linhas"][0]["ocupacao_media"], 0.6, places=2)


class TesteIndicadores(unittest.TestCase):

    def test_pontualidade(self) -> None:
        ind = Indicadores()
        for desvio in (10.0, -30.0, 400.0, 5.0):
            ind.registrar_chegada(Chegada(
                vehicle_id="A", route_id="T-1", stop_id="P", stop_name="P",
                instante="agora", desvio_s=desvio, ocupacao=0.5,
                passageiros_embarcados=2, passageiros_desembarcados=1))
        kpis = ind.instantaneo(4, 4, 600.0)
        self.assertAlmostEqual(kpis["pontualidade"]["valor"], 0.75, places=2)

    def test_disponibilidade(self) -> None:
        kpis = Indicadores().instantaneo(4, 3, 0.0)
        self.assertAlmostEqual(kpis["disponibilidade_frota"]["valor"], 0.75, places=2)

    def test_kpis_sem_dados_nao_quebram(self) -> None:
        kpis = Indicadores().instantaneo(0, 0, 0.0)
        self.assertIsNone(kpis["pontualidade"]["valor"])
        self.assertIsNone(kpis["duracao_viagem"]["valor"])


class TesteHermes(unittest.TestCase):

    def test_todo_aviso_e_nao_vinculante(self) -> None:
        anomalia = Anomalia("LOTACAO_CRITICA", "CRITICO", "Lotacao critica", "detalhe",
                            "BUS-1", "T-1", "agora")
        aviso = Hermes().avisos([anomalia])[0]
        self.assertFalse(aviso["vinculante"])
        self.assertTrue(aviso["sugestao"])

    def test_criticos_vem_primeiro(self) -> None:
        avisos = Hermes().avisos([
            Anomalia("COMBOIAMENTO", "ATENCAO", "t", "d", "B", "T-1", "agora"),
            Anomalia("LOTACAO_CRITICA", "CRITICO", "t", "d", "A", "T-1", "agora")])
        self.assertEqual(avisos[0]["severidade"], "CRITICO")

    def test_resumo_menciona_pontualidade(self) -> None:
        sintese = {"global": {"veiculos_em_operacao": 3, "veiculos_acima_do_conforto": 1},
                   "linhas": []}
        kpis = {"pontualidade": {"valor": 0.9}}
        resumo = Hermes().resumo_de_turno(sintese, kpis, [])
        self.assertIn("90%", resumo["texto"])
        self.assertFalse(resumo["vinculante"])


class TesteSimulacao(unittest.TestCase):

    def setUp(self) -> None:
        self.repo = Repositorio()
        self.linha = _linha_de_teste(n_paradas=4, extensao_m=2400.0)
        self.repo.salvar_linha(self.linha)
        self.veiculo = Veiculo(id="BUS-T", linha_id=self.linha.id, capacidade=50)
        self.central = CentralTelemetria(self.veiculo, self.linha, self.repo,
                                         "http://localhost:0")

    def test_pacote_gerado_passa_na_validacao(self) -> None:
        """O produtor e o validador precisam concordar sobre o contrato."""
        for _ in range(30):
            pacote = self.central.passo(2.0).to_dict()
            validar_telemetria(pacote)

    def test_porta_so_abre_parado(self) -> None:
        for _ in range(200):
            tel = self.central.passo(2.0)
            if tel.door_status == "OPEN":
                self.assertEqual(tel.speed_kmh, 0.0)

    def test_alerta_de_ocupacao_segue_a_regra(self) -> None:
        """O alerta e funcao apenas da taxa, nunca da anomalia."""
        for _ in range(200):
            tel = self.central.passo(2.0)
            self.assertEqual(tel.occupancy_alert, tel.occupancy_rate > LIMITE_ALERTA_OCUPACAO)

    def test_progresso_limitado(self) -> None:
        for _ in range(300):
            tel = self.central.passo(3.0)
            self.assertGreaterEqual(tel.route_progress, 0.0)
            self.assertLessEqual(tel.route_progress, 1.0)

    def test_odometro_nunca_regride(self) -> None:
        anterior = 0.0
        for _ in range(100):
            atual = self.central.passo(2.0).odometer_m
            self.assertGreaterEqual(atual, anterior)
            anterior = atual

    def test_veiculo_avanca_pelas_paradas(self) -> None:
        indices = set()
        for _ in range(400):
            indices.add(self.central.passo(4.0).next_stop_index)
        self.assertGreater(len(indices), 1, "o veiculo nao progrediu no itinerario")

    def test_store_and_forward_retem_pacotes(self) -> None:
        """Sem rede, nenhum pacote pode ser descartado em silencio."""
        for _ in range(5):
            self.central._transmitir(self.central.passo(2.0).to_dict())
        self.assertEqual(len(self.central._buffer_offline), 5)

    def test_trecho_degenerado_nao_entra_no_historico(self) -> None:
        """A parada de origem fica na posicao zero e nao pode poluir o ETA."""
        for _ in range(600):
            self.central.passo(3.0)
        media_origem, amostras_origem = self.repo.historico_trechos.media(self.linha.id, 0)
        self.assertEqual(amostras_origem, 0,
                         f"trecho degenerado alimentou o historico com {media_origem} km/h")
        _, amostras_reais = self.repo.historico_trechos.media(self.linha.id, 2)
        self.assertGreater(amostras_reais, 0)

    def test_congestionamento_produz_atraso_detectavel(self) -> None:
        """
        A causa (retencao de via) e sorteada; o diagnostico tem de emergir da
        medicao. Se nenhum atraso aparece, a deteccao de anomalia nunca exerce.
        """
        import unittest.mock as um
        random.seed(7)
        kharon = Kharon(self.repo.historico_trechos)
        codigos = set()
        desvios = []
        # taxa elevada de retencao para garantir que o cenario ocorra no intervalo simulado
        with um.patch.multiple(sys.modules[__name__], TAXA_CONGESTIONAMENTO_POR_S=1 / 120.0):
            for _ in range(3000):
                tel = self.central.passo(3.0)
                desvios.append(tel.schedule_deviation_s)
                codigos.update(a.codigo for a in kharon.analisar(tel, self.linha, [tel]))
        self.assertGreater(max(desvios), LIMITE_ATRASO_S,
                           "o trafego simulado nunca gerou atraso relevante")
        self.assertIn("ATRASO_OPERACIONAL", codigos)

    def test_acessibilidade_e_registrada(self) -> None:
        self.central.passo(2.0)
        self.central.solicitar_acessibilidade()
        # a solicitacao persiste em movimento, ate o desembarque ou o atendimento
        self.assertTrue(self.central._acessibilidade_solicitada)


class TesteRepositorio(unittest.TestCase):

    def setUp(self) -> None:
        self.repo = Repositorio()
        self.linha = _linha_de_teste()
        self.repo.salvar_linha(self.linha)

    def test_ingestao_rejeita_payload_invalido(self) -> None:
        with self.assertRaises(ErroValidacao):
            self.repo.ingerir({"vehicle_id": "X"})
        self.assertEqual(self.repo.estatisticas_ingestao()["rejeitados"], 1)

    def test_ingestao_aceita_e_registra_trilha(self) -> None:
        self.repo.ingerir(_telemetria_de_teste().to_dict())
        self.assertEqual(len(self.repo.telemetria_atual()), 1)
        self.assertEqual(len(self.repo.trilha_de("BUS-1")), 1)

    def test_remocao_de_linha_remove_veiculos(self) -> None:
        self.repo.salvar_veiculo(Veiculo(id="V1", linha_id=self.linha.id, capacidade=50))
        self.repo.remover_linha(self.linha.id)
        self.assertIsNone(self.repo.obter_veiculo("V1"))

    def test_console_nunca_expoe_dado_bruto(self) -> None:
        self.repo.ingerir(_telemetria_de_teste().to_dict())
        registro = self.repo.log_recente()[0]
        self.assertEqual(registro["payload"]["trip_id"], "***")
        self.assertTrue(registro["payload"]["vehicle_id"].startswith("V-"))

    def test_acesso_concorrente(self) -> None:
        """O repositorio precisa suportar ingestao simultanea sem corromper estado."""
        def trabalhar(n: int) -> None:
            for i in range(20):
                self.repo.ingerir(_telemetria_de_teste(
                    vehicle_id=f"BUS-{n}", position_m=float(i * 10)).to_dict())

        threads = [threading.Thread(target=trabalhar, args=(n,)) for n in range(6)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(self.repo.telemetria_atual()), 6)
        self.assertEqual(self.repo.estatisticas_ingestao()["recebidos"], 120)


class TesteAlertasEPontos(unittest.TestCase):
    """Fluxo passageiro -> gestor (rampa) e CRUD de pontos com recalculo de horarios."""

    def setUp(self) -> None:
        import unittest.mock as um
        self.repo = Repositorio()
        self.linha = _linha_de_teste(n_paradas=4)
        self.repo.salvar_linha(self.linha)
        self._patch = um.patch.object(sys.modules[__name__], "REPO", self.repo)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _injetar(self, **ajustes: Any) -> None:
        dados = asdict(_telemetria_de_teste(route_id=self.linha.id, **ajustes))
        self.repo.ingerir(dados)

    def test_alerta_id_e_estavel_e_depende_do_codigo(self) -> None:
        self.assertEqual(alerta_id("BUS-1", "PEDIDO_RAMPA"), alerta_id("BUS-1", "PEDIDO_RAMPA"))
        self.assertNotEqual(alerta_id("BUS-1", "PEDIDO_RAMPA"), alerta_id("BUS-1", "ATRASO_OPERACIONAL"))

    def test_pedido_de_rampa_vira_alerta_pendente(self) -> None:
        self._injetar(accessibility_button=True)
        alertas = [a for a in self.repo.alertas() if a["tipo"] == "RAMPA"]
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["status"], "pendente")
        self.assertIsNone(self.repo.atendimento_de("BUS-1"))

    def test_aceitar_rampa_confirma_atendimento_ao_passageiro(self) -> None:
        self._injetar(accessibility_button=True)
        aid = alerta_id("BUS-1", "PEDIDO_RAMPA")
        registro = self.repo.decidir(aid, "aceitar")
        self.assertEqual(registro["acao"], "aceitar")
        self.assertEqual(self.repo.atendimento_de("BUS-1"), "confirmado")
        self.assertEqual(self.repo.log_decisoes()[0]["alerta"], aid)

    def test_decisao_em_alerta_inexistente_levanta_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            self.repo.decidir("nao-existe", "aceitar")

    def test_atendimento_expira(self) -> None:
        self._injetar(accessibility_button=True)
        self.repo.decidir(alerta_id("BUS-1", "PEDIDO_RAMPA"), "aceitar")
        self.assertIsNone(self.repo.atendimento_de("BUS-1", validade_s=-1.0))

    def test_inserir_ponto_mantem_ordem_e_horarios_crescentes(self) -> None:
        import unittest.mock as um
        with um.patch.object(sys.modules[__name__], "REPO", self.repo):
            ponto = inserir_ponto({
                "linha_id": self.linha.id, "nome": "Ponto novo",
                "latitude": self.linha.rota[len(self.linha.rota) // 2][0],
                "longitude": self.linha.rota[len(self.linha.rota) // 2][1],
                "rampa": True, "piso_tatil": False,
            })
        self.assertEqual(len(self.linha.paradas), 5)
        self.assertTrue(ponto.rampa)
        posicoes = [p.posicao_m for p in self.linha.paradas]
        self.assertEqual(posicoes, sorted(posicoes))
        planejados = [p.chegada_planejada_s for p in self.linha.paradas]
        self.assertEqual(planejados, sorted(planejados))
        self.assertEqual(len({p.id for p in self.linha.paradas}), 5)

    def test_ponto_exige_linha_nome_e_coordenadas(self) -> None:
        with self.assertRaises(ValueError):
            inserir_ponto({"linha_id": self.linha.id, "nome": "", "latitude": -21.6, "longitude": -48.36})
        with self.assertRaises(ValueError):
            inserir_ponto({"linha_id": "NAO-EXISTE", "nome": "X", "latitude": -21.6, "longitude": -48.36})

    def test_editar_ponto_altera_acessibilidade(self) -> None:
        ponto_id = self.linha.paradas[0].id
        editar_ponto(ponto_id, {"piso_tatil": True, "rampa": False})
        p = self.linha.paradas[0]
        self.assertTrue(p.piso_tatil)
        self.assertFalse(p.rampa)

    def test_editar_ponto_inexistente_levanta_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            editar_ponto("XXX-P99", {"nome": "Y"})

    def test_remover_ponto_respeita_minimo_de_duas_paradas(self) -> None:
        self.assertTrue(remover_ponto(self.linha.paradas[0].id))
        self.assertEqual(len(self.linha.paradas), 3)
        while len(self.linha.paradas) > 2:
            remover_ponto(self.linha.paradas[0].id)
        with self.assertRaises(ValueError):
            remover_ponto(self.linha.paradas[0].id)

    def test_acessibilidade_inicial_distribui_rampa_e_piso(self) -> None:
        _definir_acessibilidade_inicial()
        rampas = [p.rampa for p in self.linha.paradas]
        self.assertIn(True, rampas)
        self.assertIn(False, rampas)


class TesteCrud(unittest.TestCase):

    def test_linha_exige_duas_coordenadas(self) -> None:
        with self.assertRaises(ValueError):
            criar_linha_do_payload({"nome": "X", "coordenadas": [[-21.6, -48.3]]}, offline=True)

    def test_linha_rejeita_coordenada_fora_de_faixa(self) -> None:
        with self.assertRaises(ValueError):
            criar_linha_do_payload(
                {"nome": "X", "coordenadas": [[-21.6, -48.3], [200.0, 0.0]]}, offline=True)

    def test_linha_offline_usa_as_coordenadas_informadas(self) -> None:
        linha = criar_linha_do_payload(
            {"nome": "X", "coordenadas": [[-21.60, -48.36], [-21.59, -48.35]],
             "usar_osrm": False}, offline=True)
        self.assertGreaterEqual(len(linha.rota), 2)
        self.assertEqual(len(linha.paradas), 6)

    def test_cor_invalida_cai_na_paleta(self) -> None:
        self.assertEqual(_cor_ou_padrao("vermelho"), proxima_cor_livre())
        self.assertEqual(_cor_ou_padrao("#FF0000"), "#FF0000")

    def test_horario_planejado_e_crescente(self) -> None:
        linha = _linha_de_teste(n_paradas=5)
        tempos = [p.chegada_planejada_s for p in linha.paradas]
        self.assertEqual(tempos, sorted(tempos))

    def test_referencia_continua_bate_nas_paradas(self) -> None:
        """Interpolar nao pode deslocar o horario planejado dos proprios pontos."""
        linha = _linha_de_teste(n_paradas=5)
        for parada in linha.paradas:
            self.assertAlmostEqual(
                linha.tempo_planejado_em(parada.posicao_m),
                parada.chegada_planejada_s, places=3)

    def test_referencia_continua_e_monotona(self) -> None:
        linha = _linha_de_teste(n_paradas=5)
        extensao = linha.extensao_m
        amostras = [linha.tempo_planejado_em(extensao * i / 50) for i in range(51)]
        self.assertEqual(amostras, sorted(amostras))

    def test_desvio_nao_tem_vies_sistematico(self) -> None:
        """
        Um veiculo rodando na velocidade de projeto deve ficar perto de zero ao
        longo de todo o percurso, e nao estruturalmente adiantado.
        """
        repo = Repositorio()
        linha = _linha_de_teste(n_paradas=5, extensao_m=3000.0)
        repo.salvar_linha(linha)
        central = CentralTelemetria(
            Veiculo(id="BUS-D", linha_id=linha.id, capacidade=50),
            linha, repo, "http://localhost:0")

        # Sem congestionamentos e com semente fixa: o teste mede so o vies da
        # referencia, sem que um atraso real sorteado seja confundido com ele.
        import unittest.mock as um
        random.seed(11)
        with um.patch.multiple(sys.modules[__name__],
                               TAXA_CONGESTIONAMENTO_POR_S=0.0,
                               TAXA_RETENCAO_PONTUAL_POR_S=0.0):
            desvios = [central.passo(2.0).schedule_deviation_s for _ in range(250)]
        media = statistics.fmean(desvios)
        self.assertLess(abs(media), 90.0,
                        f"desvio medio de {media:.1f}s indica vies na referencia")


def executar_testes() -> int:
    carregador = unittest.TestLoader()
    suite = carregador.loadTestsFromModule(sys.modules[__name__])
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if resultado.wasSuccessful() else 1


# =============================================================================
# 16. INICIALIZACAO
# =============================================================================

def iniciar_servidor(porta: int, offline: bool) -> Tuple[ThreadingHTTPServer, str]:
    """
    Sobe o gateway. Se a porta estiver ocupada, tenta as cinco seguintes em vez de
    abortar: numa apresentacao, uma porta presa por execucao anterior nao deve
    impedir a demonstracao.
    """
    ultimo_erro: Optional[OSError] = None
    for tentativa in range(6):
        alvo = porta + tentativa
        try:
            servidor = ThreadingHTTPServer((HOST, alvo), Gateway)
        except OSError as exc:
            ultimo_erro = exc
            print(f"[BOOT] porta {alvo} indisponivel, tentando a proxima ...")
            continue
        servidor.daemon_threads = True
        base_url = f"http://{HOST}:{alvo}"
        Gateway.offline = offline
        Gateway.base_url = base_url
        threading.Thread(target=servidor.serve_forever, name="HTTP-Gateway",
                         daemon=True).start()
        return servidor, base_url

    raise SystemExit(f"nenhuma porta disponivel a partir de {porta}: {ultimo_erro}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="MoveCidade - telemetria e inteligencia operacional de transporte publico")
    parser.add_argument("--porta", type=int, default=PORTA_PADRAO,
                        help=f"porta do gateway HTTP (padrao {PORTA_PADRAO})")
    parser.add_argument("--offline", action="store_true",
                        help="nao consulta a rede: usa o cache ou a malha viaria local")
    parser.add_argument("--sem-navegador", action="store_true",
                        help="nao abre o navegador automaticamente")
    parser.add_argument("--test", action="store_true",
                        help="executa a suite de testes automatizados e encerra")
    args = parser.parse_args(argv)

    if args.test:
        return executar_testes()

    print("=" * 78)
    print(" MoveCidade - Telemetria e Inteligencia Operacional de Transporte Publico")
    print(" Vulcan (IoT/Backend) · Kharon (Data/AI) · Iris (Frontend) · Hermes (Copiloto)")
    print(" Aegis (QA/LGPD) · Atlas (arquitetura e contratos)")
    print("=" * 78)

    servidor, base_url = iniciar_servidor(args.porta, True)
    print(f"[BOOT] gateway HTTP ouvindo em {base_url}")
    print("[BOOT] simulacao offline: nenhuma consulta de rede sera feita")

    bootstrap(True, base_url)

    print("-" * 78)
    print(f" Aplicacao .......... {base_url}/")
    print(f" Telemetria ......... GET  {base_url}/api/telemetria/atual")
    print(f" Stream (SSE) ....... GET  {base_url}/api/stream")
    print(f" Indicadores ........ GET  {base_url}/api/kpis")
    print(f" Resumo do turno .... GET  {base_url}/api/resumo")
    print(f" Ingestao IoT ....... POST {base_url}/api/iot/telemetria")
    print(f" CRUD ............... GET|POST|PUT|DELETE {base_url}/api/linhas e /api/veiculos")
    print(" Testes ............. python3 movecidade.py --test")
    print(" Ctrl+C para encerrar.")
    print("-" * 78)

    if not args.sem_navegador:
        try:
            webbrowser.open(f"{base_url}/")
        except Exception:
            print("[AVISO] nao foi possivel abrir o navegador; acesse a URL manualmente")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] encerrando centrais embarcadas e gateway ...")
        REPO.encerrar_simuladores()
        servidor.shutdown()
        servidor.server_close()
        print("[SHUTDOWN] MoveCidade finalizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
