"""ETA até qualquer ponto (seção 5.3), incluindo o caso "o ônibus já passou"."""

import pytest

from movecidade import config
from movecidade.eta import HistoricoTrechos, eta_simulacao, para_relogio_usuario
from movecidade.servicos import previsao_linha_no_ponto

from .conftest import pacote


def test_ponto_a_frente_usa_velocidade_fallback(repo):
    linha = repo.linha("102")
    ativos = repo.pontos_ativos_da_linha(linha)
    s_v = 100.0
    s_p = linha.s_pontos[2]  # Rodoviária, com 1 parada intermediária (Escola)
    t = eta_simulacao(linha, HistoricoTrechos(), ativos, s_v, False, s_p)
    esperado = (s_p - s_v) / (config.VELOCIDADE_FALLBACK_KMH / 3.6) + 1 * config.PARADA_MEDIA_S
    assert t == pytest.approx(esperado, rel=1e-6)


def test_usa_velocidade_historica_do_trecho(repo):
    linha = repo.linha("102")
    ativos = repo.pontos_ativos_da_linha(linha)
    hist = HistoricoTrechos()
    hist.registrar("102", 0, 36.0)  # 10 m/s no primeiro trecho
    s_p = linha.s_pontos[1]
    t = eta_simulacao(linha, hist, ativos, 0.0, False, s_p)
    assert t == pytest.approx(s_p / 10.0, rel=1e-6)


def test_onibus_ja_passou_espera_a_proxima_volta(repo):
    linha = repo.linha("102")
    ativos = repo.pontos_ativos_da_linha(linha)
    hist = HistoricoTrechos()
    s_p = linha.s_pontos[1]
    antes = eta_simulacao(linha, hist, ativos, s_p - 200, False, s_p)
    depois = eta_simulacao(linha, hist, ativos, s_p + 200, False, s_p)
    assert depois > antes
    # d = (C − s_v) + s_P, mais retorno no terminal e as paradas no caminho
    minimo = ((linha.comprimento - (s_p + 200)) + s_p) / (config.VELOCIDADE_FALLBACK_KMH / 3.6)
    assert depois >= minimo + config.RETORNO_TERMINAL_S


def test_onibus_parado_no_ponto_chega_agora(repo):
    linha = repo.linha("102")
    ativos = repo.pontos_ativos_da_linha(linha)
    s_p = linha.s_pontos[2]
    assert eta_simulacao(linha, HistoricoTrechos(), ativos, s_p, True, s_p) == 0.0


def test_conversao_para_relogio_do_usuario(monkeypatch):
    monkeypatch.setattr(config, "FATOR_TEMPO", 4.0)
    assert para_relogio_usuario(240.0) == 60.0


def test_previsao_ao_vivo_menor_e_seguinte(repo):
    linha = repo.linha("102")
    for vid, prog in (("102-A", 0.02), ("102-B", 0.5), ("102-C", 0.9)):
        repo.ingerir(pacote(repo, vid, progresso=prog))
    p = previsao_linha_no_ponto(repo, linha, "rodoviaria")
    assert p["fonte"] == "ao_vivo"
    assert p["veiculo_id"] == "102-A"          # o mais próximo antes do ponto
    assert p["eta_seguinte_s"] > p["eta_s"]


def test_sem_telemetria_recente_vira_programado(repo, monkeypatch):
    linha = repo.linha("102")
    repo.ingerir(pacote(repo, "102-A", progresso=0.02))
    monkeypatch.setattr(config, "SEM_SINAL_APOS_S", -1.0)   # todo sinal já está "velho"
    p = previsao_linha_no_ponto(repo, linha, "rodoviaria")
    assert p["fonte"] in ("programado", "sem_previsao")
    assert p["fonte"] != "ao_vivo"
