"""Pontos próximos ao pino de localização simulada (seção 5)."""

from movecidade.servicos import pontos_proximos

MATRIZ = (-21.60353, -48.36632)


def test_ordena_por_distancia_e_respeita_limite(repo):
    r = pontos_proximos(repo, *MATRIZ, raio=800, limite=3)
    pontos = r["pontos"]
    assert 1 <= len(pontos) <= 3
    assert pontos[0]["id"] == "centro"
    distancias = [p["distancia_m"] for p in pontos]
    assert distancias == sorted(distancias)
    assert all(d <= 800 for d in distancias)
    assert r["fora_do_raio"] is False


def test_tempo_a_pe_80_m_por_minuto(repo):
    p = pontos_proximos(repo, *MATRIZ)["pontos"][1]
    assert p["caminhada_min"] == max(1, round(p["distancia_m"] / 80))


def test_ponto_compartilhado_lista_todas_as_linhas(repo):
    centro = pontos_proximos(repo, *MATRIZ)["pontos"][0]
    assert {l["numero"] for l in centro["linhas"]} == {"Azul", "Verde", "Vermelha"}
    for l in centro["linhas"]:
        assert l["cor"].startswith("#") and l["fonte"] in ("ao_vivo", "programado", "sem_previsao")


def test_sem_ponto_no_raio_mostra_o_mais_proximo(repo):
    r = pontos_proximos(repo, -21.5600, -48.3000, raio=800)
    assert r["fora_do_raio"] is True
    assert len(r["pontos"]) == 1


def test_filtro_rampa_e_piso_tatil(repo):
    repo.ponto("av-15-de-novembro").acessibilidade.update(rampa=True, piso_tatil=True)
    r = pontos_proximos(repo, *MATRIZ, raio=3000, limite=10, rampa=True, piso_tatil=True)
    assert r["pontos"]
    for p in r["pontos"]:
        assert p["acessibilidade"]["rampa"] and p["acessibilidade"]["piso_tatil"]


def test_endpoint_nao_grava_localizacao(cliente, repo):
    r = cliente.get("/api/pontos/proximos", params={"lat": MATRIZ[0], "lon": MATRIZ[1]})
    assert r.status_code == 200
    with repo.banco._lock:
        tabelas = [t[0] for t in repo.banco._con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for tabela in tabelas:
        with repo.banco._lock:
            linhas = repo.banco._con.execute(f"SELECT * FROM {tabela}").fetchall()
        assert all(str(MATRIZ[0]) not in str(tuple(l)) or tabela == "pontos" for l in linhas)
