"""Função serverless da Vercel: expõe a API FastAPI do MoveCidade em /api/*."""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

# Serverless: o disco é somente leitura, exceto /tmp. Simulador e cálculo de rota
# externo ficam desligados (o app mostra os horários programados).
os.environ.setdefault("MOVECIDADE_DADOS", "/tmp/movecidade")
os.environ.setdefault("SIMULADOR_ATIVO", "0")
os.environ.setdefault("OSRM_ATIVO", "0")
os.makedirs(os.environ["MOVECIDADE_DADOS"], exist_ok=True)

from movecidade import config  # noqa: E402
from movecidade.geo.tracado import CacheRotas  # noqa: E402
from movecidade.main import criar_app  # noqa: E402
from movecidade.persistencia import Banco  # noqa: E402
from movecidade.repositorio import Repositorio  # noqa: E402

_repo = Repositorio(Banco(config.CAMINHO_BANCO), CacheRotas(config.CAMINHO_CACHE_ROTAS))
_repo.carregar()

app = criar_app(repo=_repo, iniciar_simulador=False)
