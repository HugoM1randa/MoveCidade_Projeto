"""Validação de cor de linha: contraste ≥ 4,5:1 com branco e cor exclusiva."""

from movecidade.cores import contraste, validar_cor
from movecidade.seed import PALETA


def test_paleta_semente_passa_no_contraste():
    for item in PALETA:
        assert contraste(item["cor"], "#FFFFFF") >= 4.5, item


def test_cor_clara_e_reprovada():
    ok, msg = validar_cor("#38BDF8", [])   # cor do protótipo antigo
    assert not ok and "contraste" in msg


def test_cor_repetida_e_reprovada():
    ok, msg = validar_cor("#1d4ed8", ["#1D4ED8"])
    assert not ok and "já usa" in msg


def test_formato_invalido():
    ok, _ = validar_cor("azul", [])
    assert not ok


def test_cor_escura_nova_e_aprovada():
    ok, msg = validar_cor("#334155", [p["cor"] for p in PALETA])
    assert ok and msg is None


def test_api_recusa_linha_com_cor_ruim(gestor):
    r = gestor.post("/api/linhas", json={"numero": "410", "nome": "Teste", "cor": "#FDE047",
                                          "pontos": ["terminal", "hospital"]})
    assert r.status_code == 422
    assert "contraste" in r.json()["erro"]


def test_nova_linha_recebe_proxima_cor_livre(gestor):
    r = gestor.post("/api/linhas", json={"numero": "410", "nome": "Centro – Hospital",
                                          "pontos": ["terminal", "hospital"]})
    assert r.status_code == 201
    assert r.json()["cor"] == "#BE185D"   # primeira cor reserva da paleta
