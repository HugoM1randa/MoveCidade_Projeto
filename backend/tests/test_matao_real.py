"""Dados reais de Matão: três linhas (Azul, Verde, Vermelha), seis itinerários e quadros oficiais."""

from datetime import datetime

from movecidade.servicos import FUSO_MATAO, horarios_programados, quadro_oficial, tipo_de_dia
from movecidade.seed import matao_real


def test_so_existem_as_tres_linhas_de_matao(repo):
    assert {l.numero for l in repo.linhas()} == {"Azul", "Verde", "Vermelha"}
    assert {l.cor_nome for l in repo.linhas()} == {"azul", "verde", "vermelha"}
    assert len(repo.linhas()) == 6          # dois itinerários (sentidos) por linha


def test_cada_itinerario_comeca_no_centro_e_tem_quadro_oficial(repo):
    for linha in repo.linhas():
        assert linha.pontos[0] == "centro"
        q = quadro_oficial(linha)
        assert q and q["do_centro"]["uteis"] and q["para_centro"]["domingo"]


def test_horarios_oficiais_conferem_com_a_fonte():
    q = matao_real.quadro("azul-santa-rosa")
    assert q["do_centro"]["uteis"][:3] == ["07:05", "07:30", "08:35"]
    assert q["para_centro"]["sabado"][0] == "05:10"
    assert matao_real.quadro("vermelha-monte-carlo")["para_centro"]["uteis"][0] == "04:50"
    assert matao_real.quadro("verde-paraiso")["do_centro"]["uteis"][-1] == "18:30"


def test_tipo_de_dia():
    assert tipo_de_dia(datetime(2026, 10, 28).date()) == "uteis"     # quarta
    assert tipo_de_dia(datetime(2026, 10, 31).date()) == "sabado"
    assert tipo_de_dia(datetime(2026, 11, 1).date()) == "domingo"


def test_proxima_saida_do_centro_segue_o_quadro(repo):
    linha = repo.linha("azul-bairro-alto")
    agora = datetime(2026, 10, 28, 6, 40, tzinfo=FUSO_MATAO)           # quarta, 06:40
    h = horarios_programados(repo, linha, "centro", a_partir=agora, quantidade=2)
    assert [x.strftime("%H:%M") for x in h] == ["07:00", "08:00"]


def test_depois_da_ultima_saida_vai_para_o_dia_seguinte(repo):
    linha = repo.linha("azul-bairro-alto")
    agora = datetime(2026, 10, 30, 19, 0, tzinfo=FUSO_MATAO)           # sexta, depois das 18:30
    h = horarios_programados(repo, linha, "centro", a_partir=agora, quantidade=1)
    assert h[0].strftime("%a %H:%M") == "Sat 06:30"


def test_detalhe_da_linha_traz_o_quadro(cliente):
    r = cliente.get("/api/linhas/verde-sao-jose/detalhe")
    assert r.status_code == 200
    assert r.json()["quadro"]["tipo_dia_hoje"] in ("uteis", "sabado", "domingo")
    assert r.json()["linha"]["destino"] == "São José"
