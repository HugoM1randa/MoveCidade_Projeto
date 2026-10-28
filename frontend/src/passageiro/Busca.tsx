import { ArrowLeft, Search } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { query } from '../api';
import { AvisoErro, BadgeLinha, Esqueleto, EtiquetaAcessivel, EtiquetaFonte, EtiquetaLotacao, TempoGrande, usePagina } from '../componentes/comuns';
import { usePreferencias } from '../estado/Preferencias';
import { usePolling } from '../estado/usePolling';
import type { ResultadoBusca } from '../tipos';
import { trajetoCurto } from '../util/formato';
import { CartaoPonto } from './CartaoPonto';

const TIPOS = [
  { valor: 'todos', rotulo: 'Tudo' },
  { valor: 'linhas', rotulo: 'Linhas' },
  { valor: 'pontos', rotulo: 'Pontos' },
  { valor: 'trajetos', rotulo: 'Trajetos' },
];

export function Busca() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const tipo = params.get('tipo') ?? 'todos';
  const titulo = usePagina(q ? `Busca: ${q}` : 'Busca');
  const navegar = useNavigate();
  const { pino, filtros } = usePreferencias();
  const [termo, setTermo] = useState(q);
  useEffect(() => setTermo(q), [q]);

  const url = q ? `/api/busca${query({ q, tipo, lat: pino.lat, lon: pino.lon, acessivel: filtros.somenteAcessiveis })}` : null;
  const { dados, erro, carregando } = usePolling<ResultadoBusca>(url, 3000);
  const total = (dados?.linhas.length ?? 0) + (dados?.pontos.length ?? 0);

  function enviar(e: FormEvent) {
    e.preventDefault();
    setParams({ q: termo.trim(), tipo });
  }

  return (
    <div className="pagina">
      <div className="cabecalho-pagina">
        <button type="button" className="botao-icone" onClick={() => navegar(-1)} aria-label="Voltar">
          <ArrowLeft aria-hidden="true" size={22} />
        </button>
        <h1 ref={titulo} tabIndex={-1}>Busca</h1>
      </div>
      <form role="search" className="busca" onSubmit={enviar} aria-label="Buscar linha, ponto ou trajeto">
        <label htmlFor="campo-busca-2" className="sr-only">Linha, ponto ou trajeto</label>
        <div className="campo-com-icone">
          <Search aria-hidden="true" size={20} />
          <input id="campo-busca-2" type="search" value={termo} onChange={(e) => setTermo(e.target.value)}
            placeholder="Ex.: 102, Matriz, Centro Jardim" autoComplete="off" />
        </div>
        <fieldset className="filtro-busca">
          <legend className="sr-only">Buscar por</legend>
          {TIPOS.map((t) => (
            <label key={t.valor} className={`chip${tipo === t.valor ? ' ativo' : ''}`}>
              <input type="radio" name="tipo" value={t.valor} checked={tipo === t.valor}
                onChange={() => setParams({ q: termo.trim() || q, tipo: t.valor })} />
              {t.rotulo}
            </label>
          ))}
        </fieldset>
        <button type="submit" className="botao primario">Buscar</button>
      </form>

      <AvisoErro texto={erro} />
      {!q ? (
        <p className="vazio">Digite o número de uma linha, o nome de um ponto ou de um bairro.</p>
      ) : carregando && !dados ? (
        <Esqueleto />
      ) : (
        <>
          <p className="contagem" role="status">
            {total === 0 ? `Nada encontrado para “${q}”. Tente outro nome ou número.` : `${total} resultado${total > 1 ? 's' : ''} para “${q}”`}
          </p>
          {!!dados?.linhas.length && (
            <section aria-labelledby="res-linhas" className="secao">
              <h2 id="res-linhas">Linhas</h2>
              <ul className="lista-resultados">
                {dados.linhas.map((l) => (
                  <li key={l.id}>
                    <Link className="cartao resultado-linha" to={`/linha/${l.id}${l.ponto_ref ? `?ponto=${l.ponto_ref.id}` : ''}`}>
                      <span className="resultado-topo">
                        <BadgeLinha numero={l.numero} cor={l.cor} corNome={l.cor_nome} nome={l.nome} grande />
                        <span className="resultado-nome">{trajetoCurto(l.nome)}</span>
                      </span>
                      {l.previsao && (
                        <span className="resultado-previsao">
                          <EtiquetaFonte fonte={l.previsao.fonte} horario={l.previsao.horario} />
                          {l.previsao.fonte !== 'sem_previsao' && (
                            <>
                              <span>chega em</span>
                              <TempoGrande segundos={l.previsao.eta_s} fonte={l.previsao.fonte} horario={l.previsao.horario} />
                            </>
                          )}
                          {l.ponto_ref && <span className="nota">no ponto {l.ponto_ref.nome}</span>}
                        </span>
                      )}
                      {l.previsao && (
                        <span className="chegada-info">
                          <EtiquetaLotacao lotacao={l.previsao.lotacao} />
                          <EtiquetaAcessivel acessivel={l.previsao.acessivel} />
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {!!dados?.pontos.length && (
            <section aria-labelledby="res-pontos" className="secao">
              <h2 id="res-pontos">Pontos</h2>
              <ul className="lista-pontos">
                {dados.pontos.map((p) => (
                  <li key={p.id}>
                    <CartaoPonto ponto={p} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {total > 0 && <p className="nota">Previsões sujeitas a variação.</p>}
        </>
      )}
    </div>
  );
}
