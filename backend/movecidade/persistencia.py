"""Persistência simples em SQLite: linhas, pontos, veículos e decisões sobre alertas."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List

from .dominio import Linha, Ponto, Veiculo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS pontos (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, referencia TEXT NOT NULL DEFAULT '',
    lat REAL NOT NULL, lon REAL NOT NULL,
    rampa INTEGER NOT NULL DEFAULT 0, piso_tatil INTEGER NOT NULL DEFAULT 0, abrigo INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'operando'
);
CREATE TABLE IF NOT EXISTS linhas (
    id TEXT PRIMARY KEY, numero TEXT NOT NULL, nome TEXT NOT NULL,
    cor TEXT NOT NULL, cor_nome TEXT NOT NULL, padrao TEXT NOT NULL,
    intervalo_min INTEGER NOT NULL, pontos TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS veiculos (
    id TEXT PRIMARY KEY, linha_id TEXT NOT NULL, capacidade INTEGER NOT NULL,
    acessivel INTEGER NOT NULL DEFAULT 0, ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS decisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alerta_id TEXT NOT NULL, tipo TEXT NOT NULL, linha_id TEXT, veiculo_id TEXT,
    titulo TEXT NOT NULL, sugestao TEXT NOT NULL,
    decisao TEXT NOT NULL, resultado TEXT NOT NULL DEFAULT '', decidido_em TEXT NOT NULL
);
"""


class Banco:
    def __init__(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(caminho), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        with self._lock:
            self._con.executescript(ESQUEMA)
            self._con.commit()

    def fechar(self) -> None:
        with self._lock:
            self._con.close()

    def vazio(self) -> bool:
        with self._lock:
            return self._con.execute("SELECT COUNT(*) FROM linhas").fetchone()[0] == 0

    # ------------------------------------------------------------------ pontos
    def carregar_pontos(self) -> List[Ponto]:
        with self._lock:
            linhas = self._con.execute("SELECT * FROM pontos ORDER BY nome").fetchall()
        return [Ponto(id=r["id"], nome=r["nome"], referencia=r["referencia"], lat=r["lat"], lon=r["lon"],
                      acessibilidade={"rampa": bool(r["rampa"]), "piso_tatil": bool(r["piso_tatil"]),
                                      "abrigo": bool(r["abrigo"])},
                      status=r["status"]) for r in linhas]

    def salvar_ponto(self, p: Ponto) -> None:
        with self._lock:
            self._con.execute(
                "INSERT OR REPLACE INTO pontos VALUES (?,?,?,?,?,?,?,?,?)",
                (p.id, p.nome, p.referencia, p.lat, p.lon, int(p.acessibilidade.get("rampa", False)),
                 int(p.acessibilidade.get("piso_tatil", False)), int(p.acessibilidade.get("abrigo", False)), p.status))
            self._con.commit()

    def remover_ponto(self, ponto_id: str) -> None:
        with self._lock:
            self._con.execute("DELETE FROM pontos WHERE id=?", (ponto_id,))
            self._con.commit()

    # ------------------------------------------------------------------ linhas
    def carregar_linhas(self) -> List[Linha]:
        with self._lock:
            linhas = self._con.execute("SELECT * FROM linhas ORDER BY numero").fetchall()
        return [Linha(id=r["id"], numero=r["numero"], nome=r["nome"], cor=r["cor"], cor_nome=r["cor_nome"],
                      padrao=r["padrao"], intervalo_min=r["intervalo_min"], pontos=json.loads(r["pontos"]))
                for r in linhas]

    def salvar_linha(self, l: Linha) -> None:
        with self._lock:
            self._con.execute(
                "INSERT OR REPLACE INTO linhas VALUES (?,?,?,?,?,?,?,?)",
                (l.id, l.numero, l.nome, l.cor, l.cor_nome, l.padrao, l.intervalo_min, json.dumps(l.pontos)))
            self._con.commit()

    def remover_linha(self, linha_id: str) -> None:
        with self._lock:
            self._con.execute("DELETE FROM linhas WHERE id=?", (linha_id,))
            self._con.execute("DELETE FROM veiculos WHERE linha_id=?", (linha_id,))
            self._con.commit()

    # ---------------------------------------------------------------- veículos
    def carregar_veiculos(self) -> List[Veiculo]:
        with self._lock:
            linhas = self._con.execute("SELECT * FROM veiculos ORDER BY id").fetchall()
        return [Veiculo(id=r["id"], linha_id=r["linha_id"], capacidade=r["capacidade"],
                        acessivel=bool(r["acessivel"]), ativo=bool(r["ativo"])) for r in linhas]

    def salvar_veiculo(self, v: Veiculo) -> None:
        with self._lock:
            self._con.execute("INSERT OR REPLACE INTO veiculos VALUES (?,?,?,?,?)",
                              (v.id, v.linha_id, v.capacidade, int(v.acessivel), int(v.ativo)))
            self._con.commit()

    def remover_veiculo(self, veiculo_id: str) -> None:
        with self._lock:
            self._con.execute("DELETE FROM veiculos WHERE id=?", (veiculo_id,))
            self._con.commit()

    # ---------------------------------------------------------------- decisões
    def registrar_decisao(self, d: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            cur = self._con.execute(
                "INSERT INTO decisoes (alerta_id,tipo,linha_id,veiculo_id,titulo,sugestao,decisao,resultado,decidido_em)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (d["alerta_id"], d["tipo"], d.get("linha_id"), d.get("veiculo_id"), d["titulo"], d["sugestao"],
                 d["decisao"], d.get("resultado", ""), d["decidido_em"]))
            self._con.commit()
            return {**d, "id": cur.lastrowid}

    def decisoes_recentes(self, limite: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            linhas = self._con.execute("SELECT * FROM decisoes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in linhas]

    def decididos(self) -> set:
        with self._lock:
            return {r[0] for r in self._con.execute("SELECT alerta_id FROM decisoes").fetchall()}
