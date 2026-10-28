"""Validação das cores de linha (WCAG 1.4.3 / 1.4.11) e nome legível da cor."""

from __future__ import annotations

import colorsys
import re
from typing import Iterable, Optional, Tuple

CONTRASTE_MINIMO_TEXTO_BRANCO = 4.5
# Distância euclidiana em RGB (0–441) abaixo da qual duas cores são "quase iguais".
# A paleta semente mais próxima (vermelho #B91C1C × laranja #C2410C) fica em ~41.
DISTANCIA_MINIMA_ENTRE_CORES = 30.0

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalizar(cor: str) -> str:
    return cor.strip().upper()


def hex_para_rgb(cor: str) -> Tuple[int, int, int]:
    cor = cor.lstrip("#")
    return int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16)


def luminancia_relativa(cor: str) -> float:
    def canal(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = hex_para_rgb(cor)
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(cor_a: str, cor_b: str) -> float:
    la, lb = luminancia_relativa(cor_a), luminancia_relativa(cor_b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def nome_da_cor(cor: str) -> str:
    """Nome aproximado em português, usado no texto acessível (ex.: "cor vermelha")."""
    r, g, b = (c / 255.0 for c in hex_para_rgb(cor))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.18:
        return "cinza"
    graus = h * 360
    faixas = [
        (15, "vermelha"), (40, "laranja"), (65, "âmbar escuro"), (165, "verde"),
        (200, "azul-petróleo"), (250, "azul"), (290, "roxa"), (335, "rosa"), (361, "vermelha"),
    ]
    for limite, nome in faixas:
        if graus < limite:
            return nome
    return "vermelha"


def validar_cor(cor: str, cores_em_uso: Iterable[str]) -> Tuple[bool, Optional[str]]:
    """
    Regras da seção 4.1: formato #RRGGBB, contraste ≥ 4,5:1 com texto branco e cor
    diferente das demais linhas (inclusive de tons quase iguais).
    Devolve (aprovada, mensagem_de_erro_em_português_simples).
    """
    if not isinstance(cor, str) or not _HEX.match(cor.strip()):
        return False, "Use uma cor no formato #RRGGBB, por exemplo #1D4ED8."
    cor = normalizar(cor)
    razao = contraste(cor, "#FFFFFF")
    if razao < CONTRASTE_MINIMO_TEXTO_BRANCO:
        return False, (f"Cor reprovada: o texto branco sobre ela tem contraste {razao:.1f}:1, "
                       f"abaixo do mínimo de 4,5:1. Escolha um tom mais escuro.")
    rgb = hex_para_rgb(cor)
    for outra in cores_em_uso:
        outra = normalizar(outra)
        if outra == cor:
            return False, "Cor reprovada: outra linha já usa esta cor."
        distancia = sum((a - b) ** 2 for a, b in zip(rgb, hex_para_rgb(outra))) ** 0.5
        if distancia < DISTANCIA_MINIMA_ENTRE_CORES:
            return False, f"Cor reprovada: é muito parecida com a cor {outra} de outra linha."
    return True, None
