"""Contrato de telemetria: campos exatos, tipos e intervalos → 422 com mensagem clara."""

import pytest

from .conftest import pacote


def test_pacote_valido_e_aceito(cliente, repo):
    r = cliente.post("/api/iot/telemetria", json=pacote(repo))
    assert r.status_code == 200
    assert r.json()["vehicle_id"] == "102-A"
    assert repo.ao_vivo("102-A")


@pytest.mark.parametrize("campo,valor,trecho", [
    ("latitude", "abc", "latitude"),
    ("latitude", 120.0, "latitude"),
    ("door_status", "HALF", "door_status"),
    ("anomaly_flag", "OUTRA", "anomaly_flag"),
    ("passenger_count", -3, "passenger_count"),
    ("route_progress", 1.5, "route_progress"),
    ("accessibility_button", "sim", "accessibility_button"),
])
def test_tipo_ou_intervalo_invalido(cliente, repo, campo, valor, trecho):
    r = cliente.post("/api/iot/telemetria", json=pacote(repo, **{campo: valor}))
    assert r.status_code == 422
    assert trecho in r.json()["erro"]


def test_campo_faltando(cliente, repo):
    dados = pacote(repo)
    del dados["speed_kmh"]
    r = cliente.post("/api/iot/telemetria", json=dados)
    assert r.status_code == 422
    assert "speed_kmh" in r.json()["erro"] and "obrigatório" in r.json()["erro"]


def test_campo_fora_do_contrato(cliente, repo):
    r = cliente.post("/api/iot/telemetria", json=pacote(repo, campo_novo=1))
    assert r.status_code == 422


def test_veiculo_desconhecido(cliente, repo):
    r = cliente.post("/api/iot/telemetria", json=pacote(repo, vehicle_id="XYZ-999"))
    assert r.status_code == 422
    assert "não está cadastrado" in r.json()["erro"]


def test_json_invalido(cliente):
    r = cliente.post("/api/iot/telemetria", content=b"{nao e json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_lotacao_critica_gera_alerta_e_so_executa_com_aceite(gestor, repo):
    antes = len(repo.veiculos("102"))
    repo.ingerir(pacote(repo, "102-A", passenger_count=70, occupancy_rate=1.13, occupancy_alert=True,
                        anomaly_flag="CRITICAL_OVERCROWDING"))
    pendentes = gestor.get("/api/gestor/alertas").json()["pendentes"]
    alerta = next(a for a in pendentes if a["tipo"] == "lotacao")
    assert len(repo.veiculos("102")) == antes          # nada executado sem aceite
    r = gestor.post(f"/api/gestor/alertas/{alerta['id']}/decisao", json={"decisao": "aceitar"})
    assert r.status_code == 200 and r.json()["decisao"] == "aceito"
    assert len(repo.veiculos("102")) == antes + 1      # reserva colocado após o aceite
    pendentes = gestor.get("/api/gestor/alertas").json()["pendentes"]
    assert all(a["id"] != alerta["id"] for a in pendentes)


def test_gestor_exige_login(cliente):
    assert cliente.get("/api/gestor/painel").status_code == 401
    assert cliente.post("/api/linhas", json={}).status_code == 401
