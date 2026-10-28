"""
Dados semente do MoveCidade (Matão/SP).

ATENÇÃO: os NOMES e as POSIÇÕES dos pontos são FICTÍCIOS e APROXIMADOS. As coordenadas
foram encaixadas na rua mais próxima (serviço "nearest" do OSRM) só para que os ônibus
passem por cima delas; a "referência" é o nome dessa rua. Para usar dados reais, edite
este arquivo (ou cadastre pelo painel do gestor) e apague backend/dados/movecidade.db.

Este é o ÚNICO lugar onde as cores das linhas-semente são definidas. Depois do primeiro
início elas ficam na tabela `linhas` do SQLite e o front-end lê de lá pela API.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Paleta oficial: todas têm contraste ≥ 4,5:1 com texto branco. As duas últimas são reserva
# para linhas novas criadas pelo gestor. (hex, nome da cor, padrão do traçado no mapa)
PALETA: List[Dict[str, str]] = [
    {"cor": "#1D4ED8", "nome": "azul", "padrao": "continuo"},
    {"cor": "#B91C1C", "nome": "vermelha", "padrao": "tracejado"},
    {"cor": "#047857", "nome": "verde", "padrao": "continuo"},
    {"cor": "#7E22CE", "nome": "roxa", "padrao": "pontilhado"},
    {"cor": "#C2410C", "nome": "laranja", "padrao": "traco_ponto"},
    {"cor": "#BE185D", "nome": "rosa", "padrao": "tracejado"},
    {"cor": "#A16207", "nome": "âmbar escuro", "padrao": "pontilhado"},
]

# id, nome, referência, lat, lon, rampa, piso_tatil, abrigo
_PONTOS = [
    ("praca-matriz", "Praça da Matriz", "Rua José Bonifácio", -21.60353, -48.36632, True, True, True),
    ("terminal", "Terminal Municipal", "Avenida Ernésio Gorgat", -21.60696, -48.36409, True, True, True),
    ("mercado", "Mercado Municipal", "Avenida 15 de Novembro", -21.60052, -48.36395, True, False, True),
    ("hospital", "Hospital", "Acesso do Hospital", -21.59763, -48.37007, True, True, True),
    ("escola", "Escola Estadual", "Rua Constantino Bastia", -21.60532, -48.37137, False, True, True),
    ("rodoviaria", "Rodoviária", "Avenida Quinze de Novembro", -21.61054, -48.36941, True, True, True),
    ("estadio", "Estádio", "Avenida Vinte e Oito de Agosto", -21.59544, -48.36013, True, False, False),
    ("nova-matao", "Nova Matão", "Rua Enzo Castelani", -21.59224, -48.35585, False, False, True),
    ("posto-nova-matao", "Posto de Saúde Nova Matão", "Rua Bahia", -21.59422, -48.35292, True, True, False),
    ("distrito", "Distrito Industrial", "Avenida São Lourenço", -21.59347, -48.37900, False, False, True),
    ("av-industrial", "Avenida Industrial", "Rua João Pessoa", -21.59782, -48.37417, False, True, False),
    ("cemiterio", "Cemitério da Saudade", "Alameda da Saudade", -21.59993, -48.37396, True, False, False),
    ("biblioteca", "Biblioteca Municipal", "Avenida Toledo Malta", -21.60194, -48.36914, True, True, True),
    ("supermercado", "Supermercado", "Avenida Araraquara", -21.61101, -48.35892, True, False, True),
    ("ginasio", "Ginásio de Esportes", "Avenida Cabo Manoel de Azevedo", -21.60858, -48.35589, False, False, True),
    ("ubs-vila", "UBS Vila Operária", "Rua Jundiaí", -21.61275, -48.35487, True, True, False),
    ("vila-operaria", "Vila Operária", "Rua Izidoro Adail Bottesini", -21.61713, -48.35207, False, True, True),
    ("praca-jardim", "Praça do Jardim", "Avenida Baldan", -21.61346, -48.37121, True, False, True),
    ("bairro-jardim", "Bairro Jardim", "Rua do Bairro Jardim", -21.61640, -48.37274, False, False, False),
    ("parque", "Parque Ecológico", "Avenida Doutor Laerte José Tarallo Mendes", -21.60951, -48.37479, True, True, False),
]

PONTOS: List[Dict[str, Any]] = [
    {
        "id": pid, "nome": nome, "referencia": ref, "lat": lat, "lon": lon,
        "acessibilidade": {"rampa": rampa, "piso_tatil": piso, "abrigo": abrigo},
        "status": "operando",
    }
    for pid, nome, ref, lat, lon, rampa, piso, abrigo in _PONTOS
]

# Cada linha é uma volta fechada: sai do primeiro ponto, passa pelos demais na ordem
# e retorna ao primeiro (o traçado de volta é calculado pelo OSRM). As linhas 101 e 202
# seguem o eixo das linhas do protótipo (SO→NE e NO→SE), cruzando o Centro.
LINHAS: List[Dict[str, Any]] = [
    {
        "id": "101", "numero": "101", "nome": "Centro – Nova Matão", "paleta": 0, "intervalo_min": 12,
        "pontos": ["terminal", "praca-matriz", "mercado", "estadio", "nova-matao", "posto-nova-matao"],
    },
    {
        "id": "102", "numero": "102", "nome": "Centro – Bairro Jardim", "paleta": 1, "intervalo_min": 10,
        "pontos": ["praca-matriz", "escola", "rodoviaria", "praca-jardim", "bairro-jardim"],
    },
    {
        "id": "202", "numero": "202", "nome": "Distrito Industrial – Terminal", "paleta": 2, "intervalo_min": 15,
        "pontos": ["distrito", "av-industrial", "cemiterio", "biblioteca", "terminal"],
    },
    {
        "id": "205", "numero": "205", "nome": "Terminal – Vila Operária", "paleta": 3, "intervalo_min": 12,
        "pontos": ["praca-matriz", "terminal", "supermercado", "ginasio", "ubs-vila", "vila-operaria"],
    },
    {
        "id": "310", "numero": "310", "nome": "Circular Centro", "paleta": 4, "intervalo_min": 10,
        "pontos": ["terminal", "rodoviaria", "parque", "escola", "hospital", "mercado"],
    },
]

# id, linha, capacidade, acessível
FROTA = [
    ("101-A", "101", 70, True),
    ("101-B", "101", 54, False),
    ("102-A", "102", 62, True),
    ("102-B", "102", 70, False),
    ("102-C", "102", 54, True),
    ("202-A", "202", 80, False),
    ("202-B", "202", 62, True),
    ("205-A", "205", 70, True),
    ("205-B", "205", 54, False),
    ("310-A", "310", 54, True),
    ("310-B", "310", 62, False),
    ("310-C", "310", 70, False),
]

VEICULOS: List[Dict[str, Any]] = [
    {"id": vid, "linha_id": lid, "capacidade": cap, "acessivel": acc, "ativo": True}
    for vid, lid, cap, acc in FROTA
]
