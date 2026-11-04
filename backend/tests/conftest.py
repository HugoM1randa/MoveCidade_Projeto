import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from movecidade import config  # noqa: E402

config.SIMULADOR_ATIVO = False
config.OSRM_ATIVO = False
config.GESTOR_SENHA = "senha-teste"

from fastapi.testclient import TestClient  # noqa: E402

from movecidade.geo.tracado import CacheRotas  # noqa: E402
from movecidade.main import criar_app  # noqa: E402
from movecidade.persistencia import Banco  # noqa: E402
from movecidade.repositorio import Repositorio  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    r = Repositorio(Banco(tmp_path / "teste.db"), CacheRotas(tmp_path / "cache.json"), usar_osrm=False)
    r.carregar()
    return r


@pytest.fixture
def cliente(repo):
    with TestClient(criar_app(repo, iniciar_simulador=False)) as c:
        yield c


@pytest.fixture
def gestor(cliente):
    r = cliente.post("/api/gestor/login", json={"usuario": config.GESTOR_USUARIO, "senha": "senha-teste"})
    assert r.status_code == 200
    return cliente


def pacote(repo, veiculo_id="AZ-SR-1", progresso=0.1, **extra):
    """Pacote de telemetria válido do contrato, posicionado em `progresso` da volta."""
    veiculo = repo.veiculo(veiculo_id)
    linha = repo.linha(veiculo.linha_id)
    base = {
        "timestamp": datetime.now(timezone.utc).isoformat(), "vehicle_id": veiculo_id, "route_id": linha.id,
        "trip_id": "TRIP-TESTE", "latitude": -21.60, "longitude": -48.36, "speed_kmh": 20.0,
        "door_status": "CLOSED", "passenger_count": 20, "passenger_capacity": veiculo.capacidade,
        "occupancy_rate": round(20 / veiculo.capacidade, 3), "occupancy_alert": False,
        "internal_temperature_c": 23.0, "accessibility_button": False, "is_at_stop": False,
        "anomaly_flag": "NONE", "current_stop": "A", "next_stop": "B", "distance_next_stop_m": 100.0,
        "eta_next_stop_s": 20.0, "segment_avg_speed_kmh": 20.0, "route_progress": progresso, "odometer_m": 10.0,
    }
    base.update(extra)
    return base
