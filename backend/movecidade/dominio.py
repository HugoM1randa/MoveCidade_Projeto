"""Modelo de domínio: pontos, linhas, veículos e o contrato de telemetria."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .geo import Coordenada


@dataclass
class Ponto:
    """Ponto de parada: entidade própria, compartilhada entre as linhas."""
    id: str
    nome: str
    referencia: str
    lat: float
    lon: float
    acessibilidade: Dict[str, bool] = field(default_factory=lambda: {"rampa": False, "piso_tatil": False, "abrigo": False})
    status: str = "operando"  # "operando" | "desativado"

    @property
    def coord(self) -> Coordenada:
        return (self.lat, self.lon)

    @property
    def operando(self) -> bool:
        return self.status == "operando"

    def to_dict(self, linhas_atendidas: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            "id": self.id, "nome": self.nome, "referencia": self.referencia,
            "lat": self.lat, "lon": self.lon,
            "acessibilidade": dict(self.acessibilidade), "status": self.status,
            "linhas_atendidas": linhas_atendidas or [],
        }


@dataclass
class Linha:
    """Linha de ônibus. `pontos` é a ordem do itinerário; o traçado é uma volta fechada."""
    id: str
    numero: str
    nome: str
    cor: str
    cor_nome: str
    padrao: str                      # continuo | tracejado | pontilhado | traco_ponto
    intervalo_min: int               # tabela programada: uma partida a cada N minutos
    pontos: List[str]
    # --- derivados do traçado (recalculados quando os pontos mudam) ---
    rota: List[Coordenada] = field(default_factory=list)
    acumulado: List[float] = field(default_factory=list)
    s_pontos: List[float] = field(default_factory=list)
    origem_tracado: str = "LOCAL"
    versao_tracado: int = 0

    @property
    def comprimento(self) -> float:
        return self.acumulado[-1] if self.acumulado else 0.0

    def resumo(self) -> Dict[str, Any]:
        return {
            "id": self.id, "numero": self.numero, "nome": self.nome,
            "cor": self.cor, "cor_nome": self.cor_nome, "padrao": self.padrao,
            "intervalo_min": self.intervalo_min,
        }


@dataclass
class Veiculo:
    id: str
    linha_id: str
    capacidade: int
    acessivel: bool = False
    ativo: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "linha_id": self.linha_id, "capacidade": self.capacidade,
                "acessivel": self.acessivel, "ativo": self.ativo}


class Telemetria(BaseModel):
    """
    Contrato de telemetria (exatamente os campos do protótipo). Tipos estritos e
    intervalos validados; qualquer desvio vira HTTP 422 com mensagem clara.
    """
    model_config = ConfigDict(strict=True, extra="forbid")

    timestamp: str = Field(min_length=10, max_length=40)
    vehicle_id: str = Field(min_length=1, max_length=40)
    route_id: str = Field(min_length=1, max_length=40)
    trip_id: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(ge=0, le=150)
    door_status: Literal["OPEN", "CLOSED"]
    passenger_count: int = Field(ge=0, le=400)
    passenger_capacity: int = Field(gt=0, le=400)
    occupancy_rate: float = Field(ge=0, le=3)
    occupancy_alert: bool
    internal_temperature_c: float = Field(ge=-20, le=70)
    accessibility_button: bool
    is_at_stop: bool
    anomaly_flag: Literal["NONE", "CRITICAL_OVERCROWDING", "UNEXPECTED_DELAY"]
    current_stop: str = Field(max_length=120)
    next_stop: str = Field(max_length=120)
    distance_next_stop_m: float = Field(ge=0)
    eta_next_stop_s: float = Field(ge=0)
    segment_avg_speed_kmh: float = Field(ge=0, le=150)
    route_progress: float = Field(ge=0, le=1)
    odometer_m: float = Field(ge=0)
