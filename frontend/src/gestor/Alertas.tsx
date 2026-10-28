import { Check, RefreshCw, Sparkles, X } from 'lucide-react';
import { useState } from 'react';
import { api, ErroApi } from '../api';
import { AvisoErro, BadgeLinha, Esqueleto, usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { useCatalogo } from '../estado/Catalogo';
import { usePolling } from '../estado/usePolling';
import type { Alerta, Decisao } from '../tipos';
import { horaMinuto } from '../util/formato';

interface RespostaAlertas {
  pendentes: Alerta[];
  decisoes: Decisao[];
  resumo: { frases: string[]; texto: string; fonte: string; gerado_em: string };
}

export function Alertas() {
  const titulo = usePagina('Alertas da IA');
  const { linhaPorId } = useCatalogo();
  const anunciar = useAnunciar();
  const { dados, erro, carregando, atualizar } = usePolling<RespostaAlertas>('/api/gestor/alertas', 3000);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [resultado, setResultado] = useState<string | null>(null);

  async function decidir(a: Alerta, decisao: 'aceitar' | 'ignorar') {
    setOcupado(a.id);
    try {
      const r = await api.post<Decisao>(`/api/gestor/alertas/${a.id}/decisao`, { decisao });
      const texto = `${decisao === 'aceitar' ? 'Sugestão aceita' : 'Sugestão ignorada'}: ${r.resultado}`;
      setResultado(texto);
      anunciar(texto);
      atualizar();
      // o foco vai para o título da lista para não se perder com o item removido
      document.getElementById('t-pendentes')?.focus();
    } catch (e) {
      const t = e instanceof ErroApi ? e.message : 'Não foi possível registrar a decisão.';
      setResultado(t);
      anunciar(t);
      atualizar();
    } finally {
      setOcupado(null);
    }
  }

  const linha = (id: string | null) => (id ? linhaPorId.get(id) : undefined);

  return (
    <div className="pagina-gestor">
      <h1 ref={titulo} tabIndex={-1}>Alertas da IA e resumo do turno</h1>
      <AvisoErro texto={erro} />
      {carregando && !dados ? <Esqueleto /> : dados && (
        <div className="alertas-grade">
          <section aria-labelledby="t-pendentes">
            <h2 id="t-pendentes" tabIndex={-1}>Anomalias detectadas · Kharon + Hermes ({dados.pendentes.length})</h2>
            {resultado && <p className="aviso-ok">{resultado}</p>}
            {dados.pendentes.length === 0 ? <p className="vazio cartao">Nenhum alerta pendente. A operação está normal.</p> : (
              <ul className="lista-alertas">
                {dados.pendentes.map((a) => {
                  const l = linha(a.linha_id);
                  return (
                    <li key={a.id} className={`cartao alerta alerta-${a.tipo}`}>
                      <div className="alerta-topo">
                        {l && <BadgeLinha numero={l.numero} cor={l.cor} corNome={l.cor_nome} nome={l.nome} grande />}
                        <div>
                          <h3>{a.titulo}</h3>
                          <p className="nota">{a.tipo_texto} · detectado às {horaMinuto(a.criado_em)}</p>
                        </div>
                      </div>
                      <p>{a.descricao}</p>
                      <p className="sugestao"><Sparkles aria-hidden="true" size={18} /> <strong>Sugestão:</strong> {a.sugestao}</p>
                      <div className="acoes">
                        <button type="button" className="botao primario" disabled={ocupado === a.id} onClick={() => decidir(a, 'aceitar')}>
                          <Check aria-hidden="true" size={18} /> Aceitar<span className="sr-only"> sugestão: {a.titulo}</span>
                        </button>
                        <button type="button" className="botao secundario" disabled={ocupado === a.id} onClick={() => decidir(a, 'ignorar')}>
                          <X aria-hidden="true" size={18} /> Ignorar<span className="sr-only"> sugestão: {a.titulo}</span>
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="nota">A IA só sugere. Nada é executado sem o clique em “Aceitar”.</p>
          </section>

          <div className="coluna-lateral">
            <section className="cartao resumo" aria-labelledby="t-resumo">
              <div className="cartao-topo">
                <h2 id="t-resumo">Resumo do turno · gerado por Hermes</h2>
                <button type="button" className="botao-icone" onClick={atualizar} title="Atualizar resumo">
                  <RefreshCw aria-hidden="true" size={18} /><span className="sr-only">Atualizar resumo</span>
                </button>
              </div>
              {dados.resumo.fonte === 'llm' ? <p>{dados.resumo.texto}</p> : (
                <ul className="frases">{dados.resumo.frases.map((f) => <li key={f}>{f}</li>)}</ul>
              )}
              <p className="nota">Gerado às {horaMinuto(dados.resumo.gerado_em)} a partir dos dados da simulação. O gestor é o responsável final pelas decisões.</p>
            </section>

            <section className="cartao" aria-labelledby="t-decisoes">
              <h2 id="t-decisoes">Decisões registradas</h2>
              {dados.decisoes.length === 0 ? <p className="vazio">Nenhuma decisão ainda.</p> : (
                <div className="tabela-rolagem" tabIndex={0} role="region" aria-labelledby="t-decisoes">
                  <table className="tabela compacta">
                    <thead>
                      <tr><th scope="col">Hora</th><th scope="col">Alerta</th><th scope="col">Decisão</th><th scope="col">Resultado</th></tr>
                    </thead>
                    <tbody>
                      {dados.decisoes.map((d) => (
                        <tr key={d.id}>
                          <td>{horaMinuto(d.decidido_em)}</td>
                          <td>{d.linha_id ? `Linha ${d.linha_id} · ` : ''}{d.titulo}</td>
                          <td>{d.decisao === 'aceito' ? <span className="status status-operando"><Check aria-hidden="true" size={16} /> aceito</span> : <span className="status"><X aria-hidden="true" size={16} /> ignorado</span>}</td>
                          <td>{d.resultado}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
