"""
Detecção de anomalias → alertas com sugestão (suporte à decisão).

A IA só SUGERE: nenhum alerta executa nada sozinho. A ação associada (`acao`) só roda
quando o gestor clica em "Aceitar" (ver Repositorio.decidir_alerta).
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional

TIPOS = {
    "atraso": "Atraso excessivo",
    "comboio": "Comboiamento",
    "lotacao": "Lotação crítica",
    "acessibilidade": "Pedido de acessibilidade",
}

EXPIRA_APOS_S = 300.0   # alerta pendente cuja condição sumiu há 5 min (relógio real) sai da lista


class GestorAlertas:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pendentes: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._por_chave: Dict[str, str] = {}
        self._contador = itertools.count(1)
        self.total_detectados: Dict[str, int] = {t: 0 for t in TIPOS}

    def sinalizar(self, *, tipo: str, chave: str, linha_id: str, veiculo_id: Optional[str],
                  titulo: str, descricao: str, sugestao: str, acao: Dict[str, Any]) -> None:
        agora = time.monotonic()
        with self._lock:
            existente_id = self._por_chave.get(chave)
            if existente_id and existente_id in self._pendentes:
                alerta = self._pendentes[existente_id]
                alerta.update(titulo=titulo, descricao=descricao, visto_em=agora)
                return
            alerta_id = f"{tipo}-{next(self._contador)}-{int(time.time())}"
            self._pendentes[alerta_id] = {
                "id": alerta_id, "tipo": tipo, "tipo_texto": TIPOS[tipo], "linha_id": linha_id,
                "veiculo_id": veiculo_id, "titulo": titulo, "descricao": descricao, "sugestao": sugestao,
                "acao": acao, "criado_em": datetime.now().isoformat(timespec="seconds"),
                "visto_em": agora,
            }
            self._por_chave[chave] = alerta_id
            self.total_detectados[tipo] += 1
            while len(self._pendentes) > 40:
                self._pendentes.popitem(last=False)

    def expirar(self) -> None:
        limite = time.monotonic() - EXPIRA_APOS_S
        with self._lock:
            for alerta_id in [a for a, al in self._pendentes.items() if al["visto_em"] < limite]:
                del self._pendentes[alerta_id]

    def pendentes(self) -> List[Dict[str, Any]]:
        self.expirar()
        with self._lock:
            itens = list(self._pendentes.values())
        return [{k: v for k, v in a.items() if k not in ("visto_em",)} for a in reversed(itens)]

    def retirar(self, alerta_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            alerta = self._pendentes.pop(alerta_id, None)
            if alerta:
                for chave, aid in list(self._por_chave.items()):
                    if aid == alerta_id:
                        del self._por_chave[chave]
            return alerta

    def remover_da_linha(self, linha_id: str) -> None:
        with self._lock:
            for alerta_id in [a for a, al in self._pendentes.items() if al["linha_id"] == linha_id]:
                del self._pendentes[alerta_id]
