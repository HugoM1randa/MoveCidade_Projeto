"""
Estado compartilhado do MoveCidade (em memória, thread-safe) com persistência em SQLite.

Objetos `Linha` e `Ponto` publicados são tratados como IMUTÁVEIS: toda edição cria um objeto
novo (dataclasses.replace) e troca a referência no dicionário. Assim as threads do simulador
sempre enxergam um traçado consistente.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from . import config, seed
from .cores import nome_da_cor, validar_cor
from .dominio import Linha, Ponto, Telemetria, Veiculo
from .eta import HistoricoTrechos, eta_simulacao, para_relogio_usuario, tempo_planejado_simulacao, tempo_percurso
from .geo import distancias_acumuladas, projetar_paradas
from .geo.tracado import CacheRotas, resolver_tracado
from .ia import GestorAlertas, Indicadores, frases_do_turno, resumo_de_turno
from .persistencia import Banco
from .simulador import CentralTelemetria

TOLERANCIA_PONTO_M = 15.0


class ErroNegocio(Exception):
    """Erro com mensagem em português simples e status HTTP."""

    def __init__(self, mensagem: str, status: int = 400) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def _traduzir_erro_validacao(exc: ValidationError) -> str:
    partes = []
    for erro in exc.errors()[:5]:
        campo = ".".join(str(c) for c in erro.get("loc", ())) or "pacote"
        tipo = erro.get("type", "")
        if tipo == "missing":
            partes.append(f"campo '{campo}' é obrigatório")
        elif tipo == "extra_forbidden":
            partes.append(f"campo '{campo}' não faz parte do contrato")
        elif tipo == "literal_error":
            partes.append(f"campo '{campo}' tem valor não permitido ({erro.get('msg')})")
        elif tipo.startswith(("greater", "less")):
            partes.append(f"campo '{campo}' fora do intervalo permitido ({erro.get('msg')})")
        else:
            partes.append(f"campo '{campo}' com tipo inválido ({erro.get('msg')})")
    return "Pacote de telemetria fora do contrato: " + "; ".join(partes) + "."


class Repositorio:
    def __init__(self, banco: Banco, cache: CacheRotas, usar_osrm: bool = True) -> None:
        self._lock = threading.RLock()
        self.banco = banco
        self.cache = cache
        self.usar_osrm = usar_osrm
        self._pontos: Dict[str, Ponto] = {}
        self._linhas: Dict[str, Linha] = {}
        self._veiculos: Dict[str, Veiculo] = {}
        self._telemetria: Dict[str, Telemetria] = {}
        self._recebido_em: Dict[str, float] = {}
        self._simuladores: Dict[str, CentralTelemetria] = {}
        self._viagens: Dict[str, Dict[str, Any]] = {}
        self._desvio: Dict[str, float] = {}
        self.historico = HistoricoTrechos()
        self.indicadores = Indicadores()
        self.alertas = GestorAlertas()
        self.versao_cadastro = 1
        self.pacotes_recebidos = 0
        self.pacotes_rejeitados = 0
        self.iniciado_em = datetime.now()

    # ================================================================== carga
    def carregar(self, semear: bool = True) -> None:
        if semear and self.banco.vazio():
            for p in seed.PONTOS:
                self.banco.salvar_ponto(Ponto(**p))
            for l in seed.LINHAS:
                pal = seed.PALETA[l["paleta"]]
                self.banco.salvar_linha(Linha(id=l["id"], numero=l["numero"], nome=l["nome"], cor=pal["cor"],
                                              cor_nome=pal["nome"], padrao=pal["padrao"],
                                              intervalo_min=l["intervalo_min"], pontos=list(l["pontos"])))
            for v in seed.VEICULOS:
                self.banco.salvar_veiculo(Veiculo(**v))
        with self._lock:
            self._pontos = {p.id: p for p in self.banco.carregar_pontos()}
            self._veiculos = {v.id: v for v in self.banco.carregar_veiculos()}
            linhas = self.banco.carregar_linhas()
        for linha in linhas:
            linha.pontos = [pid for pid in linha.pontos if pid in self._pontos]
            self._publicar_linha(self._tracar(linha))

    def _tracar(self, linha: Linha) -> Linha:
        """Calcula o traçado (volta fechada passando pelos pontos na ordem) e projeta os pontos."""
        coords = [self._pontos[pid].coord for pid in linha.pontos if pid in self._pontos]
        if len(coords) < 2:
            return dataclasses.replace(linha, rota=list(coords), acumulado=[0.0] * len(coords),
                                       s_pontos=[0.0] * len(coords), origem_tracado="LOCAL")
        waypoints = coords + [coords[0]]
        rota, origem = resolver_tracado(waypoints, self.cache, usar_osrm=self.usar_osrm)
        acumulado = distancias_acumuladas(rota)
        s_pontos = projetar_paradas(rota, acumulado, coords)
        s_pontos[0] = 0.0
        anterior = self._linhas.get(linha.id)
        versao = (anterior.versao_tracado + 1) if anterior else 1
        return dataclasses.replace(linha, rota=rota, acumulado=acumulado, s_pontos=s_pontos,
                                   origem_tracado=origem, versao_tracado=versao)

    def _publicar_linha(self, linha: Linha) -> None:
        with self._lock:
            anterior = self._linhas.get(linha.id)
            self._linhas[linha.id] = linha
            self.versao_cadastro += 1
        if anterior is not None and anterior.rota != linha.rota:
            self.historico.limpar_linha(linha.id)

    def _retracar_em_segundo_plano(self, linha_ids: List[str]) -> None:
        def tarefa() -> None:
            for lid in linha_ids:
                linha = self.linha(lid)
                if linha is not None:
                    self._publicar_linha(self._tracar(linha))
        threading.Thread(target=tarefa, name="retracar", daemon=True).start()

    # ============================================================== consultas
    def linha(self, linha_id: str) -> Optional[Linha]:
        with self._lock:
            return self._linhas.get(linha_id)

    def linhas(self) -> List[Linha]:
        with self._lock:
            return sorted(self._linhas.values(), key=lambda l: (len(l.numero), l.numero))

    def ponto(self, ponto_id: str) -> Optional[Ponto]:
        with self._lock:
            return self._pontos.get(ponto_id)

    def pontos(self) -> List[Ponto]:
        with self._lock:
            return sorted(self._pontos.values(), key=lambda p: p.nome)

    def veiculo(self, veiculo_id: str) -> Optional[Veiculo]:
        with self._lock:
            return self._veiculos.get(veiculo_id)

    def veiculos(self, linha_id: Optional[str] = None) -> List[Veiculo]:
        with self._lock:
            lista = sorted(self._veiculos.values(), key=lambda v: v.id)
        return [v for v in lista if linha_id is None or v.linha_id == linha_id]

    def linhas_do_ponto(self, ponto_id: str) -> List[Linha]:
        return [l for l in self.linhas() if ponto_id in l.pontos]

    def pontos_ativos_da_linha(self, linha: Linha) -> List[bool]:
        with self._lock:
            return [bool(self._pontos.get(pid) and self._pontos[pid].operando) for pid in linha.pontos]

    def telemetria(self, veiculo_id: str) -> Optional[Telemetria]:
        with self._lock:
            return self._telemetria.get(veiculo_id)

    def ao_vivo(self, veiculo_id: str) -> bool:
        with self._lock:
            recebido = self._recebido_em.get(veiculo_id)
            veiculo = self._veiculos.get(veiculo_id)
        return (veiculo is not None and veiculo.ativo and recebido is not None
                and time.monotonic() - recebido <= config.SEM_SINAL_APOS_S)

    def segundos_desde_sinal(self, veiculo_id: str) -> Optional[float]:
        with self._lock:
            recebido = self._recebido_em.get(veiculo_id)
        return None if recebido is None else time.monotonic() - recebido

    def posicao_s(self, veiculo_id: str, linha: Linha) -> Optional[float]:
        tel = self.telemetria(veiculo_id)
        if tel is None or tel.route_id != linha.id:
            return None
        return tel.route_progress * linha.comprimento

    def desvio_horario_s(self, veiculo_id: str) -> Optional[float]:
        with self._lock:
            return self._desvio.get(veiculo_id)

    def simulador(self, veiculo_id: str) -> Optional[CentralTelemetria]:
        with self._lock:
            return self._simuladores.get(veiculo_id)

    # ================================================================== frota
    def iniciar_frota(self, aquecer_s: float = 900.0) -> None:
        """Distribui os ônibus de cada linha ao longo da volta e aquece o histórico de velocidade."""
        if not config.SIMULADOR_ATIVO:
            return
        for linha in self.linhas():
            frota = [v for v in self.veiculos(linha.id) if v.ativo]
            for i, veiculo in enumerate(frota):
                s0 = linha.comprimento * i / max(1, len(frota))
                self._iniciar_simulador(veiculo, s0, aquecer_s)

    def _iniciar_simulador(self, veiculo: Veiculo, s_inicial: float, aquecer_s: float = 0.0) -> None:
        sim = CentralTelemetria(veiculo, self, s_inicial=s_inicial)
        # aquecimento silencioso: preenche a velocidade média histórica dos trechos
        passos = int(aquecer_s / 5.0)
        for _ in range(passos):
            sim.passo(5.0)
        with self._lock:
            antigo = self._simuladores.pop(veiculo.id, None)
            self._simuladores[veiculo.id] = sim
        if antigo:
            antigo.encerrar()
        sim.start()

    def _parar_simulador(self, veiculo_id: str) -> None:
        with self._lock:
            sim = self._simuladores.pop(veiculo_id, None)
            self._telemetria.pop(veiculo_id, None)
            self._recebido_em.pop(veiculo_id, None)
        if sim:
            sim.encerrar()

    def parar_tudo(self) -> None:
        with self._lock:
            sims = list(self._simuladores.values())
            self._simuladores.clear()
        for sim in sims:
            sim.encerrar()

    # =============================================================== ingestão
    def ingerir(self, payload: Any) -> Telemetria:
        """Valida tipos e intervalos do contrato e guarda o pacote. Erros → ErroNegocio(422)."""
        try:
            tel = Telemetria.model_validate(payload)
        except ValidationError as exc:
            self.pacotes_rejeitados += 1
            raise ErroNegocio(_traduzir_erro_validacao(exc), 422) from exc
        veiculo = self.veiculo(tel.vehicle_id)
        if veiculo is None:
            self.pacotes_rejeitados += 1
            raise ErroNegocio(f"Veículo '{tel.vehicle_id}' não está cadastrado.", 422)
        if veiculo.linha_id != tel.route_id:
            self.pacotes_rejeitados += 1
            raise ErroNegocio(f"O veículo '{tel.vehicle_id}' pertence à linha {veiculo.linha_id}, "
                              f"não à linha {tel.route_id}.", 422)
        agora = time.monotonic()
        with self._lock:
            anterior = self._telemetria.get(tel.vehicle_id)
            self._telemetria[tel.vehicle_id] = tel
            self._recebido_em[tel.vehicle_id] = agora
            self.pacotes_recebidos += 1
        linha = self.linha(tel.route_id)
        if linha is not None and linha.comprimento > 0:
            self._processar_eventos(tel, anterior, linha, agora)
        return tel

    def _indice_ponto_em(self, linha: Linha, s: float) -> Optional[int]:
        for i, sp in enumerate(linha.s_pontos):
            if abs(sp - s) <= TOLERANCIA_PONTO_M:
                return i
        return None

    def _processar_eventos(self, tel: Telemetria, anterior: Optional[Telemetria], linha: Linha, agora: float) -> None:
        vid = tel.vehicle_id
        ativos = self.pontos_ativos_da_linha(linha)
        s = tel.route_progress * linha.comprimento

        # --- viagem: início (quando o trip_id muda) --------------------------
        viagem = self._viagens.get(vid)
        if viagem is None or viagem["trip_id"] != tel.trip_id:
            planejado = tempo_planejado_simulacao(linha, ativos, 0.0, s) / config.FATOR_TEMPO
            viagem = {"trip_id": tel.trip_id, "inicio": agora - planejado, "estimada": s > TOLERANCIA_PONTO_M,
                      "encerrada": False}
            self._viagens[vid] = viagem

        decorrido_sim = (agora - viagem["inicio"]) * config.FATOR_TEMPO

        # --- chegada a um ponto (transição em trânsito → parado) ---------------
        chegou = tel.is_at_stop and (anterior is None or not anterior.is_at_stop)
        if chegou and not viagem["encerrada"]:
            k = self._indice_ponto_em(linha, s)
            fim_da_volta = (k == 0 and anterior is not None and anterior.route_progress > 0.5)
            if fim_da_volta:
                planejado = tempo_planejado_simulacao(linha, ativos, 0.0, linha.comprimento + 1)
                self.indicadores.registrar_chegada(decorrido_sim - planejado)
                if not viagem["estimada"]:
                    self.indicadores.registrar_viagem(decorrido_sim)
                viagem["encerrada"] = True
            elif k is not None and k > 0:
                planejado = tempo_planejado_simulacao(linha, ativos, 0.0, linha.s_pontos[k])
                self.indicadores.registrar_chegada(decorrido_sim - planejado)

        self.indicadores.registrar_ocupacao(tel.occupancy_rate)

        # --- desvio em relação ao horário programado ---------------------------
        if not viagem["encerrada"]:
            desvio = decorrido_sim - tempo_planejado_simulacao(linha, ativos, 0.0, s)
            with self._lock:
                self._desvio[vid] = desvio
        else:
            desvio = 0.0
            with self._lock:
                self._desvio[vid] = 0.0

        self._detectar_anomalias(tel, linha, ativos, s, desvio)

    # ============================================================== anomalias
    def _detectar_anomalias(self, tel: Telemetria, linha: Linha, ativos: List[bool], s: float, desvio: float) -> None:
        vid = tel.vehicle_id
        perto = tel.current_stop if tel.is_at_stop else tel.next_stop

        if tel.anomaly_flag == "CRITICAL_OVERCROWDING" or tel.occupancy_rate >= config.LIMITE_LOTACAO_CRITICA:
            pct = round(tel.occupancy_rate * 100)
            self.alertas.sinalizar(
                tipo="lotacao", chave=f"lotacao:{vid}", linha_id=linha.id, veiculo_id=vid,
                titulo=f"Lotação crítica · {pct}%",
                descricao=f"Ônibus {vid} com {tel.passenger_count} passageiros para {tel.passenger_capacity} lugares, perto de {perto}.",
                sugestao=f"Colocar um ônibus reserva na linha {linha.numero} para dividir a demanda.",
                acao={"tipo": "reforco", "linha_id": linha.id, "veiculo_id": vid})

        if desvio > config.ATRASO_ALERTA_S:
            minutos = max(1, round(para_relogio_usuario(desvio) / 60))
            self.alertas.sinalizar(
                tipo="atraso", chave=f"atraso:{vid}", linha_id=linha.id, veiculo_id=vid,
                titulo=f"Atraso excessivo · {minutos} min",
                descricao=f"Ônibus {vid} está {minutos} min atrás do horário programado, perto de {perto}.",
                sugestao=f"Colocar um ônibus reserva na linha {linha.numero} para cobrir o intervalo.",
                acao={"tipo": "reforco", "linha_id": linha.id, "veiculo_id": vid})

        if tel.accessibility_button:
            self.alertas.sinalizar(
                tipo="acessibilidade", chave=f"acessibilidade:{vid}", linha_id=linha.id, veiculo_id=vid,
                titulo=f"Pedido de acessibilidade · ônibus {vid}",
                descricao=f"Um passageiro pediu apoio de acessibilidade {'no ponto' if tel.is_at_stop else 'a caminho de'} {perto}.",
                sugestao="Avisar o motorista para baixar a rampa e aguardar o embarque com calma.",
                acao={"tipo": "acessibilidade", "veiculo_id": vid})

        # comboiamento: tempo até alcançar o ônibus da frente na mesma linha
        lider, intervalo = self._onibus_a_frente(linha, ativos, vid, s, tel.is_at_stop)
        if lider is not None and 0 < intervalo < config.COMBOIO_LIMITE_S:
            segundos = round(para_relogio_usuario(intervalo))
            par = "|".join(sorted([vid, lider]))
            self.alertas.sinalizar(
                tipo="comboio", chave=f"comboio:{par}", linha_id=linha.id, veiculo_id=vid,
                titulo="Comboiamento · 2 ônibus juntos",
                descricao=f"Ônibus {vid} está só {segundos} s atrás do ônibus {lider}.",
                sugestao=f"Segurar o ônibus {vid} por 1 minuto no próximo ponto para espaçar os horários.",
                acao={"tipo": "segurar", "veiculo_id": vid, "segundos": 60})

    def _onibus_a_frente(self, linha: Linha, ativos: List[bool], vid: str, s: float, em_parada: bool):
        melhor_id, melhor_t = None, float("inf")
        for outro in self.veiculos(linha.id):
            if outro.id == vid or not self.ao_vivo(outro.id):
                continue
            s_outro = self.posicao_s(outro.id, linha)
            if s_outro is None:
                continue
            t = eta_simulacao(linha, self.historico, ativos, s, em_parada, s_outro)
            if t < melhor_t:
                melhor_id, melhor_t = outro.id, t
        return melhor_id, melhor_t

    def intervalos_atuais(self) -> List[float]:
        """Intervalo (s de simulação) entre cada ônibus ao vivo e o da frente, em todas as linhas."""
        intervalos: List[float] = []
        for linha in self.linhas():
            ativos = self.pontos_ativos_da_linha(linha)
            vivos = [v for v in self.veiculos(linha.id) if self.ao_vivo(v.id)]
            if len(vivos) < 2:
                continue
            for v in vivos:
                tel = self.telemetria(v.id)
                s = self.posicao_s(v.id, linha)
                if tel is None or s is None:
                    continue
                _, t = self._onibus_a_frente(linha, ativos, v.id, s, tel.is_at_stop)
                if t != float("inf"):
                    intervalos.append(t)
        return intervalos

    # ============================================================= indicadores
    def kpis(self) -> Dict[str, Any]:
        ativos_cadastrados = [v for v in self.veiculos() if v.ativo]
        vivos = sum(1 for v in ativos_cadastrados if self.ao_vivo(v.id))
        duracoes = []
        for linha in self.linhas():
            if linha.comprimento > 0:
                ativos = self.pontos_ativos_da_linha(linha)
                duracoes.append(tempo_percurso(linha, self.historico, 0.0, linha.comprimento)
                                + sum(ativos[1:]) * config.PARADA_MEDIA_S)
        return self.indicadores.instantaneo(
            ativos=vivos, cadastrados=len(ativos_cadastrados), intervalos_sim_s=self.intervalos_atuais(),
            duracao_estimada_sim_s=(sum(duracoes) / len(duracoes)) if duracoes else None)

    def status_veiculo(self, veiculo_id: str) -> Dict[str, str]:
        """Status operacional com código + texto (a interface mostra ícone + texto, nunca só cor)."""
        veiculo = self.veiculo(veiculo_id)
        if veiculo is None or not veiculo.ativo:
            return {"codigo": "inativo", "texto": "fora de operação"}
        if not self.ao_vivo(veiculo_id):
            return {"codigo": "sem_sinal", "texto": "sem sinal GPS"}
        tel = self.telemetria(veiculo_id)
        if tel and (tel.anomaly_flag == "CRITICAL_OVERCROWDING" or tel.occupancy_rate >= config.LIMITE_LOTACAO_CRITICA):
            return {"codigo": "lotacao", "texto": "lotação crítica"}
        desvio = self.desvio_horario_s(veiculo_id) or 0.0
        if desvio > config.ATRASO_ALERTA_S or (tel and tel.anomaly_flag == "UNEXPECTED_DELAY"):
            return {"codigo": "atraso", "texto": "atraso"}
        return {"codigo": "operando", "texto": "operando"}

    def status_linha(self, linha: Linha) -> Dict[str, str]:
        frota = [v for v in self.veiculos(linha.id) if v.ativo]
        if not frota:
            return {"codigo": "sem_veiculos", "texto": "sem veículos"}
        estados = [self.status_veiculo(v.id)["codigo"] for v in frota]
        if all(e == "sem_sinal" for e in estados):
            return {"codigo": "sem_sinal", "texto": "sem sinal GPS"}
        if any(e == "atraso" for e in estados):
            return {"codigo": "atraso", "texto": "atraso"}
        return {"codigo": "operando", "texto": "operando"}

    def resumo_turno(self) -> Dict[str, Any]:
        kpis = self.kpis()
        pendentes = self.alertas.pendentes()
        critica = None
        contagem: Dict[str, int] = {}
        for a in pendentes:
            contagem[a["linha_id"]] = contagem.get(a["linha_id"], 0) + 1
        if contagem:
            lid = max(contagem, key=contagem.get)
            linha = self.linha(lid)
            if linha:
                tipos = sorted({a["tipo_texto"].lower() for a in pendentes if a["linha_id"] == lid})
                n = contagem[lid]
                critica = {"numero": linha.numero,
                           "motivo": f"{n} {'aviso pendente' if n == 1 else 'avisos pendentes'} de {', '.join(tipos)}"}
        frases = frases_do_turno(kpis, pendentes=pendentes, detectados=dict(self.alertas.total_detectados),
                                 decisoes=self.banco.decisoes_recentes(200), linha_critica=critica)
        return resumo_de_turno(frases)

    # ============================================================== decisões
    def decidir_alerta(self, alerta_id: str, decisao: str) -> Dict[str, Any]:
        if decisao not in ("aceitar", "ignorar"):
            raise ErroNegocio("A decisão deve ser 'aceitar' ou 'ignorar'.")
        alerta = self.alertas.retirar(alerta_id)
        if alerta is None:
            raise ErroNegocio("Este alerta não está mais pendente.", 404)
        resultado = "Nenhuma ação executada (sugestão ignorada pelo gestor)."
        if decisao == "aceitar":
            resultado = self._executar_acao(alerta["acao"])
        registro = self.banco.registrar_decisao({
            "alerta_id": alerta_id, "tipo": alerta["tipo"], "linha_id": alerta["linha_id"],
            "veiculo_id": alerta["veiculo_id"], "titulo": alerta["titulo"], "sugestao": alerta["sugestao"],
            "decisao": "aceito" if decisao == "aceitar" else "ignorado", "resultado": resultado,
            "decidido_em": datetime.now().isoformat(timespec="seconds"),
        })
        return registro

    def _executar_acao(self, acao: Dict[str, Any]) -> str:
        tipo = acao.get("tipo")
        if tipo == "reforco":
            linha = self.linha(acao["linha_id"])
            if linha is None:
                return "A linha não existe mais; nada foi feito."
            frota = self.veiculos(linha.id)
            if len(frota) >= config.MAX_VEICULOS_POR_LINHA:
                return f"A linha {linha.numero} já tem {len(frota)} ônibus (máximo); nenhum reserva foi colocado."
            n = 1
            while self.veiculo(f"{linha.numero}-R{n}"):
                n += 1
            novo = Veiculo(id=f"{linha.numero}-R{n}", linha_id=linha.id, capacidade=80, acessivel=True)
            s_ref = self.posicao_s(acao.get("veiculo_id", ""), linha) or 0.0
            self.banco.salvar_veiculo(novo)
            with self._lock:
                self._veiculos[novo.id] = novo
                self.versao_cadastro += 1
            if config.SIMULADOR_ATIVO:
                self._iniciar_simulador(novo, (s_ref + 400.0) % max(1.0, linha.comprimento))
            return f"Ônibus reserva {novo.id} colocado na linha {linha.numero}."
        if tipo == "segurar":
            sim = self.simulador(acao["veiculo_id"])
            if sim is None:
                return "O ônibus não está mais em operação; nada foi feito."
            sim.segurar(float(acao.get("segundos", 60)) * config.FATOR_TEMPO)
            return f"O ônibus {acao['veiculo_id']} vai esperar 1 min a mais no próximo ponto."
        if tipo == "acessibilidade":
            sim = self.simulador(acao["veiculo_id"])
            if sim:
                sim.confirmar_acessibilidade()
            return f"Motorista do ônibus {acao['veiculo_id']} avisado para dar apoio no embarque."
        return "Nenhuma ação associada."

    def pedir_acessibilidade(self, veiculo_id: str) -> None:
        sim = self.simulador(veiculo_id)
        if sim is None or not self.ao_vivo(veiculo_id):
            raise ErroNegocio("Este ônibus está sem sinal agora. Tente de novo em instantes.", 409)
        sim.pedir_acessibilidade()

    # =========================================================== CRUD: pontos
    def salvar_ponto(self, dados: Dict[str, Any], ponto_id: Optional[str] = None) -> Ponto:
        nome = str(dados.get("nome") or "").strip()
        if not nome:
            raise ErroNegocio("Informe o nome do ponto.")
        try:
            lat, lon = float(dados["lat"]), float(dados["lon"])
        except (KeyError, TypeError, ValueError):
            raise ErroNegocio("Informe as coordenadas do ponto (latitude e longitude).")
        if not (-21.70 <= lat <= -21.50 and -48.45 <= lon <= -48.28):
            raise ErroNegocio("As coordenadas precisam ficar dentro da área de Matão.")
        status = dados.get("status", "operando")
        if status not in ("operando", "desativado"):
            raise ErroNegocio("Status inválido. Use 'operando' ou 'desativado'.")
        acess = dados.get("acessibilidade") or {}
        anterior = self.ponto(ponto_id) if ponto_id else None
        if ponto_id and anterior is None:
            raise ErroNegocio("Ponto não encontrado.", 404)
        if not ponto_id:
            base = "".join(c if c.isalnum() else "-" for c in nome.lower()).strip("-")[:30] or "ponto"
            ponto_id, n = base, 2
            while self.ponto(ponto_id):
                ponto_id, n = f"{base}-{n}", n + 1
        ponto = Ponto(id=ponto_id, nome=nome, referencia=str(dados.get("referencia") or "").strip(),
                      lat=round(lat, 6), lon=round(lon, 6),
                      acessibilidade={k: bool(acess.get(k, False)) for k in ("rampa", "piso_tatil", "abrigo")},
                      status=status)
        self.banco.salvar_ponto(ponto)
        with self._lock:
            self._pontos[ponto.id] = ponto
            self.versao_cadastro += 1
        if anterior and (anterior.lat, anterior.lon) != (ponto.lat, ponto.lon):
            self._retracar_em_segundo_plano([l.id for l in self.linhas_do_ponto(ponto.id)])
        return ponto

    def remover_ponto(self, ponto_id: str) -> None:
        if self.ponto(ponto_id) is None:
            raise ErroNegocio("Ponto não encontrado.", 404)
        usadas = self.linhas_do_ponto(ponto_id)
        if usadas:
            raise ErroNegocio("Este ponto ainda é usado pelas linhas " + ", ".join(l.numero for l in usadas)
                              + ". Tire o ponto dessas linhas ou marque-o como desativado.", 409)
        self.banco.remover_ponto(ponto_id)
        with self._lock:
            self._pontos.pop(ponto_id, None)
            self.versao_cadastro += 1

    # =========================================================== CRUD: linhas
    def cores_em_uso(self, exceto: Optional[str] = None) -> List[str]:
        return [l.cor for l in self.linhas() if l.id != exceto]

    def proxima_cor_livre(self) -> Dict[str, str]:
        usadas = {c.upper() for c in self.cores_em_uso()}
        for item in seed.PALETA:
            if item["cor"].upper() not in usadas:
                return item
        return {"cor": "", "nome": "", "padrao": "continuo"}

    def salvar_linha(self, dados: Dict[str, Any], linha_id: Optional[str] = None) -> Linha:
        anterior = self.linha(linha_id) if linha_id else None
        if linha_id and anterior is None:
            raise ErroNegocio("Linha não encontrada.", 404)
        numero = str(dados.get("numero") or (anterior.numero if anterior else "")).strip()
        if not numero or len(numero) > 6 or not numero.replace("-", "").isalnum():
            raise ErroNegocio("Informe o número da linha (até 6 letras ou números, ex.: 410).")
        if not anterior and any(l.numero == numero for l in self.linhas()):
            raise ErroNegocio(f"Já existe uma linha {numero}.", 409)
        nome = str(dados.get("nome") or "").strip()
        if not nome:
            raise ErroNegocio("Informe o nome da linha (ex.: Centro – Jardim Paraíso).")
        pontos = [str(p) for p in (dados.get("pontos") or [])]
        if len(pontos) < 2:
            raise ErroNegocio("A linha precisa de pelo menos 2 pontos.")
        if len(set(pontos)) != len(pontos):
            raise ErroNegocio("Um mesmo ponto não pode aparecer duas vezes na linha.")
        faltando = [p for p in pontos if self.ponto(p) is None]
        if faltando:
            raise ErroNegocio("Pontos inexistentes: " + ", ".join(faltando))
        livre = self.proxima_cor_livre()
        cor = str(dados.get("cor") or (anterior.cor if anterior else livre["cor"])).strip().upper()
        ok, motivo = validar_cor(cor, self.cores_em_uso(exceto=linha_id))
        if not ok:
            raise ErroNegocio(motivo or "Cor reprovada.", 422)
        try:
            intervalo = int(dados.get("intervalo_min") or (anterior.intervalo_min if anterior else 15))
        except (TypeError, ValueError):
            raise ErroNegocio("O intervalo programado deve ser um número de minutos.")
        if not 3 <= intervalo <= 120:
            raise ErroNegocio("O intervalo programado deve ficar entre 3 e 120 minutos.")
        padroes = ("continuo", "tracejado", "pontilhado", "traco_ponto")
        padrao = dados.get("padrao") or (anterior.padrao if anterior else livre.get("padrao", "continuo"))
        if padrao not in padroes:
            padrao = "continuo"
        paleta = next((p for p in seed.PALETA if p["cor"].upper() == cor), None)
        cor_nome = paleta["nome"] if paleta else nome_da_cor(cor)

        nova = Linha(id=anterior.id if anterior else numero, numero=numero, nome=nome, cor=cor, cor_nome=cor_nome,
                     padrao=padrao, intervalo_min=intervalo, pontos=pontos)
        if anterior and anterior.pontos == pontos:
            nova = dataclasses.replace(nova, rota=anterior.rota, acumulado=anterior.acumulado,
                                       s_pontos=anterior.s_pontos, origem_tracado=anterior.origem_tracado,
                                       versao_tracado=anterior.versao_tracado)
            self.banco.salvar_linha(nova)
            self._publicar_linha(nova)
        else:
            self.banco.salvar_linha(nova)
            self._publicar_linha(self._tracar(nova))
        return self.linha(nova.id)  # type: ignore[return-value]

    def remover_linha(self, linha_id: str) -> None:
        if self.linha(linha_id) is None:
            raise ErroNegocio("Linha não encontrada.", 404)
        for v in self.veiculos(linha_id):
            self._parar_simulador(v.id)
        self.banco.remover_linha(linha_id)
        with self._lock:
            self._linhas.pop(linha_id, None)
            for vid in [v.id for v in self._veiculos.values() if v.linha_id == linha_id]:
                del self._veiculos[vid]
            self.versao_cadastro += 1
        self.alertas.remover_da_linha(linha_id)
        self.historico.limpar_linha(linha_id)

    # ========================================================= CRUD: veículos
    def criar_veiculo(self, dados: Dict[str, Any]) -> Veiculo:
        linha = self.linha(str(dados.get("linha_id") or ""))
        if linha is None:
            raise ErroNegocio("Escolha uma linha existente para o ônibus.")
        frota = self.veiculos(linha.id)
        if len(frota) >= config.MAX_VEICULOS_POR_LINHA:
            raise ErroNegocio(f"A linha {linha.numero} já tem o máximo de {config.MAX_VEICULOS_POR_LINHA} ônibus.", 409)
        try:
            capacidade = int(dados.get("capacidade") or 70)
        except (TypeError, ValueError):
            raise ErroNegocio("A capacidade deve ser um número.")
        if not 10 <= capacidade <= 200:
            raise ErroNegocio("A capacidade deve ficar entre 10 e 200 passageiros.")
        vid = str(dados.get("id") or "").strip()
        if not vid:
            letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            vid = next(f"{linha.numero}-{l}" for l in letras if not self.veiculo(f"{linha.numero}-{l}"))
        if self.veiculo(vid):
            raise ErroNegocio(f"Já existe um ônibus com o código {vid}.", 409)
        veiculo = Veiculo(id=vid, linha_id=linha.id, capacidade=capacidade, acessivel=bool(dados.get("acessivel")))
        self.banco.salvar_veiculo(veiculo)
        with self._lock:
            self._veiculos[vid] = veiculo
            self.versao_cadastro += 1
        if config.SIMULADOR_ATIVO:
            self._iniciar_simulador(veiculo, 0.0)
        return veiculo

    def remover_veiculo(self, veiculo_id: str) -> None:
        if self.veiculo(veiculo_id) is None:
            raise ErroNegocio("Ônibus não encontrado.", 404)
        self._parar_simulador(veiculo_id)
        self.banco.remover_veiculo(veiculo_id)
        with self._lock:
            self._veiculos.pop(veiculo_id, None)
            self.versao_cadastro += 1
