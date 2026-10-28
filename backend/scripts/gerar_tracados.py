"""
Gera o cache semente de traçados (seed/tracados_cache.json) consultando o OSRM.

Rode quando mudar pontos ou linhas no arquivo seed/dados.py:
    python -m scripts.gerar_tracados      (de dentro da pasta backend)
Com o cache versionado, o app funciona offline com o traçado real das ruas.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from movecidade.geo.tracado import CACHE_SEMENTE, buscar_rota_osrm, chave_waypoints  # noqa: E402
from movecidade.seed import LINHAS, PONTOS  # noqa: E402


def main() -> None:
    pontos = {p["id"]: (p["lat"], p["lon"]) for p in PONTOS}
    dados = {}
    for linha in LINHAS:
        coords = [pontos[pid] for pid in linha["pontos"]]
        waypoints = coords + [coords[0]]
        geometria = buscar_rota_osrm(waypoints)
        if not geometria:
            print(f"Linha {linha['numero']}: OSRM indisponível — mantenha o cache anterior.")
            continue
        dados[chave_waypoints(waypoints)] = [[round(a, 6), round(b, 6)] for a, b in geometria]
        print(f"Linha {linha['numero']}: {len(geometria)} vértices")
        time.sleep(0.5)
    if dados:
        CACHE_SEMENTE.write_text(json.dumps(dados), encoding="utf-8")
        print(f"Gravado em {CACHE_SEMENTE}")


if __name__ == "__main__":
    main()
