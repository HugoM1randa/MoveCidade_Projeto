"""Configuração central do MoveCidade, lida de variáveis de ambiente (e do arquivo .env na raiz)."""

from __future__ import annotations

import os
from pathlib import Path

RAIZ_BACKEND = Path(__file__).resolve().parent.parent
RAIZ_PROJETO = RAIZ_BACKEND.parent


def _carregar_dotenv() -> None:
    """Lê o .env da raiz do projeto sem dependências externas. Variáveis já definidas prevalecem."""
    arquivo = RAIZ_PROJETO / ".env"
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_dotenv()


def _float(nome: str, padrao: float) -> float:
    try:
        return float(os.environ.get(nome, padrao))
    except ValueError:
        return padrao


def _bool(nome: str, padrao: bool) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


# --- Simulação -----------------------------------------------------------------
# A simulação roda FATOR_TEMPO vezes mais rápido que o relógio. Todo tempo mostrado
# ao usuário é convertido para o relógio dele (segundos de simulação ÷ FATOR_TEMPO).
FATOR_TEMPO: float = max(0.25, _float("FATOR_TEMPO", 2.0))
SIMULADOR_ATIVO: bool = _bool("SIMULADOR_ATIVO", True)
INTERVALO_MIN_S: float = 1.5            # janela de envio de telemetria (relógio real)
INTERVALO_MAX_S: float = 2.0
FALHA_GPS_ATIVA: bool = _bool("SIM_FALHA_GPS", True)

# --- Geometria e traçado --------------------------------------------------------
ESPACAMENTO_ROTA_M: float = 12.0
OSRM_ATIVO: bool = _bool("OSRM_ATIVO", True)
OSRM_ENDPOINT: str = "https://router.project-osrm.org/route/v1/driving/"
OSRM_TIMEOUT_S: float = _float("OSRM_TIMEOUT_S", 8.0)

# --- Operação e regras -----------------------------------------------------------
VELOCIDADE_FALLBACK_KMH: float = 18.0    # usada no ETA enquanto não há histórico do trecho
VELOCIDADE_PLANEJADA_KMH: float = 20.0   # base da tabela de horários (programado)
PARADA_MEDIA_S: float = 25.0             # tempo médio de porta aberta (relógio da simulação)
PARADA_MIN_S: float = 15.0
PARADA_MAX_S: float = 35.0
RETORNO_TERMINAL_S: float = 60.0         # tempo de retorno/regulação no terminal
LIMITE_ALERTA_OCUPACAO: float = 0.70     # regra independente de lotação (script)
LIMITE_LOTACAO_CRITICA: float = 0.95
SEM_SINAL_APOS_S: float = 10.0           # sem telemetria há mais que isso (relógio real) → "sem sinal"
# Regras operacionais em tempo de operação (relógio da simulação); com FATOR_TEMPO=1 coincide com o real.
COMBOIO_LIMITE_S: float = 120.0          # dois ônibus da mesma linha a menos de 2 min um do outro
ATRASO_TOLERANCIA_S: float = 120.0       # pontualidade: até 2 min de atraso conta como "no horário"
ATRASO_ALERTA_S: float = 300.0           # mais de 5 min atrás do horário → alerta de atraso excessivo
MAX_VEICULOS_POR_LINHA: int = 5
HORARIO_INICIO_OPERACAO: int = 5         # tabela programada: das 05h às 23h59
HORARIO_FIM_OPERACAO: int = 24

# --- Persistência e servidor -----------------------------------------------------
DIRETORIO_DADOS = Path(os.environ.get("MOVECIDADE_DADOS", RAIZ_BACKEND / "dados"))
CAMINHO_BANCO = Path(os.environ.get("MOVECIDADE_BANCO", DIRETORIO_DADOS / "movecidade.db"))
CAMINHO_CACHE_ROTAS = DIRETORIO_DADOS / "cache_rotas.json"
DIRETORIO_FRONTEND = RAIZ_PROJETO / "frontend" / "dist"

# --- Gestor -------------------------------------------------------------------------
GESTOR_USUARIO: str = os.environ.get("GESTOR_USUARIO", "gestor")
GESTOR_SENHA: str = os.environ.get("GESTOR_SENHA", "")
SESSAO_SEGREDO: str = os.environ.get("SESSAO_SEGREDO", "troque-este-segredo-no-env")
SESSAO_DURACAO_S: int = 8 * 3600

# --- Ponto de extensão opcional: LLM para o resumo do turno (Hermes) ---------------
# Se HERMES_LLM_URL estiver definido, o resumo é enviado (POST JSON {"frases": [...]})
# e espera-se {"texto": "..."} de volta. Qualquer falha cai no template determinístico.
HERMES_LLM_URL: str = os.environ.get("HERMES_LLM_URL", "")
