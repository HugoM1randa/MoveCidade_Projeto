"""
Dados REAIS do transporte coletivo urbano de Matão/SP (Viação Paraty): linhas Azul, Verde e Vermelha.

Fontes: quadros de horários e itinerários oficiais publicados pela Prefeitura de Matão / Viação Paraty
(os mesmos que alimentam o Bus2/Mobilibus). Cada linha tem dois itinerários ("sentidos"), e cada
itinerário é uma volta que sai do Centro, percorre o bairro e volta ao Centro.

POSIÇÕES: o Bus2 não publica as coordenadas das paradas. Por isso as paradas são as RUAS do itinerário
oficial. Coordenadas conhecidas ficam em ANCORAS (ruas já encaixadas no mapa); o restante vem de
`ruas_matao.json`, gerado por `python -m scripts.gerar_ruas_matao` (geocodifica as ruas no OpenStreetMap).
Rua sem coordenada simplesmente não vira parada — nenhuma posição é inventada.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

ARQUIVO_RUAS = Path(__file__).resolve().parent / "ruas_matao.json"

DATA_REFERENCIA = "dez/2025"
FONTE = "Viação Paraty / Prefeitura de Matão (quadros oficiais, também no Bus2)"

CENTRO_ID = "centro"
CENTRO = {"nome": "Centro (Praça Sete de Setembro)", "referencia": "Início e fim de todos os itinerários",
          "lat": -21.60353, "lon": -48.36632}

# Ruas com posição conhecida (encaixadas na rua pelo OSRM). Gerado/ampliado por ruas_matao.json.
ANCORAS: Dict[str, Tuple[float, float]] = {
    "Av. 15 de Novembro": (-21.60052, -48.36395),
    "Rua Enzo Castelani": (-21.59224, -48.35585),
    "Av. São Lourenço": (-21.59347, -48.37900),
    "Rua Constantino Bastia": (-21.60532, -48.37137),
    "Av. Baldan": (-21.61346, -48.37121),
    "Av. Dr. Laerte Taralo Mendes": (-21.60951, -48.37479),
    "Av. Toledo Malta": (-21.60194, -48.36914),
    "Av. Araraquara": (-21.61101, -48.35892),
    "Rua Jundiaí": (-21.61275, -48.35487),
    "Rua Izidoro Adail Botezini": (-21.61713, -48.35207),
}

# Paleta: contraste ≥ 4,5:1 com texto branco. (hex, nome, padrão do traçado: não depende só da cor)
PALETA: List[Dict[str, str]] = [
    {"cor": "#1D4ED8", "nome": "azul", "padrao": "continuo"},
    {"cor": "#15803D", "nome": "verde", "padrao": "tracejado"},
    {"cor": "#DC2626", "nome": "vermelha", "padrao": "pontilhado"},
    {"cor": "#7E22CE", "nome": "roxa", "padrao": "traco_ponto"},
    {"cor": "#C2410C", "nome": "laranja", "padrao": "continuo"},
    {"cor": "#BE185D", "nome": "rosa", "padrao": "tracejado"},
    {"cor": "#A16207", "nome": "âmbar escuro", "padrao": "pontilhado"},
]


def _h(texto: str) -> List[str]:
    return [t.strip() for t in texto.split("/") if t.strip()]


def _meia_em_meia(inicio: str, fim: str) -> List[str]:
    def m(t: str) -> int:
        return int(t[:2]) * 60 + int(t[3:])
    return [f"{x // 60:02d}:{x % 60:02d}" for x in range(m(inicio), m(fim) + 1, 30)]


_ALL30 = _meia_em_meia("06:30", "18:30")

# Linha → itinerário → quadro. "do_centro" = saídas do Centro; "para_centro" = saídas do bairro.
LINHAS_REAIS: List[Dict[str, Any]] = [
    {
        "id": "azul-santa-rosa", "linha": "Azul", "paleta": 0, "destino": "Jd. Santa Rosa", "intervalo_min": 30,
        "ruas": ["Av. 15 de Novembro", "Av. Baldan", "Av. Dr. Laerte Taralo Mendes", "Rua Bambozzi",
                 "Av. Saldanha da Gama", "Rua Cesário Motta", "Av. José da Costa Filho", "Rua Constantino Bastia",
                 "Av. Nelson Domingues de Moraes", "Rua Achilles Chiozzini", "Rua Durval de Souza",
                 "Rua Gildo Nicolucci", "Rua Vicente Córdoa", "Av. Marcílio Cechetto", "Av. Benedito de Queiroz",
                 "Rua Aristodemos Pompéo Lanza", "Av. Felippe Thomaz Granato", "Av. Odair Pedro de Melo",
                 "Av. Eduardo Claro dos Santos", "Av. Joaquim da Silva", "Av. Miguel Garcia Filho",
                 "Av. Emil Gaston Lauchner", "Av. Ludwig Eckes", "Av. Adalberto Antunes", "Av. Antônio Lian",
                 "Rua Sinharinha Frota"],
        "obs": "Alguns horários de Santa Rosa → Centro vêm do bairro São José (05:10). "
               "Saídas das 16:30 (Centro → Santa Rosa) atendem o Jd. Benassi (Cond. Vila Romana).",
        "do_centro": {
            "uteis": _h("07:05 / 07:30 / 08:35 / 09:05 / 09:35 / 10:05 / 10:35 / 11:05 / 11:35 / 12:05 / 12:35 / 13:05 / 13:35 / 14:35 / 15:05 / 15:35 / 16:05 / 16:30 / 17:05 / 17:35 / 18:05 / 18:35"),
            "sabado": _h("07:05 / 08:35 / 09:05 / 10:05 / 10:35 / 11:35 / 12:05 / 13:05 / 13:35 / 14:35 / 15:05 / 16:05 / 17:35"),
            "domingo": _h("07:00 / 08:30 / 13:00 / 14:30 / 16:00 / 17:30"),
        },
        "para_centro": {
            "uteis": _h("05:10 / 05:55 / 06:15 / 07:25 / 07:55 / 08:55 / 09:25 / 09:55 / 10:25 / 10:55 / 11:25 / 11:55 / 12:25 / 12:55 / 13:25 / 13:55 / 14:55 / 15:25 / 15:55 / 16:25 / 16:55 / 17:25 / 17:55"),
            "sabado": _h("05:10 / 05:55 / 07:25 / 07:55 / 08:55 / 09:25 / 10:25 / 10:55 / 11:55 / 12:25 / 13:25 / 13:55 / 14:55 / 16:25"),
            "domingo": _h("05:10 / 05:55 / 07:25 / 13:25 / 16:25"),
        },
    },
    {
        "id": "azul-bairro-alto", "linha": "Azul", "paleta": 0, "destino": "Bairro Alto", "intervalo_min": 30,
        "ruas": ["Av. São Lourenço", "Rua José Simão Kifouri", "Av. G. Maria M. Martins",
                 "Rua Guido Cardim", "Rua Enzo Castelani", "Rua Luiz Andreatti", "Av. Napoleão Bottura",
                 "Av. Cor. Leão Pio de Freitas", "Av. 15 de Novembro"],
        "obs": "Alguns horários de Bairro Alto → Centro vêm do Bairro Popular (05:15).",
        "do_centro": {
            "uteis": _h("06:30 / 07:00 / 08:00 / 08:30 / 09:00 / 09:30 / 10:00 / 10:30 / 11:00 / 11:30 / 12:00 / 12:30 / 13:00 / 14:00 / 14:30 / 15:30 / 16:00 / 16:30 / 17:00 / 17:30 / 18:00 / 18:30"),
            "sabado": _h("06:30 / 08:00 / 08:30 / 09:30 / 10:00 / 11:00 / 11:30 / 12:30 / 13:00 / 14:00 / 14:30 / 15:30 / 17:00"),
            "domingo": _h("06:30 / 08:00 / 14:00 / 17:00"),
        },
        "para_centro": {
            "uteis": _h("05:15 / 05:50 / 06:45 / 07:15 / 08:15 / 08:45 / 09:15 / 09:45 / 10:15 / 10:45 / 11:15 / 11:45 / 12:15 / 12:45 / 13:15 / 14:15 / 14:45 / 15:45 / 16:15 / 16:45 / 17:15 / 17:45 / 18:15"),
            "sabado": _h("05:15 / 06:45 / 08:15 / 08:45 / 09:45 / 10:15 / 11:15 / 11:45 / 12:45 / 13:15 / 14:15 / 14:45 / 15:45 / 17:15"),
            "domingo": _h("05:15 / 06:45 / 08:15 / 14:15 / 17:15"),
        },
    },
    {
        "id": "verde-sao-jose", "linha": "Verde", "paleta": 1, "destino": "São José", "intervalo_min": 30,
        "ruas": ["Av. São Lourenço", "Av. Toledo Malta", "Rodovia dos Trabalhadores",
                 "Av. Bernardino Scutti", "Av. Manoel Mingoranci", "Rua Tomaz Spinelli", "Av. Odone Marchesan",
                 "Rua Francisco Pedro Antônio", "Av. Domingos Mariani", "Rua Américo Vezani", "Av. Campos Salles", "Av. 15 de Novembro"],
        "obs": "Alguns horários de São José → Centro passam pelo Alto dos Pinheiros. O das 05:00 passa pelo Santa Rosa às 05:10.",
        "do_centro": {
            "uteis": _ALL30,
            "sabado": _h("06:30 / 08:00 / 08:30 / 09:30 / 10:00 / 11:00 / 11:30 / 12:30 / 13:00 / 14:00 / 14:30 / 15:30 / 17:00"),
            "domingo": _h("06:30 / 08:00 / 14:00 / 17:00"),
        },
        "para_centro": {
            "uteis": _h("05:00 / 06:00 / 06:45 / 07:15 / 07:45 / 08:15 / 08:45 / 09:15 / 09:45 / 10:15 / 10:45 / 11:15 / 11:45 / 12:15 / 12:45 / 13:15 / 13:45 / 14:15 / 14:45 / 15:15 / 15:45 / 16:15 / 16:45 / 17:15 / 17:45 / 18:15"),
            "sabado": _h("05:00 / 06:45 / 08:15 / 08:45 / 09:45 / 10:15 / 11:15 / 11:45 / 12:45 / 13:15 / 14:15 / 14:45 / 15:45 / 17:15"),
            "domingo": _h("05:00 / 06:45 / 08:15 / 14:15 / 17:15"),
        },
    },
    {
        "id": "verde-paraiso", "linha": "Verde", "paleta": 1, "destino": "Jd. Paraíso", "intervalo_min": 30,
        "ruas": ["Av. 15 de Novembro", "Av. Sinharinha Frota", "Av. Trolesi", "Via Orlando José Scutti",
                 "Rua Alberto Bidutti", "Rua Santo Nonis", "Av. Antônio Gorgatti", "Rua José da Cunha",
                 "Rua Alexandre dos Santos Pires", "Av. Marlene David dos Santos", "Av. José Antônio Vidal",
                 "Rua José Burjalle", "Rua Luís G. da Silva", "Av. Jacyro Rosa", "Av. Ver. Amauri Squisatti",
                 "Av. Jandira P. C. da Silva", "Av. Augusto Ferreira", "Av. Germano Primo Pinotti",
                 "Rua Cesário Motta"],
        "obs": "Parte das saídas segue via Nova Matão / Boa Vista (Toriba). "
               "A saída das 05:00 do Paraíso vem do Monte Carlo às 04:50.",
        "do_centro": {
            "uteis": _ALL30,
            "sabado": _h("07:00 / 08:30 / 09:00 / 10:00 / 10:30 / 11:30 / 12:00 / 13:00 / 13:30 / 14:30 / 15:00 / 16:00 / 17:30"),
            "domingo": _h("07:00 / 08:30 / 13:00 / 14:30 / 16:00 / 17:30"),
        },
        "para_centro": {
            "uteis": _h("05:00 / 05:55 / 06:25 / 06:55 / 07:25 / 07:55 / 08:25 / 08:55 / 09:25 / 09:55 / 10:25 / 10:55 / 11:25 / 11:55 / 12:25 / 12:55 / 13:25 / 13:55 / 14:25 / 14:55 / 15:25 / 15:55 / 16:25 / 16:55 / 17:25 / 17:55"),
            "sabado": _h("05:00 / 05:55 / 07:25 / 07:55 / 08:55 / 09:25 / 10:25 / 10:55 / 11:55 / 12:25 / 13:25 / 13:55 / 14:55 / 16:25"),
            "domingo": _h("05:00 / 06:00 / 07:30 / 13:30 / 16:30"),
        },
    },
    {
        "id": "vermelha-popular", "linha": "Vermelha", "paleta": 2, "destino": "Bairro Popular", "intervalo_min": 30,
        "ruas": ["Rua São Lourenço", "Rua Nhonhô Magalhães", "Rua Prudente de Moraes", "Av. Carlos Mariani",
                 "Av. Américo Apoloni", "Av. São Paulo", "Rua Pará", "Av. Mato Grosso do Sul", "Rua João Cecheto",
                 "Av. Alagoas", "Av. Trolesi", "Av. José Esquetine", "Av. José Rolin Dias", "Av. Rotary",
                 "Av. Laurindo de Matos", "Av. Nestor Gardini", "Rua Pedro Trolli", "Rua José Domingos Bussola",
                 "Av. Brasil", "Av. Antônio Geraldo Granata", "Av. Benício Pinto de Mendonça",
                 "Av. Pascoal Trevisan", "Rua Brasílio Bambozi", "Av. 15 de Novembro"],
        "obs": "A saída das 05:00 do Popular passa pelo Bairro Alto às 05:15.",
        "do_centro": {
            "uteis": _h("07:00 / 07:30 / 08:30 / 09:00 / 09:30 / 10:00 / 10:30 / 11:00 / 11:30 / 12:00 / 12:30 / 13:00 / 13:30 / 14:30 / 15:00 / 15:30 / 16:00 / 16:30 / 17:00 / 17:30 / 18:00 / 18:30"),
            "sabado": _h("07:00 / 08:30 / 09:00 / 10:00 / 10:30 / 11:30 / 12:00 / 13:00 / 13:30 / 14:30 / 15:00 / 16:00 / 17:30"),
            "domingo": _h("07:00 / 08:30 / 13:00 / 14:30 / 16:00 / 17:30"),
        },
        "para_centro": {
            "uteis": _h("05:00 / 06:00 / 06:25 / 07:25 / 07:55 / 08:55 / 09:25 / 09:55 / 10:25 / 10:55 / 11:25 / 11:55 / 12:25 / 13:25 / 13:55 / 14:55 / 15:25 / 15:55 / 16:25 / 16:55 / 17:25 / 17:55"),
            "sabado": _h("05:00 / 06:00 / 07:25 / 07:55 / 08:55 / 09:25 / 10:25 / 10:55 / 11:55 / 12:25 / 13:25 / 13:55 / 14:55 / 16:25"),
            "domingo": _h("05:00 / 06:00 / 07:25 / 13:25 / 16:25"),
        },
    },
    {
        "id": "vermelha-monte-carlo", "linha": "Vermelha", "paleta": 2, "destino": "Monte Carlo", "intervalo_min": 30,
        "ruas": ["Av. 15 de Novembro", "Av. Sinharinha Frota", "Av. Araraquara", "Rua Izidoro Adail Botezini",
                 "Av. Trolesi", "Av. Cássio Bottura", "Av. Pindorama", "Rua Jundiaí", "Av. Rincão",
                 "Av. Américo Brasiliense", "Rua Catanduva", "Av. Taquaritinga", "Rua Cesário Motta"],
        "obs": "A saída das 04:50 do Monte Carlo passa pelo Jd. Paraíso às 05:00.",
        "do_centro": {
            "uteis": _h("06:30 / 07:00 / 08:00 / 08:30 / 09:00 / 09:30 / 10:00 / 10:30 / 11:00 / 11:30 / 12:00 / 12:30 / 13:00 / 14:00 / 14:30 / 15:30 / 16:00 / 16:30 / 17:00 / 17:30 / 18:00 / 18:30"),
            "sabado": _h("06:30 / 08:00 / 08:30 / 09:30 / 10:00 / 11:00 / 11:30 / 12:30 / 13:00 / 14:00 / 14:30 / 15:30 / 17:00"),
            "domingo": _h("06:30 / 08:00 / 14:00 / 17:00"),
        },
        "para_centro": {
            "uteis": _h("04:50 / 06:45 / 07:15 / 08:15 / 08:45 / 09:15 / 09:45 / 10:15 / 10:45 / 11:15 / 11:45 / 12:15 / 12:45 / 13:15 / 14:15 / 14:45 / 15:45 / 16:15 / 16:45 / 17:15 / 17:45 / 18:15"),
            "sabado": _h("04:50 / 06:45 / 08:15 / 08:45 / 09:45 / 10:15 / 11:15 / 11:45 / 12:45 / 13:15 / 14:15 / 14:45 / 15:45 / 17:15"),
            "domingo": _h("04:50 / 06:45 / 08:15 / 14:15 / 17:15"),
        },
    },
]

# Ônibus SIMULADOS (a operadora não publica o GPS da frota): 2 por itinerário.
CAPACIDADES = (70, 54)
SIGLAS = {"azul-santa-rosa": "AZ-SR", "azul-bairro-alto": "AZ-BA", "verde-sao-jose": "VD-SJ",
          "verde-paraiso": "VD-PA", "vermelha-popular": "VM-PO", "vermelha-monte-carlo": "VM-MC"}


def slug(texto: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem).strip("-")


def coordenadas_das_ruas() -> Dict[str, Tuple[float, float]]:
    """ANCORAS + o que o geocodificador gravou em ruas_matao.json (o arquivo prevalece)."""
    coords = dict(ANCORAS)
    if ARQUIVO_RUAS.exists():
        try:
            bruto = json.loads(ARQUIVO_RUAS.read_text(encoding="utf-8"))
            for rua, valor in bruto.items():
                if isinstance(valor, list) and len(valor) >= 2:
                    coords[rua] = (float(valor[0]), float(valor[1]))
        except (ValueError, OSError):
            pass
    return coords


def _paradas_do_itinerario(item: Dict[str, Any], coords: Dict[str, Tuple[float, float]], maximo: int = 14) -> List[str]:
    ruas = [r for r in dict.fromkeys(item["ruas"]) if r in coords]
    if len(ruas) > maximo:  # mantém primeira e última e distribui as demais
        passo = (len(ruas) - 1) / (maximo - 1)
        ruas = [ruas[round(i * passo)] for i in range(maximo)]
    return [CENTRO_ID] + [slug(r) for r in ruas]


def montar() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Devolve (pontos, linhas, veículos) no formato esperado por seed.dados."""
    coords = coordenadas_das_ruas()
    pontos: Dict[str, Dict[str, Any]] = {
        CENTRO_ID: {"id": CENTRO_ID, "nome": CENTRO["nome"], "referencia": CENTRO["referencia"],
                    "lat": CENTRO["lat"], "lon": CENTRO["lon"],
                    "acessibilidade": {"rampa": True, "piso_tatil": False, "abrigo": True}, "status": "operando"}
    }
    linhas: List[Dict[str, Any]] = []
    veiculos: List[Dict[str, Any]] = []
    for item in LINHAS_REAIS:
        ids = _paradas_do_itinerario(item, coords)
        for rua in item["ruas"]:
            pid = slug(rua)
            if pid in ids and pid not in pontos:
                lat, lon = coords[rua]
                pontos[pid] = {"id": pid, "nome": rua, "referencia": "Itinerário oficial (posição aproximada)",
                               "lat": lat, "lon": lon,
                               "acessibilidade": {"rampa": False, "piso_tatil": False, "abrigo": False},
                               "status": "operando"}
        linhas.append({"id": item["id"], "numero": item["linha"], "nome": f"Centro – {item['destino']}",
                       "paleta": item["paleta"], "intervalo_min": item["intervalo_min"], "pontos": ids})
        sigla = SIGLAS[item["id"]]
        for n in (1, 2):
            veiculos.append({"id": f"{sigla}-{n}", "linha_id": item["id"], "capacidade": CAPACIDADES[n - 1],
                             "acessivel": n == 1, "ativo": True})
    return list(pontos.values()), linhas, veiculos


def quadro(linha_id: str) -> Dict[str, Any]:
    """Quadro de horários oficial de um itinerário (ou {} se a linha não for uma das reais)."""
    for item in LINHAS_REAIS:
        if item["id"] == linha_id:
            return {"destino": item["destino"], "observacoes": item["obs"], "fonte": FONTE,
                    "referencia": DATA_REFERENCIA, "do_centro": item["do_centro"],
                    "para_centro": item["para_centro"]}
    return {}
