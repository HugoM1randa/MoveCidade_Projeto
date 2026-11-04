"""
Dados semente do MoveCidade (Matão/SP).

Agora são os dados REAIS das três linhas urbanas de Matão (Azul, Verde e Vermelha), definidos em
`matao_real.py` (itinerários e quadros de horários oficiais). Este módulo só expõe o formato que o
repositório espera: PALETA, PONTOS, LINHAS e VEICULOS. Depois do primeiro início os dados ficam no SQLite;
para recarregar o seed, apague backend/dados/movecidade.db.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import matao_real

PALETA: List[Dict[str, str]] = matao_real.PALETA

PONTOS: List[Dict[str, Any]]
LINHAS: List[Dict[str, Any]]
VEICULOS: List[Dict[str, Any]]
PONTOS, LINHAS, VEICULOS = matao_real.montar()
