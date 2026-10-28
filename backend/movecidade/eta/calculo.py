"""
Previsão de chegada (ETA) de cada ônibus até QUALQUER ponto à frente na rota (seção 5.3).

Tempos internos estão no relógio da SIMULAÇÃO. `para_relogio_usuario` converte para o
relógio que o passageiro vê (÷ FATOR_TEMPO): quando a contagem chega a "agora", o ônibus
está chegando ao ponto no mapa.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Sequence, Tuple

from .. import config
from ..dominio import Linha

TOLERANCIA_M = 12.0       # folga para considerar que o ônibus "está" no ponto


def para_relogio_usuario(segundos_simulacao: float) -> float:
    return segundos_simulacao / config.FATOR_TEMPO


class HistoricoTrechos:
    """Velocidade média histórica por trecho (média móvel exponencial), compartilhada pela linha."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._medias: Dict[Tuple[str, int], float] = {}

    def registrar(self, linha_id: str, trecho: int, velocidade_kmh: float) -> None:
        """
        Média móvel exponencial (como no script), com amortecimento: uma passagem muito fora
        do normal (ex.: um ônibus preso num congestionamento) entra limitada a ±35% da média,
        para não distorcer sozinha a previsão dos próximos ônibus.
        """
        if velocidade_kmh <= 0.5:
            return
        with self._lock:
            anterior = self._medias.get((linha_id, trecho))
            if anterior is None:
                self._medias[(linha_id, trecho)] = velocidade_kmh
                return
            amostra = min(max(velocidade_kmh, anterior * 0.65), anterior * 1.35)
            self._medias[(linha_id, trecho)] = anterior * 0.7 + amostra * 0.3

    def media(self, linha_id: str, trecho: int) -> Optional[float]:
        with self._lock:
            return self._medias.get((linha_id, trecho))

    def limpar_linha(self, linha_id: str) -> None:
        with self._lock:
            for chave in [k for k in self._medias if k[0] == linha_id]:
                del self._medias[chave]


def _limites_trechos(linha: Linha) -> List[float]:
    """Trecho k vai do ponto k ao ponto k+1; o último vai do último ponto ao fim da volta."""
    return list(linha.s_pontos) + [linha.comprimento]


def _velocidade_ms(linha: Linha, historico: Optional[HistoricoTrechos], trecho: int) -> float:
    media = historico.media(linha.id, trecho) if historico else None
    kmh = media if media and media > 1.0 else config.VELOCIDADE_FALLBACK_KMH
    return kmh / 3.6


def tempo_percurso(linha: Linha, historico: Optional[HistoricoTrechos], s_de: float, s_ate: float) -> float:
    """Σ (comprimento de cada pedaço de trecho ÷ velocidade média histórica do trecho), em s de simulação."""
    if s_ate <= s_de:
        return 0.0
    limites = _limites_trechos(linha)
    total = 0.0
    for k in range(len(limites) - 1):
        ini, fim = limites[k], limites[k + 1]
        sobreposicao = min(fim, s_ate) - max(ini, s_de)
        if sobreposicao > 0:
            total += sobreposicao / _velocidade_ms(linha, historico, k)
    # pedaço antes do primeiro ponto (se o ponto 0 não estiver exatamente no início)
    if limites and s_de < limites[0]:
        total += (min(limites[0], s_ate) - s_de) / _velocidade_ms(linha, historico, len(limites) - 2)
    return total


def paradas_entre(linha: Linha, ativos: Sequence[bool], s_de: float, s_ate: float) -> int:
    """Número de paradas intermediárias (pontos operando) estritamente entre s_de e s_ate."""
    return sum(1 for s, ativo in zip(linha.s_pontos, ativos)
               if ativo and s_de + TOLERANCIA_M < s < s_ate - TOLERANCIA_M)


def eta_simulacao(linha: Linha, historico: Optional[HistoricoTrechos], ativos: Sequence[bool],
                  s_veiculo: float, em_parada: bool, s_ponto: float) -> float:
    """
    Tempo (s de simulação) para o veículo na posição `s_veiculo` chegar ao ponto em `s_ponto`.
    - Se s_P ≥ s_v: d = s_P − s_v.
    - Se o ônibus já passou: d = (C − s_v) + s_P, mais o tempo de retorno no terminal.
    Soma também o tempo médio de parada em cada ponto intermediário.
    """
    C = linha.comprimento
    if C <= 0:
        return 0.0
    s_inicio = linha.s_pontos[0] if linha.s_pontos else 0.0
    parado_no_terminal = em_parada and s_veiculo <= s_inicio + TOLERANCIA_M
    restante_parada = 0.0
    if em_parada:
        restante_parada = (config.RETORNO_TERMINAL_S if parado_no_terminal else config.PARADA_MEDIA_S) / 2

    if abs(s_ponto - s_veiculo) <= TOLERANCIA_M and (em_parada or s_ponto >= s_veiculo):
        return 0.0
    if s_ponto >= s_veiculo:
        t = tempo_percurso(linha, historico, s_veiculo, s_ponto)
        t += paradas_entre(linha, ativos, s_veiculo, s_ponto) * config.PARADA_MEDIA_S
        return t + restante_parada

    # já passou: termina a volta, regula no terminal e vem de novo até o ponto
    t = tempo_percurso(linha, historico, s_veiculo, C)
    t += paradas_entre(linha, ativos, s_veiculo, C + TOLERANCIA_M * 2) * config.PARADA_MEDIA_S
    if s_ponto > s_inicio + TOLERANCIA_M:
        t += config.RETORNO_TERMINAL_S
        t += tempo_percurso(linha, historico, 0.0, s_ponto)
        t += paradas_entre(linha, ativos, s_inicio, s_ponto) * config.PARADA_MEDIA_S
    return t + restante_parada


def tempo_planejado_simulacao(linha: Linha, ativos: Sequence[bool], s_de: float, s_ate: float) -> float:
    """Tempo da tabela programada (velocidade planejada fixa + paradas), em s de simulação."""
    if s_ate <= s_de:
        return 0.0
    t = (s_ate - s_de) / (config.VELOCIDADE_PLANEJADA_KMH / 3.6)
    return t + paradas_entre(linha, ativos, s_de, s_ate) * config.PARADA_MEDIA_S


def classificar_lotacao(taxa: float) -> str:
    if taxa < 0.40:
        return "baixa"
    if taxa < config.LIMITE_ALERTA_OCUPACAO:
        return "media"
    return "alta"
