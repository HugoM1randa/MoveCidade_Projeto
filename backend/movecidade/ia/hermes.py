"""
Hermes — resumo do turno gerado por TEMPLATE a partir dos dados reais da simulação.

Ponto de extensão opcional: se HERMES_LLM_URL estiver definido, as frases do template são
enviadas a esse endpoint para reescrita; qualquer falha devolve o template.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import config


def turno_atual(hora: Optional[int] = None) -> str:
    hora = datetime.now().hour if hora is None else hora
    if 5 <= hora < 12:
        return "manhã"
    if 12 <= hora < 18:
        return "tarde"
    if 18 <= hora < 24:
        return "noite"
    return "madrugada"


def _num(valor: Optional[float], sufixo: str) -> str:
    if valor is None:
        return "ainda sem dados"
    texto = f"{valor:.1f}".replace(".", ",") if isinstance(valor, float) and not valor.is_integer() else f"{int(valor)}"
    return f"{texto}{sufixo}"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def frases_do_turno(kpis: Dict[str, Any], *, pendentes: List[Dict[str, Any]], detectados: Dict[str, int],
                    decisoes: List[Dict[str, Any]], linha_critica: Optional[Dict[str, Any]]) -> List[str]:
    frases: List[str] = []
    disp = kpis["disponibilidade"]
    frases.append(
        f"Turno da {turno_atual()}: {disp['ativos']} de {disp['cadastrados']} ônibus estão operando com sinal "
        f"({_num(disp['valor'], '%')} de disponibilidade).")

    pont = kpis["pontualidade"]
    if pont["valor"] is not None:
        avaliacao = "boa" if pont["valor"] >= 85 else ("regular" if pont["valor"] >= 70 else "baixa")
        frases.append(f"A pontualidade está {avaliacao}: {pont['valor']}% das chegadas aos pontos foram no horário.")
    else:
        frases.append("A pontualidade ainda está sendo medida; os primeiros dados chegam em poucos minutos.")

    ocup = kpis["ocupacao_horario"]
    if ocup["valor"] is not None:
        frases.append(f"A ocupação média nesta hora é de {ocup['valor']}%, com espera média de "
                      f"{_num(kpis['tempo_espera']['valor'], ' min')} nos pontos.")

    total = sum(detectados.values())
    if total:
        partes = []
        nomes = {"atraso": "atraso", "comboio": "comboiamento", "lotacao": "lotação crítica",
                 "acessibilidade": "pedido de acessibilidade"}
        for tipo, qtd in detectados.items():
            if qtd:
                partes.append(f"{qtd} de {nomes[tipo]}")
        aguardam = len(pendentes)
        frases.append(f"{'Foi detectada' if total == 1 else 'Foram detectadas'} {_plural(total, 'ocorrência', 'ocorrências')} "
                      f"desde o início do turno ({', '.join(partes)}); "
                      f"{_plural(aguardam, 'aguarda', 'aguardam')} decisão.")
    else:
        frases.append("Nenhuma ocorrência detectada até agora.")

    if linha_critica:
        frases.append(f"Atenção à linha {linha_critica['numero']}: {linha_critica['motivo']}.")

    aceitas = sum(1 for d in decisoes if d["decisao"] == "aceito")
    if decisoes:
        frases.append(f"O gestor já decidiu {_plural(len(decisoes), 'sugestão', 'sugestões')} "
                      f"({_plural(aceitas, 'aceita', 'aceitas')} e {_plural(len(decisoes) - aceitas, 'ignorada', 'ignoradas')}).")
    return frases[:5]


def resumo_de_turno(frases: List[str]) -> Dict[str, Any]:
    texto = " ".join(frases)
    fonte = "template"
    if config.HERMES_LLM_URL:
        try:
            req = urllib.request.Request(config.HERMES_LLM_URL, data=json.dumps({"frases": frases}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=6) as resp:
                gerado = json.loads(resp.read().decode("utf-8")).get("texto")
            if isinstance(gerado, str) and gerado.strip():
                texto, fonte = gerado.strip(), "llm"
        except Exception:
            pass
    return {"frases": frases, "texto": texto, "fonte": fonte,
            "gerado_em": datetime.now().isoformat(timespec="seconds")}
