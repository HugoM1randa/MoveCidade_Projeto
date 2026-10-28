"""
Central de telemetria embarcada — uma thread por ônibus (lógica do protótipo script_ramon.py).

Mudanças em relação ao script:
- os eventos aleatórios usam taxas por segundo de simulação (não por "tique"), então o
  comportamento não muda quando FATOR_TEMPO muda;
- a rota é uma volta fechada: ao terminar, o ônibus regula no terminal e começa nova viagem
  (sem "teletransporte" do fim para o início);
- as paradas são os pontos compartilhados da linha (pontos desativados são pulados);
- o tempo de parada é medido em segundos de simulação, o mesmo valor médio usado no ETA;
- o pacote é publicado pelo mesmo caminho de ingestão/validação do POST /api/iot/telemetria.
"""

from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from .. import config
from ..dominio import Linha, Veiculo
from ..eta import eta_simulacao, para_relogio_usuario
from ..geo import posicao_em

if TYPE_CHECKING:  # pragma: no cover
    from ..repositorio import Repositorio

RAIO_CHEGADA_M = 10.0
TAXA_RETENCAO_POR_S = 1 / 900.0         # congestionamento / semáforo longo
TAXA_SOBRELOTACAO_POR_S = 1 / 2400.0
TAXA_FALHA_GPS_POR_S_REAL = 1 / 1500.0  # perda de sinal (relógio real)
PROB_BOTAO_ACESSIBILIDADE = 0.03        # por chegada a ponto (pedido feito a bordo)


def probabilidade(taxa_por_s: float, dt_s: float) -> float:
    return 1.0 - math.exp(-taxa_por_s * dt_s)


def fator_demanda(hora: int) -> float:
    """Demanda de embarque por horário (picos da manhã e do fim da tarde)."""
    if 6 <= hora < 9 or 17 <= hora < 19:
        return 1.6
    if 11 <= hora < 14:
        return 1.2
    if hora >= 22 or hora < 5:
        return 0.4
    return 0.9


class CentralTelemetria(threading.Thread):
    def __init__(self, veiculo: Veiculo, repo: "Repositorio", s_inicial: float = 0.0,
                 semente: Optional[int] = None) -> None:
        super().__init__(name=f"IoT-{veiculo.id}", daemon=True)
        self.veiculo = veiculo
        self._repo = repo
        self._parar = threading.Event()
        self._cmd = threading.Lock()
        self._rng = random.Random(semente)

        self._versao_tracado = -1
        self._comprimento_anterior = 0.0
        self.s = s_inicial
        self.idx: Optional[int] = None          # índice (em linha.pontos) do ponto-alvo; None = fim da volta
        self.parado_em: Optional[int] = None    # índice do ponto onde está parado
        self.no_terminal = False
        self.parada_restante_s = 0.0
        self.retencao_s = 0.0
        self.sobrelotacao_s = 0.0
        self.segurar_s = 0.0
        self.velocidade = 0.0
        self.odometro = 0.0
        self.passageiros = max(3, int(veiculo.capacidade * self._rng.uniform(0.15, 0.40)))
        self.temperatura = round(self._rng.uniform(22.0, 25.0), 1)
        self.botao_acessibilidade = False
        self.pedido_passageiro_ate = 0.0
        self.sem_sinal_ate = 0.0
        self.trip_id = self._novo_trip_id()
        self._amostras: List[float] = []
        self._trecho_inicio: Optional[int] = None
        self._ultimo_ponto: Optional[int] = None

    # ----------------------------------------------------------------- comandos
    def encerrar(self) -> None:
        self._parar.set()

    def pedir_acessibilidade(self) -> None:
        """Botão de acessibilidade acionado pelo passageiro no app."""
        with self._cmd:
            self.pedido_passageiro_ate = time.monotonic() + 12.0

    def confirmar_acessibilidade(self) -> None:
        with self._cmd:
            self.pedido_passageiro_ate = 0.0
            self.botao_acessibilidade = False

    def segurar(self, segundos_simulacao: float) -> None:
        """Retém o ônibus por mais tempo no próximo ponto (regularização de intervalo)."""
        with self._cmd:
            self.segurar_s += segundos_simulacao

    def sem_sinal(self) -> bool:
        return time.monotonic() < self.sem_sinal_ate

    # ---------------------------------------------------------------- utilidades
    def _novo_trip_id(self) -> str:
        return f"TRIP-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{self.veiculo.id}"

    def _pontos_ativos(self, linha: Linha) -> List[bool]:
        return self._repo.pontos_ativos_da_linha(linha)

    def _proximo_alvo(self, linha: Linha, ativos: List[bool], depois_de_s: float) -> Optional[int]:
        for i, s in enumerate(linha.s_pontos):
            if ativos[i] and s > depois_de_s + 1.0:
                return i
        return None

    def _sincronizar_tracado(self, linha: Linha, ativos: List[bool]) -> None:
        """Se o traçado mudou (gestor editou a linha), reposiciona o ônibus proporcionalmente."""
        if linha.versao_tracado == self._versao_tracado:
            return
        if self._versao_tracado >= 0 and linha.comprimento > 0:
            progresso = min(1.0, self.s / max(1.0, self._comprimento_anterior))
            self.s = progresso * linha.comprimento
        self._versao_tracado = linha.versao_tracado
        self._comprimento_anterior = linha.comprimento
        self.parada_restante_s = 0.0
        self.parado_em = None
        self.no_terminal = False
        self.idx = self._proximo_alvo(linha, ativos, self.s - 1.5)
        self._amostras = []
        self._trecho_inicio = None

    def _fechar_trechos(self, linha: Linha, ate_trecho_exclusivo: int) -> None:
        """Consolida a velocidade média dos trechos percorridos desde o último ponto."""
        if self._amostras and self._trecho_inicio is not None:
            media = sum(self._amostras) / len(self._amostras)
            for k in range(self._trecho_inicio, ate_trecho_exclusivo):
                self._repo.historico.registrar(linha.id, k, media)
        self._amostras = []

    def _nome(self, linha: Linha, indice: Optional[int]) -> str:
        if indice is None:
            indice = 0
        if 0 <= indice < len(linha.pontos):
            ponto = self._repo.ponto(linha.pontos[indice])
            if ponto:
                return ponto.nome
        return "—"

    # ---------------------------------------------------------------- ciclo
    def run(self) -> None:
        self._parar.wait(self._rng.uniform(0.2, 1.4))
        while not self._parar.is_set():
            intervalo = self._rng.uniform(config.INTERVALO_MIN_S, config.INTERVALO_MAX_S)
            pacote = self.passo(intervalo * config.FATOR_TEMPO)
            agora = time.monotonic()
            if (config.FALHA_GPS_ATIVA and agora >= self.sem_sinal_ate
                    and self._rng.random() < probabilidade(TAXA_FALHA_GPS_POR_S_REAL, intervalo)):
                self.sem_sinal_ate = agora + self._rng.uniform(15.0, 25.0)
            if pacote is not None and not self.sem_sinal():
                try:
                    self._repo.ingerir(pacote)
                except Exception:  # a central embarcada nunca pode cair por erro no gateway
                    pass
            self._parar.wait(intervalo)

    def passo(self, dt: float) -> Optional[dict]:
        """Avança `dt` segundos de simulação e devolve o pacote de telemetria (dict do contrato)."""
        linha = self._repo.linha(self.veiculo.linha_id)
        if linha is None or linha.comprimento <= 0 or not linha.s_pontos:
            return None
        ativos = self._pontos_ativos(linha)
        self._sincronizar_tracado(linha, ativos)
        cap = self.veiculo.capacidade
        rng = self._rng
        hora = datetime.now().hour

        # --- anomalias com duração (Kharon) ------------------------------------
        if self.sobrelotacao_s > 0:
            self.sobrelotacao_s -= dt
        elif rng.random() < probabilidade(TAXA_SOBRELOTACAO_POR_S, dt):
            self.sobrelotacao_s = rng.uniform(40, 90)
            self.passageiros = rng.randint(int(cap * 0.96), cap + 6)
        if self.retencao_s > 0:
            self.retencao_s -= dt
        elif self.parada_restante_s <= 0 and rng.random() < probabilidade(TAXA_RETENCAO_POR_S, dt):
            self.retencao_s = rng.uniform(40, 120)

        with self._cmd:
            pedido_passageiro = time.monotonic() < self.pedido_passageiro_ate

        if self.parada_restante_s > 0:
            # --- parado no ponto: porta aberta, embarque e desembarque ------------
            em_parada = True
            self.velocidade = 0.0
            portas = "OPEN"
            desembarque = sum(1 for _ in range(self.passageiros) if rng.random() < 0.025 * dt)
            embarque = int(rng.uniform(0, 2 * 0.9 * fator_demanda(hora) * dt) + 0.5)
            if self.sobrelotacao_s > 0:
                desembarque = 0
            self.passageiros = max(0, min(cap + 8, self.passageiros - desembarque + embarque))
            self.temperatura += 0.04 * dt
            self.parada_restante_s -= dt
            if self.parada_restante_s <= 0:
                self.parada_restante_s = 0.0
                if self.no_terminal:
                    self.no_terminal = False
                    self.trip_id = self._novo_trip_id()
                self._ultimo_ponto = self.parado_em
                self._trecho_inicio = self.parado_em
                self.idx = self._proximo_alvo(linha, ativos, self.s)
                self.parado_em = None
                self.botao_acessibilidade = False
                portas = "CLOSED"
        else:
            em_parada = False
            portas = "CLOSED"
            if self.retencao_s > 0:
                self.velocidade = round(rng.uniform(0.0, 6.0), 1)
            else:
                alvo = rng.uniform(14.0, 36.0)
                self.velocidade = round(max(0.0, self.velocidade * 0.6 + alvo * 0.4), 1)
            avanco = (self.velocidade / 3.6) * dt
            self.s += avanco
            self.odometro += avanco
            self._amostras.append(self.velocidade)
            self.temperatura -= 0.02 * dt if self.temperatura > 23.0 else -0.008 * dt

            alvo_s = linha.s_pontos[self.idx] if self.idx is not None else linha.comprimento
            if self.s >= alvo_s - RAIO_CHEGADA_M:
                if self.idx is None:
                    # fim da volta: regula no terminal (primeiro ponto) e inicia nova viagem
                    self._fechar_trechos(linha, len(linha.s_pontos))
                    self.s = linha.s_pontos[0]
                    self.parado_em = 0
                    self.no_terminal = True
                    self.parada_restante_s = config.RETORNO_TERMINAL_S
                else:
                    self._fechar_trechos(linha, self.idx)
                    self.s = alvo_s
                    self.parado_em = self.idx
                    with self._cmd:
                        extra, self.segurar_s = self.segurar_s, 0.0
                    self.parada_restante_s = rng.uniform(config.PARADA_MIN_S, config.PARADA_MAX_S) + extra
                    if rng.random() < PROB_BOTAO_ACESSIBILIDADE:
                        self.botao_acessibilidade = True
                em_parada = True
                self.velocidade = 0.0
                portas = "OPEN"

        self.temperatura = round(max(19.5, min(31.0, self.temperatura)), 1)
        ocupacao = round(self.passageiros / cap, 3) if cap else 0.0
        anomalia = "NONE"
        if self.sobrelotacao_s > 0:
            anomalia = "CRITICAL_OVERCROWDING"
        elif self.retencao_s > 0 and not em_parada:
            anomalia = "UNEXPECTED_DELAY"

        if em_parada:
            atual_idx = self.parado_em
            proximo_idx = self._proximo_alvo(linha, ativos, self.s)
        else:
            atual_idx = self._ultimo_ponto
            proximo_idx = self.idx
        alvo_s = linha.s_pontos[proximo_idx] if proximo_idx is not None else linha.comprimento
        if proximo_idx is None:
            proximo_idx = 0  # depois do último ponto, o próximo é o terminal de origem
        distancia = max(0.0, alvo_s - self.s)
        eta_sim = eta_simulacao(linha, self._repo.historico, ativos, self.s, em_parada,
                                linha.s_pontos[proximo_idx])
        media_trecho = self._repo.historico.media(linha.id, self.idx if self.idx is not None else len(linha.s_pontos) - 1)
        lat, lon = posicao_em(linha.rota, linha.acumulado, self.s)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vehicle_id": self.veiculo.id,
            "route_id": linha.id,
            "trip_id": self.trip_id,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "speed_kmh": float(self.velocidade),
            "door_status": portas,
            "passenger_count": int(self.passageiros),
            "passenger_capacity": int(cap),
            "occupancy_rate": float(ocupacao),
            "occupancy_alert": ocupacao > config.LIMITE_ALERTA_OCUPACAO,
            "internal_temperature_c": float(self.temperatura),
            "accessibility_button": bool(self.botao_acessibilidade or pedido_passageiro),
            "is_at_stop": em_parada,
            "anomaly_flag": anomalia,
            "current_stop": self._nome(linha, atual_idx) if atual_idx is not None else "—",
            "next_stop": self._nome(linha, proximo_idx),
            "distance_next_stop_m": round(distancia, 1),
            "eta_next_stop_s": round(para_relogio_usuario(eta_sim), 1),
            "segment_avg_speed_kmh": round(float(media_trecho or config.VELOCIDADE_FALLBACK_KMH), 1),
            "route_progress": round(min(1.0, self.s / linha.comprimento), 6),
            "odometer_m": round(self.odometro, 1),
        }
