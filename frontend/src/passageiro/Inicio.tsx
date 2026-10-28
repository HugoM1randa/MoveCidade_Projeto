import type L from 'leaflet';
import { Crosshair, MapPin, Search } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { query } from '../api';
import { AvisoErro, BadgeLinha, Esqueleto, usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { useCatalogo } from '../estado/Catalogo';
import { usePreferencias } from '../estado/Preferencias';
import { usePolling } from '../estado/usePolling';
import { MapaBase, useCamadaOnibus, useCamadaPontos, useCamadaRotas, usePino } from '../mapa/Mapa';
import type { DetalheLinha, PontoComChegadas, RespostaProximos, VeiculoMapa } from '../tipos';
import { distancia, tempoDeChegada, trajetoCurto } from '../util/formato';
import type { Posicao } from '../util/geo';
import { CartaoPonto, LinhaChegada } from './CartaoPonto';

type TipoBusca = 'linhas' | 'pontos' | 'trajetos';

export function Inicio() {
  const titulo = usePagina('Início');
  const navegar = useNavigate();
  const anunciar = useAnunciar();
  const { linhas, pontos } = useCatalogo();
  const { pino, setPino, filtros, favoritos } = usePreferencias();
  const [mapa, setMapa] = useState<L.Map | null>(null);
  const [consulta, setConsulta] = useState<Posicao>(pino);
  const [termo, setTermo] = useState('');
  const [tipo, setTipo] = useState<TipoBusca>('linhas');
  const anunciarProxima = useRef(false);
  const estadosAnteriores = useRef(new Map<string, string>());

  // move o pino na hora; a consulta espera o usuário parar (evita uma requisição por tecla)
  useEffect(() => {
    const id = window.setTimeout(() => setConsulta(pino), 350);
    return () => window.clearTimeout(id);
  }, [pino]);

  const url = `/api/pontos/proximos${query({ lat: consulta.lat, lon: consulta.lon, raio: 800, limite: 3,
    acessivel: filtros.somenteAcessiveis })}`;
  const { dados, erro, carregando } = usePolling<RespostaProximos>(url, 2000);
  const { dados: frota } = usePolling<{ veiculos: VeiculoMapa[] }>('/api/veiculos/mapa', 2000);

  const proximos = dados?.pontos ?? [];
  const destacados = useMemo(() => proximos.map((p) => p.id), [proximos.map((p) => p.id).join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  useCamadaRotas(mapa, linhas, { fraco: true });
  useCamadaPontos(mapa, pontos, { destacados, interativo: false, aoSelecionar: (p) => focarCartao(p.id) });
  useCamadaOnibus(mapa, (frota?.veiculos ?? []).filter((v) => !filtros.somenteAcessiveis || v.acessivel));
  const dadosRef = useRef(dados);
  dadosRef.current = dados;
  usePino(mapa, pino, (p) => {
    anunciarProxima.current = true;
    setPino(p);
  }, () => {
    // Enter no pino: confirma e repete o ponto mais próximo (se a consulta já está em dia)
    const p = dadosRef.current?.pontos[0];
    if (p && !anunciarProxima.current) anunciar(`Localização confirmada. Ponto mais próximo: ${p.nome}, a ${distancia(p.distancia_m ?? 0)}.`);
  });

  // aria-live: anuncia a nova localização (uma vez por mudança) e quando um ônibus passa a "chegando"
  useEffect(() => {
    if (!dados) return;
    if (anunciarProxima.current) {
      anunciarProxima.current = false;
      const p = dados.pontos[0];
      anunciar(p ? `Localização atualizada. Ponto mais próximo: ${p.nome}, a ${distancia(p.distancia_m ?? 0)}.`
        : 'Localização atualizada. Nenhum ponto encontrado por perto.');
    }
    const anteriores = estadosAnteriores.current;
    for (const p of dados.pontos) {
      for (const l of p.linhas) {
        const chave = `${p.id}:${l.linha_id}`;
        const estado = l.fonte === 'ao_vivo' ? tempoDeChegada(l.eta_s).estado : 'sem';
        const antes = anteriores.get(chave);
        if (antes === 'minutos' && (estado === 'chegando' || estado === 'agora')) {
          anunciar(`Linha ${l.numero} chegando ao ponto ${p.nome}.`);
        }
        anteriores.set(chave, estado);
      }
    }
  }, [dados, anunciar]);

  function focarCartao(id: string) {
    const el = document.getElementById(`ponto-${id}`)?.querySelector('button, a') as HTMLElement | null;
    el?.focus();
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  function centralizarEm(p: PontoComChegadas) {
    mapa?.setView([p.lat, p.lon], Math.max(mapa.getZoom(), 16), { animate: true });
  }

  function pinoNoCentro() {
    if (!mapa) return;
    const c = mapa.getCenter();
    anunciarProxima.current = true;
    setPino({ lat: +c.lat.toFixed(6), lon: +c.lng.toFixed(6) });
  }

  function buscar(e: FormEvent) {
    e.preventDefault();
    if (!termo.trim()) return;
    navegar(`/busca${query({ q: termo.trim(), tipo })}`);
  }

  const filtrosAtivos = filtros.somenteAcessiveis ? ['somente ônibus acessíveis'] : [];

  return (
    <div className="pagina inicio">
      <div className="inicio-cabecalho">
        <h1 ref={titulo} tabIndex={-1}>Para onde você vai em Matão?</h1>
        <form role="search" className="busca" onSubmit={buscar} aria-label="Buscar linha, ponto ou trajeto">
          <label htmlFor="campo-busca" className="sr-only">Linha, ponto ou trajeto</label>
          <div className="campo-com-icone">
            <Search aria-hidden="true" size={20} />
            <input id="campo-busca" type="search" placeholder="Linha, ponto ou trajeto" value={termo}
              onChange={(e) => setTermo(e.target.value)} autoComplete="off" enterKeyHint="search" />
          </div>
          <fieldset className="filtro-busca">
            <legend className="sr-only">Buscar por</legend>
            {(['linhas', 'pontos', 'trajetos'] as TipoBusca[]).map((t) => (
              <label key={t} className={`chip${tipo === t ? ' ativo' : ''}`}>
                <input type="radio" name="tipo-busca" value={t} checked={tipo === t} onChange={() => setTipo(t)} />
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </label>
            ))}
          </fieldset>
          <button type="submit" className="botao primario">Buscar</button>
        </form>
      </div>

      <div className="inicio-grade">
        <section className="bloco-mapa" aria-labelledby="titulo-local">
          <h2 id="titulo-local" className="sr-only">Sua localização no mapa</h2>
          <div className="mapa-moldura">
            <MapaBase rotulo="Mapa de Matão com sua localização simulada, os pontos próximos e os ônibus" className="mapa-compacto" aoPronto={setMapa} zoom={15} centro={[pino.lat, pino.lon]} />
            <span className="selo-simulado"><MapPin aria-hidden="true" size={16} /> Localização simulada</span>
          </div>
          <p className="ajuda-mapa" id="ajuda-pino">
            Toque no mapa ou arraste o pino para mudar sua localização. Pelo teclado: Tab até o pino e use as setas.
          </p>
          <button type="button" className="botao secundario" onClick={pinoNoCentro}>
            <Crosshair aria-hidden="true" size={20} /> Colocar pino no centro do mapa
          </button>
        </section>

        <div className="coluna-listas">
          <section aria-labelledby="titulo-perto" className="secao">
            <h2 id="titulo-perto">Pontos perto de você</h2>
            {filtrosAtivos.length > 0 && (
              <p className="filtros-ativos">
                Filtros ligados: {filtrosAtivos.join(', ')}. <Link to="/acessibilidade">Mudar</Link>
              </p>
            )}
            <AvisoErro texto={erro} />
            {carregando && !dados ? (
              <Esqueleto linhas={3} />
            ) : proximos.length === 0 ? (
              <p className="vazio">Nenhum ponto encontrado por perto. Tente mover o pino.</p>
            ) : (
              <>
                {dados?.fora_do_raio && <p className="nota">Não há pontos a até 800 m. Este é o mais próximo:</p>}
                <ol className="lista-pontos">
                  {proximos.map((p, i) => (
                    <li key={p.id}>
                      <CartaoPonto ponto={p} ordem={i + 1} aoCentralizar={() => centralizarEm(p)} />
                    </li>
                  ))}
                </ol>
              </>
            )}
          </section>

          <Favoritos linhasFav={favoritos.linhas} pontosFav={favoritos.pontos} pino={consulta} />
        </div>
      </div>
    </div>
  );
}

function Favoritos({ linhasFav, pontosFav, pino }: { linhasFav: string[]; pontosFav: string[]; pino: Posicao }) {
  return (
    <section aria-labelledby="titulo-fav" className="secao">
      <h2 id="titulo-fav">Favoritos</h2>
      {!linhasFav.length && !pontosFav.length ? (
        <p className="vazio">Toque na estrela (★) de uma linha ou de um ponto para guardar aqui.</p>
      ) : (
        <ul className="lista-favoritos">
          {linhasFav.map((id) => <FavoritoLinha key={`l-${id}`} id={id} pino={pino} />)}
          {pontosFav.map((id) => <FavoritoPonto key={`p-${id}`} id={id} />)}
        </ul>
      )}
    </section>
  );
}

function FavoritoLinha({ id, pino }: { id: string; pino: Posicao }) {
  const { linhaPorId } = useCatalogo();
  const { filtros } = usePreferencias();
  const linha = linhaPorId.get(id);
  const { dados } = usePolling<DetalheLinha>(linha ? `/api/linhas/${id}/detalhe${query({ lat: pino.lat, lon: pino.lon, acessivel: filtros.somenteAcessiveis })}` : null, 4000);
  if (!linha) return null;
  return (
    <li className="cartao favorito-linha">
      <p className="favorito-titulo">
        <BadgeLinha numero={linha.numero} cor={linha.cor} corNome={linha.cor_nome} nome={linha.nome} />
        <Link to={`/linha/${id}${dados?.ponto ? `?ponto=${dados.ponto.id}` : ''}`}>{trajetoCurto(linha.nome)}</Link>
      </p>
      {dados?.previsao && dados.ponto && (
        <ul className="lista-chegadas compacta" aria-label={`Previsão no ponto ${dados.ponto.nome}`}>
          <LinhaChegada l={dados.previsao} pontoId={dados.ponto.id} />
        </ul>
      )}
      {dados?.ponto && <p className="nota">No ponto {dados.ponto.nome} · sujeito a variação</p>}
    </li>
  );
}

function FavoritoPonto({ id }: { id: string }) {
  const { filtros } = usePreferencias();
  const { dados } = usePolling<PontoComChegadas>(`/api/pontos/${id}${query({ acessivel: filtros.somenteAcessiveis })}`, 3000);
  if (!dados) return null;
  return (
    <li>
      <CartaoPonto ponto={dados} idTitulo={`fav-ponto-${id}`} />
    </li>
  );
}
