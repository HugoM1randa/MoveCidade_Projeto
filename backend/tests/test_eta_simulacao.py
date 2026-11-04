"""Critério de aceite: o tempo previsto bate com a chegada real do ônibus no simulador (±20%)."""

import random

from movecidade.eta import eta_simulacao
from movecidade.simulador import CentralTelemetria


def test_previsao_bate_com_a_chegada_simulada(repo):
    rng = random.Random(7)
    erros = []
    for linha_id in ("azul-santa-rosa", "vermelha-monte-carlo"):
        linha = repo.linha(linha_id)
        ativos = repo.pontos_ativos_da_linha(linha)
        frota = repo.veiculos(linha_id)
        sims = [CentralTelemetria(v, repo, linha.comprimento * i / len(frota), semente=i + 1) for i, v in enumerate(frota)]
        for _ in range(180):                       # aquece o histórico de velocidade dos trechos
            for s in sims:
                s.passo(5.0)
        for _ in range(25):
            sim = rng.choice(sims)
            k = rng.randrange(len(linha.s_pontos))
            previsto = eta_simulacao(linha, repo.historico, ativos, sim.s, sim.parada_restante_s > 0, linha.s_pontos[k])
            if previsto < 120:
                for s in sims:
                    s.passo(5.0)
                continue
            t = 0.0
            while not (sim.parado_em == k and sim.parada_restante_s > 0) and t < 6000:
                for s in sims:
                    s.passo(5.0)
                t += 5.0
            erros.append((t - previsto) / previsto)
    dentro = sum(1 for e in erros if abs(e) <= 0.20) / len(erros)
    assert len(erros) >= 20
    assert dentro >= 0.75, f"só {dentro:.0%} das previsões ficaram dentro de ±20%"
