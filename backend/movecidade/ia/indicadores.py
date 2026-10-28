"""
Indicadores do gestor (PDF, seção 6), calculados a partir da telemetria simulada.

Regras operacionais (tolerâncias) usam o relógio da simulação; os valores exibidos são
convertidos para o relógio do usuário, o mesmo em que ele vê os ônibus andarem.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

from .. import config


class Indicadores:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chegadas: Deque[Tuple[float, bool]] = deque(maxlen=300)   # (desvio_sim_s, no_horario)
        self._viagens: Deque[float] = deque(maxlen=60)                   # duração em s de simulação
        self._ocupacao_hora: Dict[int, List[float]] = {}                 # hora -> [soma, n]

    def registrar_chegada(self, desvio_sim_s: float) -> None:
        no_horario = -60.0 <= desvio_sim_s <= config.ATRASO_TOLERANCIA_S
        with self._lock:
            self._chegadas.append((desvio_sim_s, no_horario))

    def registrar_viagem(self, duracao_sim_s: float) -> None:
        if duracao_sim_s > 0:
            with self._lock:
                self._viagens.append(duracao_sim_s)

    def registrar_ocupacao(self, taxa: float, hora: Optional[int] = None) -> None:
        hora = datetime.now().hour if hora is None else hora
        with self._lock:
            acumulado = self._ocupacao_hora.setdefault(hora, [0.0, 0])
            acumulado[0] += min(taxa, 1.2)
            acumulado[1] += 1

    def instantaneo(self, *, ativos: int, cadastrados: int, intervalos_sim_s: List[float],
                    duracao_estimada_sim_s: Optional[float]) -> Dict[str, Any]:
        with self._lock:
            chegadas = list(self._chegadas)
            viagens = list(self._viagens)
            ocupacao = {h: (v[0] / v[1]) for h, v in self._ocupacao_hora.items() if v[1]}
        hora = datetime.now().hour

        pontualidade = (round(100 * sum(1 for _, ok in chegadas if ok) / len(chegadas)) if chegadas else None)
        espera_min = (round(sum(intervalos_sim_s) / len(intervalos_sim_s) / 2 / config.FATOR_TEMPO / 60, 1)
                      if intervalos_sim_s else None)
        ocup_atual = round(100 * ocupacao[hora]) if hora in ocupacao else None
        if viagens:
            duracao_min, duracao_fonte = round(sum(viagens) / len(viagens) / config.FATOR_TEMPO / 60, 1), "medida"
        elif duracao_estimada_sim_s:
            duracao_min, duracao_fonte = round(duracao_estimada_sim_s / config.FATOR_TEMPO / 60, 1), "estimada"
        else:
            duracao_min, duracao_fonte = None, "sem dados"
        disponibilidade = round(100 * ativos / cadastrados) if cadastrados else None

        return {
            "pontualidade": {
                "valor": pontualidade, "unidade": "%", "amostras": len(chegadas),
                "ajuda": "Parcela das chegadas aos pontos que aconteceram no horário programado "
                         "(até 2 minutos de atraso de operação).",
            },
            "tempo_espera": {
                "valor": espera_min, "unidade": "min",
                "ajuda": "Tempo médio que um passageiro espera no ponto: metade do intervalo atual "
                         "entre ônibus da mesma linha.",
            },
            "ocupacao_horario": {
                "valor": ocup_atual, "unidade": "%", "hora": hora,
                "por_hora": [{"hora": h, "valor": round(100 * v)} for h, v in sorted(ocupacao.items())],
                "ajuda": "Ocupação média dos ônibus (passageiros ÷ capacidade) na hora atual.",
            },
            "duracao_viagem": {
                "valor": duracao_min, "unidade": "min", "fonte": duracao_fonte, "amostras": len(viagens),
                "ajuda": "Tempo médio para um ônibus completar a volta inteira da linha, "
                         "sem contar a parada no terminal.",
            },
            "disponibilidade": {
                "valor": disponibilidade, "unidade": "%", "ativos": ativos, "cadastrados": cadastrados,
                "ajuda": "Parcela dos ônibus cadastrados que estão operando e enviando sinal agora.",
            },
        }
