import type L from 'leaflet';
import { Accessibility, Bus, Layers, List, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ErroApi, query } from '../api';
import { AcessibilidadePonto, BadgeLinha, BotaoFavorito, EtiquetaAcessivel, EtiquetaLotacao, TempoGrande, usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { useCatalogo } from '../estado/Catalogo';
import { usePreferencias } from '../estado/Preferencias';
import { usePolling } from '../estado/usePolling';
import { MapaBase, useCamadaOnibus, useCamadaPontos, useCamadaRotas, usePino } from '../mapa/Mapa';
import type { Linha, Ponto, PontoComChegadas, VeiculoMapa } from '../tipos';
import { caminhada, distancia, nomePadrao, tracoDoPadrao, trajetoCurto } from '../util/formato';
import { haversine } from '../util/geo';
import { LinhaChegada } from './CartaoPonto';

function sem(texto: string) {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

export function MapaAoVivo() {
  const titulo = usePagina('Mapa ao vivo');
  const [params, setParams] = useSearchParams();
  const { linhas, pontos, pontoPorId, linhaPorId } = useCatalogo();
  const { pino, setPino, filtros } = usePreferencias();
  const [mapa, setMapa] = useState<L.Map | null>(null);
  const [ocultas, setOcultas] = useState<Set<string>>(new Set());
  const [legendaAberta, setLegendaAberta] = useState(false);
  const [modoLista, setModoLista] = useState(false);
  const [termo, setTermo] = useState('');

  const pontoSel = params.get('ponto');
  const veiculoSel = params.get('veiculo');
  const linhaFoco = params.get('linha');
  const { dados: frota } = usePolling<{ veiculos: VeiculoMapa[] }>('/api/veiculos/mapa', 2000);
  // filtro "Somente veículos acessíveis" (tela Acessibilidade) vale também para o mapa
  const veiculos = (frota?.veiculos ?? []).filter((v) => !filtros.somenteAcessiveis || v.acessivel);

  const visiveis = useMemo(() => new Set(linhas.map((l) => l.id).filter((id) => !ocultas.has(id))), [linhas, ocultas]);

  useCamadaRotas(mapa, linhas, { visiveis, destaque: linhaFoco });
  useCamadaPontos(mapa, pontos, { interativo: true, selecionado: pontoSel, aoSelecionar: (p) => abrirPonto(p.id, false) });
  useCamadaOnibus(mapa, veiculos, { visiveis, interativo: true, selecionado: veiculoSel, aoSelecionar: (v) => abrirVeiculo(v.id) });
  usePino(mapa, pino, setPino, () => {}, false);

  // foco inicial vindo de "Ver no mapa" (linha) ou de um ponto
  useEffect(() => {
    if (!mapa) return;
    if (linhaFoco) {
      const l = linhaPorId.get(linhaFoco);
      if (l?.rota?.length) mapa.fitBounds(l.rota, { padding: [30, 30] });
    } else if (pontoSel) {
      const p = pontoPorId.get(pontoSel);
      if (p) mapa.setView([p.lat, p.lon], 16);
    }
  }, [mapa, linhaFoco, linhaPorId.size]); // eslint-disable-line react-hooks/exhaustive-deps

  function abrirPonto(id: string, centralizar = true) {
    const p = pontoPorId.get(id);
    if (centralizar && p) mapa?.setView([p.lat, p.lon], Math.max(16, mapa.getZoom()));
    setParams((atual) => {
      const n = new URLSearchParams(atual);
      n.set('ponto', id);
      n.delete('veiculo');
      return n;
    }, { replace: true });
  }
  function abrirVeiculo(id: string) {
    setParams((atual) => {
      const n = new URLSearchParams(atual);
      n.set('veiculo', id);
      n.delete('ponto');
      return n;
    }, { replace: true });
  }
  function fecharFolha() {
    setParams((atual) => {
      const n = new URLSearchParams(atual);
      n.delete('ponto');
      n.delete('veiculo');
      return n;
    }, { replace: true });
  }

  const sugestoes = useMemo(() => {
    const t = sem(termo.trim());
    if (!t) return [];
    const ls = linhas.filter((l) => l.numero.startsWith(t) || sem(l.nome).includes(t)).map((l) => ({ tipo: 'linha' as const, l }));
    const ps = pontos.filter((p) => p.status === 'operando' && sem(p.nome).includes(t)).map((p) => ({ tipo: 'ponto' as const, p }));
    return [...ls, ...ps].slice(0, 6);
  }, [termo, linhas, pontos]);

  function escolherLinha(l: Linha) {
    setTermo('');
    setOcultas((o) => {
      const n = new Set(o);
      n.delete(l.id);
      return n;
    });
    setParams({ linha: l.id }, { replace: true });
    if (l.rota?.length) mapa?.fitBounds(l.rota, { padding: [30, 30] });
  }

  function alternarLinha(id: string) {
    setOcultas((o) => {
      const n = new Set(o);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  return (
    <div className="pagina-mapa">
      <h1 ref={titulo} tabIndex={-1} className="sr-only">Mapa ao vivo</h1>
      <div className="mapa-barra">
        <div className="busca-mapa">
          <label htmlFor="busca-mapa" className="sr-only">Procurar linha ou ponto no mapa</label>
          <div className="campo-com-icone">
            <Search aria-hidden="true" size={20} />
            <input id="busca-mapa" type="search" placeholder="Linha ou ponto" value={termo} onChange={(e) => setTermo(e.target.value)}
              autoComplete="off" aria-describedby="busca-mapa-dica" />
          </div>
          <span id="busca-mapa-dica" className="sr-only">Os resultados aparecem logo abaixo do campo.</span>
          {sugestoes.length > 0 && (
            <ul className="sugestoes" aria-label="Resultados">
              {sugestoes.map((s) => (
                <li key={s.tipo === 'linha' ? `l${s.l.id}` : `p${s.p.id}`}>
                  {s.tipo === 'linha' ? (
                    <button type="button" onClick={() => escolherLinha(s.l)}>
                      <BadgeLinha numero={s.l.numero} cor={s.l.cor} corNome={s.l.cor_nome} nome={s.l.nome} /> {trajetoCurto(s.l.nome)}
                    </button>
                  ) : (
                    <button type="button" onClick={() => { setTermo(''); abrirPonto(s.p.id); }}>
                      Ponto {s.p.nome}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="mapa-botoes">
          <button type="button" className="botao secundario" aria-expanded={legendaAberta} aria-controls="legenda-linhas" onClick={() => setLegendaAberta((v) => !v)}>
            <Layers aria-hidden="true" size={20} /> Linhas
          </button>
          <button type="button" className="botao secundario" aria-pressed={modoLista} onClick={() => setModoLista((v) => !v)}>
            <List aria-hidden="true" size={20} /> Ver em lista
          </button>
        </div>
      </div>

      {legendaAberta && (
        <fieldset id="legenda-linhas" className="legenda">
          <legend>Mostrar ou ocultar linhas no mapa</legend>
          {linhas.map((l) => (
            <label key={l.id} className="legenda-item">
              <input type="checkbox" checked={!ocultas.has(l.id)} onChange={() => alternarLinha(l.id)} />
              <BadgeLinha numero={l.numero} cor={l.cor} corNome={l.cor_nome} nome={l.nome} />
              <svg width="44" height="12" aria-hidden="true">
                <line x1="2" y1="6" x2="42" y2="6" stroke="#fff" strokeWidth="8" strokeLinecap="round" />
                <line x1="2" y1="6" x2="42" y2="6" stroke={l.cor} strokeWidth="4" strokeLinecap="round" strokeDasharray={tracoDoPadrao(l.padrao)} />
              </svg>
              <span>{trajetoCurto(l.nome)} <span className="nota">· traço {nomePadrao(l.padrao)}</span></span>
            </label>
          ))}
        </fieldset>
      )}

      <div className={`mapa-area${modoLista ? ' com-lista' : ''}`}>
        <MapaBase rotulo="Mapa ao vivo com as linhas, os pontos e os ônibus de Matão" className="mapa-cheio" aoPronto={setMapa} zoom={14} />
        {modoLista && <ListaOnibus veiculos={veiculos.filter((v) => visiveis.has(v.linha_id))} aoMostrar={(v) => { abrirVeiculo(v.id); mapa?.setView([v.lat, v.lon], 16); }} />}
      </div>

      {pontoSel && pontoPorId.get(pontoSel) && <FolhaPonto ponto={pontoPorId.get(pontoSel)!} aoFechar={fecharFolha} />}
      {veiculoSel && <FolhaVeiculo veiculo={veiculos.find((v) => v.id === veiculoSel) ?? null} id={veiculoSel} aoFechar={fecharFolha} />}
    </div>
  );
}

function ListaOnibus({ veiculos, aoMostrar }: { veiculos: VeiculoMapa[]; aoMostrar: (v: VeiculoMapa) => void }) {
  const vivos = veiculos.filter((v) => v.ao_vivo).sort((a, b) => a.numero.localeCompare(b.numero) || a.id.localeCompare(b.id));
  return (
    <section className="lista-mapa" aria-labelledby="titulo-lista-onibus">
      <h2 id="titulo-lista-onibus">Ônibus em operação agora</h2>
      {!vivos.length ? <p className="vazio">Nenhum ônibus com sinal agora.</p> : (
        <ul>
          {vivos.map((v) => (
            <li key={v.id} className="cartao">
              <p className="favorito-titulo">
                <BadgeLinha numero={v.numero} cor={v.cor} corNome={v.cor_nome} nome={`ônibus ${v.id}`} /> Ônibus {v.id}
              </p>
              <p>Próximo ponto: <strong>{v.proximo_ponto}</strong> · <TempoGrande segundos={v.eta_proximo_s} fonte="ao_vivo" /></p>
              <div className="chegada-info">
                <EtiquetaLotacao lotacao={v.lotacao} />
                <EtiquetaAcessivel acessivel={v.acessivel} />
              </div>
              <button type="button" className="botao texto" onClick={() => aoMostrar(v)}>Ver detalhes no mapa<span className="sr-only"> do ônibus {v.id}</span></button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Folha({ titulo, aoFechar, children }: { titulo: string; aoFechar: () => void; children: ReactNode }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [aoFechar]);
  return (
    <section className="folha" aria-label={titulo}>
      <button type="button" className="botao-icone fechar" onClick={aoFechar} aria-label="Fechar">
        <X aria-hidden="true" size={22} />
      </button>
      {children}
    </section>
  );
}

function FolhaPonto({ ponto, aoFechar }: { ponto: Ponto; aoFechar: () => void }) {
  const { pino, filtros, favoritos, alternarFavorito } = usePreferencias();
  const { dados } = usePolling<PontoComChegadas>(`/api/pontos/${ponto.id}${query({ acessivel: filtros.somenteAcessiveis })}`, 2000);
  const d = haversine(pino, ponto);
  return (
    <Folha titulo={`Ponto ${ponto.nome}`} aoFechar={aoFechar}>
      <div className="cartao-topo">
        <h2 className="titulo-ponto">{ponto.nome}</h2>
        <BotaoFavorito ativo={favoritos.pontos.includes(ponto.id)} rotulo={`ponto ${ponto.nome}`} aoAlternar={() => alternarFavorito('pontos', ponto.id)} />
      </div>
      <div className="cartao-meta">
        <span>{distancia(d)} da sua localização · {caminhada(d)}</span>
        <AcessibilidadePonto a={ponto.acessibilidade} />
      </div>
      {dados ? (
        <ul className="lista-chegadas" aria-label={`Ônibus que passam em ${ponto.nome}`}>
          {dados.linhas.map((l) => <LinhaChegada key={l.linha_id} l={l} pontoId={ponto.id} />)}
        </ul>
      ) : <p className="nota">Carregando previsões…</p>}
      <p className="nota">Previsões sujeitas a variação.</p>
    </Folha>
  );
}

function FolhaVeiculo({ veiculo, id, aoFechar }: { veiculo: VeiculoMapa | null; id: string; aoFechar: () => void }) {
  const { setVeiculoSelecionado } = usePreferencias();
  const anunciar = useAnunciar();
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => setVeiculoSelecionado(id), [id, setVeiculoSelecionado]);

  async function acionar() {
    try {
      const r = await api.post<{ mensagem: string }>(`/api/veiculos/${id}/acessibilidade`);
      setMsg(r.mensagem);
      anunciar(r.mensagem);
    } catch (e) {
      const t = e instanceof ErroApi ? e.message : 'Não foi possível enviar o pedido.';
      setMsg(t);
      anunciar(t);
    }
  }

  return (
    <Folha titulo={`Ônibus ${id}`} aoFechar={aoFechar}>
      {!veiculo || !veiculo.ao_vivo ? (
        <p className="vazio">O ônibus {id} está sem sinal no momento. Não há previsão ao vivo para ele.</p>
      ) : (
        <>
          <h2 className="favorito-titulo">
            <BadgeLinha numero={veiculo.numero} cor={veiculo.cor} corNome={veiculo.cor_nome} nome={`ônibus ${veiculo.id}`} />
            <Bus aria-hidden="true" size={20} /> Ônibus {veiculo.id}
          </h2>
          <p>
            {veiculo.no_ponto ? 'Parado no ponto. ' : ''}Próximo ponto: <strong>{veiculo.proximo_ponto}</strong> ·{' '}
            <TempoGrande segundos={veiculo.eta_proximo_s} fonte="ao_vivo" />
          </p>
          <div className="chegada-info">
            <EtiquetaLotacao lotacao={veiculo.lotacao} />
            {veiculo.acessivel ? <EtiquetaAcessivel acessivel /> : <span className="etiqueta">sem elevador</span>}
          </div>
          <div className="acoes">
            <Link className="botao secundario" to={`/linha/${veiculo.linha_id}`}>Ver linha {veiculo.numero}</Link>
            <button type="button" className="botao primario" onClick={acionar}>
              <Accessibility aria-hidden="true" size={20} /> Acionar botão de acessibilidade
            </button>
          </div>
          {msg && <p className="aviso-ok">{msg}</p>}
          <p className="nota">Previsão sujeita a variação.</p>
        </>
      )}
    </Folha>
  );
}
