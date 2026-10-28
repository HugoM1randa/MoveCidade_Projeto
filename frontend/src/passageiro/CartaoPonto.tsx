import { Link } from 'react-router-dom';
import { AcessibilidadePonto, BadgeLinha, BotaoFavorito, EtiquetaAcessivel, EtiquetaFonte, EtiquetaLotacao, TempoGrande } from '../componentes/comuns';
import { usePreferencias } from '../estado/Preferencias';
import type { PontoComChegadas, PrevisaoLinha } from '../tipos';
import { caminhada, distancia, textoSeguinte } from '../util/formato';

export function LinhaChegada({ l, pontoId }: { l: PrevisaoLinha; pontoId: string }) {
  const seguinte = l.fonte !== 'sem_previsao' ? textoSeguinte(l.eta_seguinte_s) : null;
  return (
    <li>
      <Link to={`/linha/${l.linha_id}?ponto=${pontoId}`} className="chegada">
        <span className="chegada-linha">
          <BadgeLinha numero={l.numero} cor={l.cor} corNome={l.cor_nome} nome={l.nome} />
          <span className="destino">
            <span className="sr-only">sentido </span>
            <span aria-hidden="true">→ </span>
            {l.destino}
          </span>
        </span>
        <span className="chegada-tempo">
          <TempoGrande segundos={l.eta_s} fonte={l.fonte} horario={l.horario} />
          <span className="seguinte">{seguinte ?? ' '}</span>
        </span>
        <span className="chegada-info">
          <EtiquetaFonte fonte={l.fonte} horario={l.horario} />
          <EtiquetaLotacao lotacao={l.lotacao} />
          <EtiquetaAcessivel acessivel={l.acessivel} />
        </span>
      </Link>
    </li>
  );
}

export function CartaoPonto({ ponto, ordem, aoCentralizar, idTitulo }: {
  ponto: PontoComChegadas; ordem?: number; aoCentralizar?: () => void; idTitulo?: string;
}) {
  const { favoritos, alternarFavorito } = usePreferencias();
  const id = idTitulo ?? `ponto-${ponto.id}`;
  return (
    <article className="cartao cartao-ponto" aria-labelledby={id}>
      <header className="cartao-topo">
        {ordem !== undefined && <span className="num-ponto" aria-hidden="true">{ordem}</span>}
        <h3 id={id} className="titulo-ponto">
          {aoCentralizar ? (
            <button type="button" className="link-ponto" onClick={aoCentralizar} title="Mostrar no mapa">
              {ponto.nome}
            </button>
          ) : (
            <Link to={`/mapa?ponto=${ponto.id}`} className="link-ponto">{ponto.nome}</Link>
          )}
        </h3>
        <BotaoFavorito ativo={favoritos.pontos.includes(ponto.id)} rotulo={`ponto ${ponto.nome}`} aoAlternar={() => alternarFavorito('pontos', ponto.id)} />
      </header>
      <div className="cartao-meta">
        {ponto.distancia_m !== undefined && (
          <span>
            {distancia(ponto.distancia_m)} · {caminhada(ponto.distancia_m)}
          </span>
        )}
        <AcessibilidadePonto a={ponto.acessibilidade} />
      </div>
      {ponto.linhas.length ? (
        <ul className="lista-chegadas" aria-label={`Ônibus que passam em ${ponto.nome}`}>
          {ponto.linhas.map((l) => (
            <LinhaChegada key={l.linha_id} l={l} pontoId={ponto.id} />
          ))}
        </ul>
      ) : (
        <p className="vazio">Nenhuma linha passa neste ponto agora.</p>
      )}
      <p className="nota">Previsões sujeitas a variação.</p>
    </article>
  );
}
