import { Accessibility, AlertTriangle, CalendarClock, Footprints, Radio, Star, Umbrella, Users, WifiOff } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import type { Acessibilidade, Fonte, Lotacao } from '../tipos';
import { rotuloLinha, tempoDeChegada, textoLotacao } from '../util/formato';

/** Badge da linha: cor da linha + número SEMPRE juntos (a cor nunca é a única informação). */
export function BadgeLinha({ numero, cor, corNome, nome, grande, semTextoOculto }: {
  numero: string; cor: string; corNome: string; nome: string; grande?: boolean; semTextoOculto?: boolean;
}) {
  return (
    <span className="badge-linha-wrap">
      <span className={`badge-linha${grande ? ' grande' : ''}`} style={{ background: cor }} aria-hidden="true">
        {numero}
      </span>
      {!semTextoOculto && <span className="sr-only">{rotuloLinha(numero, corNome, nome)}</span>}
    </span>
  );
}

export function TempoGrande({ segundos, fonte, horario }: { segundos: number | null; fonte: Fonte; horario?: string | null }) {
  if (fonte === 'sem_previsao' || segundos === null) {
    return <span className="tempo sem">sem previsão no momento</span>;
  }
  const t = tempoDeChegada(segundos);
  return (
    <span className={`tempo ${t.estado}`}>
      <span aria-hidden="true">{t.principal}</span>
      <span className="sr-only">{fonte === 'programado' && horario ? `programado para ${horario}, ${t.falado}` : t.falado}</span>
    </span>
  );
}

export function EtiquetaFonte({ fonte, horario }: { fonte: Fonte; horario?: string | null }) {
  if (fonte === 'ao_vivo') {
    return (
      <span className="etiqueta ao-vivo">
        <Radio aria-hidden="true" size={16} /> ao vivo
      </span>
    );
  }
  if (fonte === 'programado') {
    return (
      <span className="etiqueta programado">
        <CalendarClock aria-hidden="true" size={16} /> programado{horario ? ` ${horario}` : ''}
      </span>
    );
  }
  return (
    <span className="etiqueta sem-sinal">
      <WifiOff aria-hidden="true" size={16} /> sem previsão
    </span>
  );
}

export function EtiquetaLotacao({ lotacao, pct }: { lotacao: Lotacao | null; pct?: number }) {
  if (!lotacao) return null;
  const nivel = { baixa: 1, media: 2, alta: 3 }[lotacao];
  return (
    <span className={`etiqueta lotacao lotacao-${lotacao}`}>
      <span className="barras" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} className={i <= nivel ? 'cheia' : ''} />
        ))}
      </span>
      <Users aria-hidden="true" size={16} />
      {textoLotacao(lotacao)}
      {pct !== undefined && <span className="sr-only">, {pct}% ocupado</span>}
    </span>
  );
}

export function EtiquetaAcessivel({ acessivel }: { acessivel: boolean | null | undefined }) {
  if (!acessivel) return null;
  return (
    <span className="etiqueta acessivel">
      <Accessibility aria-hidden="true" size={16} /> acessível
    </span>
  );
}

export function AcessibilidadePonto({ a }: { a: Acessibilidade }) {
  const itens: { tem: boolean; icone: ReactNode; texto: string }[] = [
    { tem: a.rampa, icone: <Accessibility aria-hidden="true" size={16} />, texto: 'rampa' },
    { tem: a.piso_tatil, icone: <Footprints aria-hidden="true" size={16} />, texto: 'piso tátil' },
    { tem: a.abrigo, icone: <Umbrella aria-hidden="true" size={16} />, texto: 'abrigo' },
  ];
  const presentes = itens.filter((i) => i.tem);
  if (!presentes.length) return <span className="acess-ponto vazio">sem rampa ou piso tátil</span>;
  return (
    <ul className="acess-ponto" aria-label="Acessibilidade do ponto">
      {presentes.map((i) => (
        <li key={i.texto}>
          {i.icone}
          {i.texto}
        </li>
      ))}
    </ul>
  );
}

export function BotaoFavorito({ ativo, rotulo, aoAlternar }: { ativo: boolean; rotulo: string; aoAlternar: () => void }) {
  return (
    <button type="button" className={`botao-icone favorito${ativo ? ' ativo' : ''}`} aria-pressed={ativo} onClick={aoAlternar}
      title={ativo ? `Remover ${rotulo} dos favoritos` : `Favoritar ${rotulo}`}>
      <Star aria-hidden="true" size={22} fill={ativo ? 'currentColor' : 'none'} />
      <span className="sr-only">Favoritar {rotulo}</span>
    </button>
  );
}

export function AvisoErro({ texto }: { texto: string | null }) {
  if (!texto) return null;
  return (
    <p className="aviso-erro" role="status">
      <AlertTriangle aria-hidden="true" size={18} /> {texto}
    </p>
  );
}

export function Esqueleto({ linhas = 3 }: { linhas?: number }) {
  return (
    <div className="esqueleto" aria-hidden="true">
      {Array.from({ length: linhas }).map((_, i) => (
        <div key={i} className="esqueleto-bloco" />
      ))}
    </div>
  );
}

/** Título único por rota e foco no <h1> ao navegar (o leitor de tela anuncia a nova página). */
export function usePagina(titulo: string) {
  const ref = useRef<HTMLHeadingElement>(null);
  const local = useLocation();
  useEffect(() => {
    document.title = `${titulo} · MoveCidade`;
  }, [titulo]);
  useEffect(() => {
    if (window.history.state?.idx > 0 || local.key !== 'default') ref.current?.focus({ preventScroll: false });
  }, [local.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  return ref;
}
