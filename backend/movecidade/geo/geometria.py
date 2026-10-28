"""Geometria das rotas (reaproveitada do protótipo script_ramon.py e estendida)."""

from __future__ import annotations

import bisect
import math
from typing import List, Sequence, Tuple

from ..config import ESPACAMENTO_ROTA_M

Coordenada = Tuple[float, float]  # (latitude, longitude)

RAIO_TERRA_M = 6_371_000.0


def haversine_m(a: Coordenada, b: Coordenada) -> float:
    """Distância geodésica em metros entre duas coordenadas (lat, lon)."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(min(1.0, h)))


def reamostrar(caminho: Sequence[Coordenada], espacamento_m: float = ESPACAMENTO_ROTA_M) -> List[Coordenada]:
    """
    Densifica o traçado inserindo pontos a cada `espacamento_m` SOMENTE entre vértices
    consecutivos da via. Os vértices originais são mantidos, então as curvas e esquinas
    ficam exatamente onde a rua está.
    """
    if len(caminho) < 2:
        return [(p[0], p[1]) for p in caminho]

    saida: List[Coordenada] = [(caminho[0][0], caminho[0][1])]
    for i in range(len(caminho) - 1):
        p, q = caminho[i], caminho[i + 1]
        comprimento = haversine_m(p, q)
        if comprimento <= 0.01:
            continue
        percorrido = espacamento_m
        while percorrido < comprimento - 1.0:
            t = percorrido / comprimento
            saida.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
            percorrido += espacamento_m
        saida.append((q[0], q[1]))
    return saida


def distancias_acumuladas(rota: Sequence[Coordenada]) -> List[float]:
    """Vetor de distâncias acumuladas (m) do início da rota até cada vértice."""
    acumulado: List[float] = [0.0]
    for i in range(len(rota) - 1):
        acumulado.append(acumulado[-1] + haversine_m(rota[i], rota[i + 1]))
    return acumulado


def posicao_em(rota: Sequence[Coordenada], acumulado: Sequence[float], s: float) -> Coordenada:
    """Converte posição curvilínea `s` (m) em (lat, lon), interpolando dentro do trecho."""
    if len(rota) < 2:
        return rota[0] if rota else (0.0, 0.0)
    s = max(0.0, min(s, acumulado[-1]))
    i = min(max(bisect.bisect_right(acumulado, s) - 1, 0), len(rota) - 2)
    trecho = acumulado[i + 1] - acumulado[i]
    t = 0.0 if trecho <= 0 else (s - acumulado[i]) / trecho
    p, q = rota[i], rota[i + 1]
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def _projetar_no_segmento(p: Coordenada, a: Coordenada, b: Coordenada) -> Tuple[float, float]:
    """Projeta `p` no segmento a→b. Devolve (distância em m, fração t ∈ [0,1])."""
    lat0 = math.radians((a[0] + b[0]) / 2)
    kx = math.cos(lat0) * 111_320.0
    ky = 110_540.0
    ax, ay = a[1] * kx, a[0] * ky
    bx, by = b[1] * kx, b[0] * ky
    px, py = p[1] * kx, p[0] * ky
    dx, dy = bx - ax, by - ay
    comp2 = dx * dx + dy * dy
    t = 0.0 if comp2 <= 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / comp2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy), t


def projetar_paradas(rota: Sequence[Coordenada], acumulado: Sequence[float],
                     pontos: Sequence[Coordenada], folga_m: float = 15.0) -> List[float]:
    """
    Projeta cada ponto (na ordem do itinerário) sobre o traçado e devolve a posição
    curvilínea `s` (m) de cada um, sempre crescente.

    Diferente do script original (vértice mais próximo em toda a rota), a busca é
    monotônica: começa onde o ponto anterior ficou e escolhe a PRIMEIRA passagem que
    esteja quase tão perto quanto a melhor. Isso evita que, numa rota de ida e volta
    pela mesma rua, um ponto da ida seja projetado na volta.
    """
    if len(rota) < 2:
        return [0.0 for _ in pontos]
    posicoes: List[float] = []
    inicio = 0
    for ponto in pontos:
        medidas = []
        for i in range(inicio, len(rota) - 1):
            d, t = _projetar_no_segmento(ponto, rota[i], rota[i + 1])
            medidas.append((i, d, t))
        if not medidas:
            posicoes.append(acumulado[-1])
            continue
        melhor = min(m[1] for m in medidas)
        escolhido = next(m for m in medidas if m[1] <= melhor + folga_m)
        # desce até o mínimo local dessa passagem
        idx = medidas.index(escolhido)
        while idx + 1 < len(medidas) and medidas[idx + 1][1] < medidas[idx][1]:
            idx += 1
        i, _, t = medidas[idx]
        s = acumulado[i] + t * (acumulado[i + 1] - acumulado[i])
        if posicoes and s < posicoes[-1]:
            s = posicoes[-1]
        posicoes.append(s)
        inicio = i
    return posicoes
