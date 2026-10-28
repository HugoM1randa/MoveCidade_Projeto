import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Minus, Plus } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { Linha, Ponto, VeiculoMapa } from '../tipos';
import { tracoDoPadrao } from '../util/formato';
import { CENTRO_MATAO, deslocar, type Posicao } from '../util/geo';

const reduzMovimento = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/**
 * Mapa base OpenStreetMap, dessaturado por CSS (visual claro e discreto) para as cores das linhas se destacarem.
 * Zoom e créditos ficam numa faixa ABAIXO do mapa: controles por cima do mapa cobririam marcadores
 * (alvos de toque encobertos, WCAG 2.5.8).
 */
export function MapaBase({ rotulo, className, aoPronto, zoom = 14, centro = CENTRO_MATAO }: {
  rotulo: string; className?: string; aoPronto: (m: L.Map | null) => void; zoom?: number; centro?: [number, number];
}) {
  const div = useRef<HTMLDivElement>(null);
  const mapaRef = useRef<L.Map | null>(null);
  useEffect(() => {
    if (!div.current) return;
    const mapa = L.map(div.current, { zoomControl: false, attributionControl: false, zoomAnimation: !reduzMovimento(),
      fadeAnimation: !reduzMovimento(), markerZoomAnimation: !reduzMovimento() }).setView(centro, zoom);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(mapa);
    const container = mapa.getContainer();
    container.setAttribute('role', 'region');
    container.setAttribute('aria-label', rotulo);
    mapaRef.current = mapa;
    aoPronto(mapa);
    const observador = new ResizeObserver(() => mapa.invalidateSize());
    observador.observe(div.current);
    return () => {
      observador.disconnect();
      aoPronto(null);
      mapaRef.current = null;
      mapa.remove();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="mapa-wrap">
      <div ref={div} className={`mapa ${className ?? ''}`} />
      <div className="mapa-rodape">
        <span className="creditos">
          © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">colaboradores do OpenStreetMap</a> · <a href="https://leafletjs.com" target="_blank" rel="noreferrer">Leaflet</a>
        </span>
        <span className="zoom">
          <button type="button" className="botao-icone" onClick={() => mapaRef.current?.zoomIn()} aria-label="Aproximar o mapa"><Plus aria-hidden="true" size={20} /></button>
          <button type="button" className="botao-icone" onClick={() => mapaRef.current?.zoomOut()} aria-label="Afastar o mapa"><Minus aria-hidden="true" size={20} /></button>
        </span>
      </div>
    </div>
  );
}

/** Enter ou Espaço num marcador focado equivale ao clique (o Leaflet só deixa o marcador focável). */
function ativarPorTeclado(m: L.Marker) {
  const el = m.getElement();
  if (!el) return;
  el.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      ev.stopPropagation();
      m.fire('click');
    }
  });
}

/** Traçado das linhas: contorno branco + cor da linha + padrão (contínuo, tracejado, pontilhado, traço-ponto). */
export function useCamadaRotas(mapa: L.Map | null, linhas: Linha[], opcoes: { visiveis?: Set<string>; destaque?: string | null; fraco?: boolean } = {}) {
  const { visiveis, destaque, fraco } = opcoes;
  const chaveVisiveis = visiveis ? [...visiveis].sort().join(',') : '*';
  useEffect(() => {
    if (!mapa) return;
    const grupo = L.layerGroup().addTo(mapa);
    for (const linha of linhas) {
      if (!linha.rota || linha.rota.length < 2) continue;
      if (visiveis && !visiveis.has(linha.id)) continue;
      const apagada = destaque && destaque !== linha.id;
      const opacidade = apagada ? 0.25 : fraco ? 0.75 : 1;
      L.polyline(linha.rota, { color: '#FFFFFF', weight: 9, opacity: opacidade, interactive: false, lineCap: 'round' }).addTo(grupo);
      L.polyline(linha.rota, {
        color: linha.cor, weight: 5, opacity: opacidade, interactive: false,
        dashArray: tracoDoPadrao(linha.padrao), lineCap: 'round', lineJoin: 'round',
      }).addTo(grupo);
    }
    return () => {
      grupo.remove();
    };
  }, [mapa, linhas, chaveVisiveis, destaque, fraco]); // eslint-disable-line react-hooks/exhaustive-deps
}

/** Marcadores de ponto. Interativos = focáveis (Tab) com nome acessível; Enter abre o ponto. */
export function useCamadaPontos(mapa: L.Map | null, pontos: Ponto[], opcoes: {
  destacados?: string[]; aoSelecionar?: (p: Ponto) => void; interativo?: boolean; selecionado?: string | null; mostrarDesativados?: boolean;
} = {}) {
  const { destacados = [], aoSelecionar, interativo = true, selecionado, mostrarDesativados = false } = opcoes;
  const callback = useRef(aoSelecionar);
  callback.current = aoSelecionar;
  const chave = destacados.join(',');
  useEffect(() => {
    if (!mapa) return;
    const grupo = L.layerGroup().addTo(mapa);
    for (const p of pontos) {
      if (p.status !== 'operando' && !mostrarDesativados) continue;
      const ordem = destacados.indexOf(p.id);
      const destaque = ordem >= 0;
      const sel = selecionado === p.id;
      const html = `<span class="ponto-marcador${destaque ? ' destaque' : ''}${sel ? ' selecionado' : ''}">${destaque ? ordem + 1 : ''}</span>`;
      const tamanho = destaque || sel ? 30 : 24;
      const ativo = interativo || destaque;
      const m = L.marker([p.lat, p.lon], {
        icon: L.divIcon({ html, className: 'ponto-icone', iconSize: [tamanho, tamanho], iconAnchor: [tamanho / 2, tamanho / 2] }),
        interactive: ativo, keyboard: ativo, title: '', zIndexOffset: destaque || sel ? 950 : 900,
      }).addTo(grupo);
      const el = m.getElement();
      if (el) {
        if (ativo) {
          el.setAttribute('role', 'button');
          el.setAttribute('aria-label', `Ponto ${p.nome}${destaque ? `, número ${ordem + 1} da lista` : ''}. Linhas ${p.linhas_atendidas.join(', ')}.`);
        } else {
          el.setAttribute('aria-hidden', 'true');
        }
      }
      if (ativo) {
        m.on('click', () => callback.current?.(p));
        ativarPorTeclado(m);
      }
    }
    return () => {
      grupo.remove();
    };
  }, [mapa, pontos, chave, interativo, selecionado, mostrarDesativados]); // eslint-disable-line react-hooks/exhaustive-deps
}

/**
 * Ônibus em movimento: ícone na cor da linha com o número. Só ônibus com sinal recente ("ao vivo").
 * Clicáveis com mouse/toque, mas fora da ordem do Tab: alvos que andam a cada 2 s e se sobrepõem
 * atrapalham o teclado (WCAG 2.5.8). A mesma função existe em lista ("Ver em lista" / tabela da frota).
 */
export function useCamadaOnibus(mapa: L.Map | null, veiculos: VeiculoMapa[], opcoes: {
  visiveis?: Set<string>; aoSelecionar?: (v: VeiculoMapa) => void; interativo?: boolean; selecionado?: string | null;
} = {}) {
  const { visiveis, aoSelecionar, interativo = false, selecionado } = opcoes;
  const marcadores = useRef(new Map<string, L.Marker>());
  const callback = useRef(aoSelecionar);
  callback.current = aoSelecionar;
  const veiculosRef = useRef(veiculos);
  veiculosRef.current = veiculos;

  useEffect(() => {
    if (!mapa) return;
    const atuais = marcadores.current;
    const vistos = new Set<string>();
    for (const v of veiculos) {
      if (!v.ao_vivo) continue;
      if (visiveis && !visiveis.has(v.linha_id)) continue;
      vistos.add(v.id);
      const conteudo = `${v.numero}${v.acessivel ? '<span class="onibus-acess">♿</span>' : ''}`;
      const classe = `onibus-marcador${selecionado === v.id ? ' selecionado' : ''}`;
      const rotulo = `Ônibus ${v.id}, linha ${v.numero}, cor ${v.cor_nome}${v.acessivel ? ', acessível' : ''}. Próximo ponto: ${v.proximo_ponto ?? 'sem informação'}.`;
      let m = atuais.get(v.id);
      if (!m) {
        m = L.marker([v.lat, v.lon], {
          icon: L.divIcon({ html: `<span class="${classe}" style="background:${v.cor}">${conteudo}</span>`, className: 'onibus-icone', iconSize: [48, 28], iconAnchor: [24, 14] }),
          interactive: interativo, keyboard: false, zIndexOffset: 800, title: '',
        }).addTo(mapa);
        const id = v.id;
        if (interativo) {
          m.on('click', () => {
            const atual = veiculosRef.current.find((x) => x.id === id);
            if (atual) callback.current?.(atual);
          });
        }
        atuais.set(v.id, m);
      } else {
        m.setLatLng([v.lat, v.lon]);
      }
      // atualiza o conteúdo sem recriar o elemento (o foco do teclado não se perde a cada 2 s)
      const el = m.getElement();
      if (el) {
        const interno = el.firstElementChild as HTMLElement | null;
        if (interno) {
          if (interno.className !== classe) interno.className = classe;
          if (interno.innerHTML !== conteudo) interno.innerHTML = conteudo;
          interno.style.background = v.cor;
        }
        el.setAttribute('aria-hidden', 'true');
        el.title = rotulo;
      }
    }
    for (const [id, m] of atuais) {
      if (!vistos.has(id)) {
        m.remove();
        atuais.delete(id);
      }
    }
  }, [mapa, veiculos, visiveis, interativo, selecionado]);

  useEffect(() => () => {
    for (const m of marcadores.current.values()) m.remove();
    marcadores.current.clear();
  }, [mapa]);
}

const PASSO_M = 25;
const PASSO_LONGO_M = 100;

/**
 * Pino "Você está aqui" (localização SIMULADA). Move por toque no mapa, arraste ou teclado:
 * Tab até o pino, setas movem ~25 m (Shift: ~100 m) e Enter confirma — alternativa ao arraste (WCAG 2.5.7).
 */
export function usePino(mapa: L.Map | null, pino: Posicao, aoMover: (p: Posicao) => void, aoConfirmar: () => void, moverPorToque = true) {
  const marcador = useRef<L.Marker | null>(null);
  const posicao = useRef(pino);
  posicao.current = pino;
  const mover = useRef(aoMover);
  mover.current = aoMover;
  const confirmar = useRef(aoConfirmar);
  confirmar.current = aoConfirmar;

  useEffect(() => {
    if (!mapa) return;
    const icone = L.divIcon({
      className: 'pino-icone',
      html: '<span class="pino"><svg viewBox="0 0 24 32" width="30" height="40" aria-hidden="true"><path d="M12 1C6 1 1.5 5.4 1.5 11.2 1.5 19 12 31 12 31s10.5-12 10.5-19.8C22.5 5.4 18 1 12 1z" fill="#111827" stroke="#fff" stroke-width="2"/><circle cx="12" cy="11" r="4.2" fill="#fff"/></svg></span>',
      iconSize: [44, 48], iconAnchor: [22, 44],
    });
    const m = L.marker([posicao.current.lat, posicao.current.lon], { icon: icone, draggable: true, keyboard: false, zIndexOffset: 1000, autoPan: true }).addTo(mapa);
    marcador.current = m;
    const el = m.getElement()!;
    el.tabIndex = 0;
    el.setAttribute('role', 'application');
    el.setAttribute('aria-roledescription', 'pino de localização');
    el.setAttribute('aria-label', 'Você está aqui (localização simulada). Use as setas para mover o pino; com Shift ele anda mais rápido. Enter confirma.');
    const aoTeclar = (ev: KeyboardEvent) => {
      const passo = ev.shiftKey ? PASSO_LONGO_M : PASSO_M;
      const deslocamentos: Record<string, [number, number]> = {
        ArrowUp: [0, passo], ArrowDown: [0, -passo], ArrowLeft: [-passo, 0], ArrowRight: [passo, 0],
      };
      if (ev.key in deslocamentos) {
        ev.preventDefault();
        ev.stopPropagation();
        const [l, n] = deslocamentos[ev.key];
        const nova = deslocar(posicao.current, l, n);
        m.setLatLng([nova.lat, nova.lon]);
        mapa.panInside([nova.lat, nova.lon], { padding: [40, 40], animate: !reduzMovimento() });
        mover.current(nova);
      } else if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        ev.stopPropagation();
        confirmar.current();
      }
    };
    el.addEventListener('keydown', aoTeclar);
    m.on('dragend', () => {
      const ll = m.getLatLng();
      mover.current({ lat: +ll.lat.toFixed(6), lon: +ll.lng.toFixed(6) });
      confirmar.current();
    });
    const aoClicar = (e: L.LeafletMouseEvent) => {
      const nova = { lat: +e.latlng.lat.toFixed(6), lon: +e.latlng.lng.toFixed(6) };
      m.setLatLng(e.latlng);
      mover.current(nova);
      confirmar.current();
    };
    if (moverPorToque) mapa.on('click', aoClicar);
    return () => {
      el.removeEventListener('keydown', aoTeclar);
      mapa.off('click', aoClicar);
      m.remove();
      marcador.current = null;
    };
  }, [mapa, moverPorToque]);

  // sincroniza quando o pino muda por fora (botão "colocar no centro")
  useEffect(() => {
    const m = marcador.current;
    if (!m) return;
    const ll = m.getLatLng();
    if (Math.abs(ll.lat - pino.lat) > 1e-7 || Math.abs(ll.lng - pino.lon) > 1e-7) m.setLatLng([pino.lat, pino.lon]);
  }, [pino]);
}
