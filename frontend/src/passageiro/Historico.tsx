import { ShieldCheck, Trash2 } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BadgeLinha, usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { usePreferencias } from '../estado/Preferencias';
import type { Viagem } from '../tipos';
import { duracao, horaMinuto, rotuloDia } from '../util/formato';

const PERIODOS = [
  { valor: '7', rotulo: '7 dias' },
  { valor: '30', rotulo: '30 dias' },
  { valor: 'tudo', rotulo: 'Tudo' },
];

export function Historico() {
  const titulo = usePagina('Histórico');
  const { historico, apagarHistorico } = usePreferencias();
  const anunciar = useAnunciar();
  const [periodo, setPeriodo] = useState('7');
  const idSelect = useId();

  const grupos = useMemo(() => {
    const limite = periodo === 'tudo' ? 0 : Date.now() - Number(periodo) * 86400000;
    const mapa = new Map<string, Viagem[]>();
    for (const v of historico.filter((x) => (x.fim ?? x.inicio) >= limite)) {
      const r = rotuloDia(new Date(v.inicio));
      mapa.set(r, [...(mapa.get(r) ?? []), v]);
    }
    return [...mapa.entries()];
  }, [historico, periodo]);

  function apagar() {
    if (!window.confirm('Apagar todo o histórico de viagens deste aparelho? Não dá para desfazer.')) return;
    apagarHistorico();
    anunciar('Histórico apagado.');
  }

  return (
    <div className="pagina estreita">
      <div className="cabecalho-pagina entre">
        <h1 ref={titulo} tabIndex={-1}>Histórico</h1>
        <div className="campo-linha">
          <label htmlFor={idSelect}>Período</label>
          <select id={idSelect} value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
            {PERIODOS.map((p) => <option key={p.valor} value={p.valor}>{p.rotulo}</option>)}
          </select>
        </div>
      </div>

      <p className="aviso-lgpd">
        <ShieldCheck aria-hidden="true" size={20} />
        Suas viagens ficam guardadas só neste aparelho. Nada é enviado ao servidor (LGPD).
      </p>

      {grupos.length === 0 ? (
        <div className="vazio cartao">
          <p>Nenhuma viagem {periodo === 'tudo' ? 'registrada' : `nos últimos ${periodo} dias`}.</p>
          <p>Para registrar: abra uma linha, toque em <strong>Embarquei neste ônibus</strong> e, ao descer, em <strong>Desembarquei</strong>.</p>
          <Link to="/" className="botao secundario">Ver pontos perto de você</Link>
        </div>
      ) : (
        grupos.map(([dia, viagens], i) => (
          <section key={dia} className="secao" aria-labelledby={`dia-${i}`}>
            <h2 id={`dia-${i}`}>{dia}</h2>
            <ul className="lista-historico">
              {viagens.map((v) => (
                <li key={v.id} className="cartao viagem">
                  <BadgeLinha numero={v.numero} cor={v.cor} corNome={v.cor_nome} nome={v.nome_linha} />
                  <div>
                    <p className="viagem-trecho">{v.origem_nome} <span aria-hidden="true">→</span><span className="sr-only">até</span> {v.destino_nome}</p>
                    <p className="nota">
                      {horaMinuto(v.inicio)} · {duracao((v.fim ?? v.inicio) - v.inicio)} ·{' '}
                      {v.atraso_min && v.atraso_min > 1 ? <span className="atrasou">atrasou {v.atraso_min} min</span> : <span>no horário</span>}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      {historico.length > 0 && (
        <button type="button" className="botao perigo" onClick={apagar}>
          <Trash2 aria-hidden="true" size={20} /> Apagar histórico
        </button>
      )}
    </div>
  );
}
