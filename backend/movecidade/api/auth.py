"""Login simples do gestor: usuário e senha do .env, sessão em cookie assinado (HMAC)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel

from .. import config

COOKIE = "mc_sessao"
router = APIRouter(prefix="/api/gestor", tags=["gestor: sessão"])


def _assinar(texto: str) -> str:
    return hmac.new(config.SESSAO_SEGREDO.encode(), texto.encode(), hashlib.sha256).hexdigest()


def criar_token(usuario: str) -> str:
    expira = int(time.time()) + config.SESSAO_DURACAO_S
    corpo = f"{usuario}|{expira}"
    return base64.urlsafe_b64encode(f"{corpo}|{_assinar(corpo)}".encode()).decode()


def usuario_do_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        usuario, expira, assinatura = base64.urlsafe_b64decode(token.encode()).decode().rsplit("|", 2)
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(assinatura, _assinar(f"{usuario}|{expira}")):
        return None
    if int(expira) < time.time():
        return None
    return usuario


def exigir_gestor(request: Request) -> str:
    """Dependência FastAPI: só deixa passar quem tem sessão válida de gestor."""
    usuario = usuario_do_token(request.cookies.get(COOKIE))
    if usuario is None:
        raise HTTPException(status_code=401, detail="Entre com o usuário do gestor para continuar.")
    return usuario


class Credenciais(BaseModel):
    usuario: str
    senha: str


@router.post("/login")
def login(dados: Credenciais, response: Response) -> dict:
    if not config.GESTOR_SENHA:
        raise HTTPException(status_code=503, detail="Login desativado: defina GESTOR_SENHA no arquivo .env.")
    usuario_ok = hmac.compare_digest(dados.usuario.strip(), config.GESTOR_USUARIO)
    senha_ok = hmac.compare_digest(dados.senha, config.GESTOR_SENHA)
    if not (usuario_ok and senha_ok):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")
    response.set_cookie(COOKIE, criar_token(config.GESTOR_USUARIO), max_age=config.SESSAO_DURACAO_S,
                        httponly=True, samesite="strict", path="/")
    return {"usuario": config.GESTOR_USUARIO}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/sessao")
def sessao(mc_sessao: Optional[str] = Cookie(default=None)) -> dict:
    usuario = usuario_do_token(mc_sessao)
    return {"autenticado": usuario is not None, "usuario": usuario}
