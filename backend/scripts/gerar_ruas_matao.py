"""
Descobre a posição das ruas dos itinerários oficiais de Matão (OpenStreetMap / Nominatim) e grava
seed/ruas_matao.json. Rode uma vez, com internet, e versione o arquivo gerado:

    cd backend
    python -m scripts.gerar_ruas_matao          # só as ruas que ainda não têm posição
    python -m scripts.gerar_ruas_matao --tudo   # refaz todas
    python -m scripts.gerar_tracados            # depois: regrava o traçado real das ruas (OSRM)
    # (o script apaga backend/dados/movecidade.db para o app recarregar linhas e pontos)

Só entram posições dentro da área urbana de Matão. Rua não encontrada é listada no final e
simplesmente não vira parada: o script nunca inventa coordenadas.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from movecidade.seed import matao_real as m  # noqa: E402

ENDPOINT = "https://nominatim.openstreetmap.org/search"
# Caixa da área urbana de Matão (oeste, norte, leste, sul)
VIEWBOX = (-48.46, -21.54, -48.30, -21.68)
ABREVIACOES = (("Av. ", "Avenida "), ("Rod. ", "Rodovia "), ("Ver. ", "Vereador "), ("Cor. ", "Coronel "),
               ("Dr. ", "Doutor "), ("G. ", ""), ("Jorn. ", "Jornalista "), ("Prof. ", "Professor "))


def nome_completo(rua: str) -> str:
    for curto, longo in ABREVIACOES:
        rua = rua.replace(curto, longo)
    return rua.strip()


def buscar(rua: str):
    params = {"street": nome_completo(rua), "city": "Matão", "state": "São Paulo", "country": "Brasil",
              "format": "jsonv2", "limit": "5", "bounded": "1",
              "viewbox": f"{VIEWBOX[0]},{VIEWBOX[1]},{VIEWBOX[2]},{VIEWBOX[3]}"}
    req = urllib.request.Request(f"{ENDPOINT}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "MoveCidade-SmartCityLab/2.0 (projeto acadêmico)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        achados = json.loads(resp.read().decode("utf-8"))
    for a in achados:
        lat, lon = float(a["lat"]), float(a["lon"])
        if VIEWBOX[0] <= lon <= VIEWBOX[2] and VIEWBOX[3] <= lat <= VIEWBOX[1]:
            return round(lat, 5), round(lon, 5)
    return None


def main() -> None:
    refazer = "--tudo" in sys.argv
    atual = json.loads(m.ARQUIVO_RUAS.read_text(encoding="utf-8")) if m.ARQUIVO_RUAS.exists() else {}
    ruas = list(dict.fromkeys(r for item in m.LINHAS_REAIS for r in item["ruas"]))
    faltam, nao_achadas = [r for r in ruas if refazer or (r not in atual and r not in m.ANCORAS)], []
    print(f"{len(faltam)} rua(s) para localizar …")
    for rua in faltam:
        try:
            pos = buscar(rua)
        except OSError as erro:
            print(f"  ! {rua}: sem conexão ({erro}). Rode de novo mais tarde.")
            break
        if pos:
            atual[rua] = list(pos)
            print(f"  ✓ {rua}: {pos[0]}, {pos[1]}")
        else:
            nao_achadas.append(rua)
            print(f"  ✗ {rua}: não encontrada")
        time.sleep(1.1)  # política de uso do Nominatim: no máximo 1 requisição por segundo
    m.ARQUIVO_RUAS.write_text(json.dumps(atual, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Gravado em {m.ARQUIVO_RUAS} ({len(atual)} ruas).")
    banco = Path(__file__).resolve().parent.parent / "dados" / "movecidade.db"
    if banco.exists():
        banco.unlink()
        print("Banco antigo apagado: as linhas e pontos serão recarregados na próxima execução.")
    if nao_achadas:
        print("Sem posição (não viram parada):", "; ".join(nao_achadas))


if __name__ == "__main__":
    main()
