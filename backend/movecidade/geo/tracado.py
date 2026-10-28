"""
Resolução do traçado real das linhas.

Ordem de preferência (como no protótipo, com cache):
  1) cache local (dados/cache_rotas.json) e cache semente versionado (seed/tracados_cache.json);
  2) API pública OSRM (router.project-osrm.org) — polilinha real das vias;
  3) fallback offline: segmentos entre os próprios pontos, reamostrados.
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .. import config
from .geometria import Coordenada, reamostrar

CACHE_SEMENTE = Path(__file__).resolve().parent.parent / "seed" / "tracados_cache.json"


def chave_waypoints(waypoints: Sequence[Coordenada]) -> str:
    texto = ";".join(f"{lat:.5f},{lon:.5f}" for lat, lon in waypoints)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


class CacheRotas:
    """Cache de geometrias por conjunto de waypoints. Thread-safe."""

    def __init__(self, caminho: Path, semente: Optional[Path] = CACHE_SEMENTE) -> None:
        self._caminho = caminho
        self._lock = threading.Lock()
        self._dados: Dict[str, List[List[float]]] = {}
        for arquivo in (semente, caminho):
            if arquivo and arquivo.exists():
                try:
                    self._dados.update(json.loads(arquivo.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    pass

    def obter(self, waypoints: Sequence[Coordenada]) -> Optional[List[Coordenada]]:
        with self._lock:
            bruto = self._dados.get(chave_waypoints(waypoints))
        return [(p[0], p[1]) for p in bruto] if bruto else None

    def guardar(self, waypoints: Sequence[Coordenada], geometria: Sequence[Coordenada]) -> None:
        with self._lock:
            self._dados[chave_waypoints(waypoints)] = [[round(a, 6), round(b, 6)] for a, b in geometria]
            try:
                self._caminho.parent.mkdir(parents=True, exist_ok=True)
                self._caminho.write_text(json.dumps(self._dados), encoding="utf-8")
            except OSError:
                pass


def buscar_rota_osrm(waypoints: Sequence[Coordenada]) -> Optional[List[Coordenada]]:
    """Consulta o OSRM público. Devolve None em qualquer falha (offline, timeout, limite)."""
    if len(waypoints) < 2:
        return None
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    url = f"{config.OSRM_ENDPOINT}{coords}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MoveCidade-SmartCityLab/2.0"})
        with urllib.request.urlopen(req, timeout=config.OSRM_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if payload.get("code") != "Ok" or not payload.get("routes"):
        return None
    linha = payload["routes"][0]["geometry"]["coordinates"]  # [lon, lat]
    return [(float(lat), float(lon)) for lon, lat in linha]


def resolver_tracado(waypoints: Sequence[Coordenada], cache: CacheRotas,
                     usar_osrm: bool = True) -> Tuple[List[Coordenada], str]:
    """Resolve o traçado final. Devolve (rota_densa, origem) com origem em OSRM | CACHE | LOCAL."""
    if len(waypoints) < 2:
        return [tuple(w) for w in waypoints], "LOCAL"  # type: ignore[misc]
    em_cache = cache.obter(waypoints)
    if em_cache:
        return reamostrar(em_cache), "CACHE"
    if usar_osrm and config.OSRM_ATIVO:
        geometria = buscar_rota_osrm(waypoints)
        if geometria and len(geometria) >= 2:
            cache.guardar(waypoints, geometria)
            return reamostrar(geometria), "OSRM"
    return reamostrar(list(waypoints)), "LOCAL"
