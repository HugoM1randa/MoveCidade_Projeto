import { ArrowLeft, Bus, Map as MapIcon, WifiOff } from 'lucide-react';
import { useId, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { query } from '../api';
import { Abas } from '../componentes/Abas';
import { AcessibilidadePonto, AvisoErro, BotaoFavorito, Esqueleto, EtiquetaAcessivel, EtiquetaFonte, EtiquetaLotacao, TempoGrande, usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { useCatalogo } from '../estado/Catalogo';
import { usePreferencias } from '../estado/Preferencias';
import { usePolling } from '../estado/usePolling';
import type { DetalheLinha as Detalhe, ProximoVeiculo, TipoDia } from '../tipos';
import { rotuloLinha, tempoDeChegada, trajetoCurto } from '../util/formato';

export function DetalheLinha() {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const navegar = useNavigate();
  const { linhaPorId } = useCatalogo();
  const linhaCat = linhaPorId.get(id);
  const titulo = usePagina(linhaCat ? `Linha ${linhaCat.numero}` : 'Linha');
  const { pino, filtros, favoritos, alternarFavorito } = usePreferencias();
  const [aba, setAba] = useState('proximos');
  const idSelect = useId();

  const pontoParam = params.get('ponto');
  const url = `/api/linhas/${encodeURIComponent(id)}/detalhe${query({ ponto: pontoParam, lat: pontoParam ? undefined : pino.lat,
    lon: pontoParam ? undefined : pino.lon, acessivel: filtros.somenteAcessiveis })}`;
  const { dados, erro, carregando } = usePolling<Detalhe>(url, 2000);

  if (!dados && carregando) return <div className="pagina"><h1 ref={titulo} tabIndex={-1}>Linha</h1><Esqueleto linhas={4} /></div>;
  if (!dados) {
    return (
      <div className="pagina">
        <h1 ref={titulo} tabIndex={-1}>Linha não encontrada</h1>
        <AvisoErro texto={erro} />
        <Link to="/" className="botao secundario">Voltar ao início</Link>
      </div>
    );
  }
  const { linha, ponto, previsao } = dados;

  return (
    <div className="pagina detalhe-linha">
      <div className="cabecalho-linha" style={{ background: linha.cor }}>
        <button type="button" className="botao-icone claro" onClick={() => navegar(-1)} aria-label="Voltar">
          <ArrowLeft aria-hidden="true" size={22} />
        </button>
        <div className="cabecalho-linha-texto">
          <h1 ref={titulo} tabIndex={-1}>
            <span className="sr-only">{rotuloLinha(linha.numero, linha.cor_nome, linha.nome)}</span>
            <span aria-hidden="true">Linha {linha.numero}</span>
          </h1>
          <p aria-hidden="true">{trajetoCurto(linha.nome)}</p>
        </div>
        <BotaoFavorito ativo={favoritos.linhas.includes(linha.id)} rotulo={`linha ${linha.numero}`} aoAlternar={() => alternarFavorito('linhas', linha.id)} />
      </div>

      <div className="escolha-ponto">
        <label htmlFor={idSelect}>Seu ponto</label>
        <select id={idSelect} value={ponto?.id ?? ''} onChange={(e) => setParams({ ponto: e.target.value }, { replace: true })}>
          {dados.trajeto.filter((t) => t.operando).map((t) => (
            <option key={t.id} value={t.id}>{t.ordem}. {t.nome}</option>
          ))}
        </select>
      </div>

      {previsao && ponto && (
        <section className="destaque-previsao" aria-labelledby="titulo-previsao">
          <h2 id="titulo-previsao" className="sr-only">Previsão de chegada</h2>
          <div className="numero-grande">
            {previsao.fonte === 'sem_previsao' || previsao.eta_s === null ? (
              <span className="tempo sem">sem previsão no momento</span>
            ) : (
              <NumeroGrande segundos={previsao.eta_s} />
            )}
          </div>
          <p>
            Previsão de chegada ao ponto <strong>{ponto.nome}</strong> <span className="nota">(sujeito a variação)</span>
          </p>
          <EtiquetaFonte fonte={previsao.fonte} horario={previsao.horario} />
        </section>
      )}

      <AvisoErro texto={erro} />

      <Abas rotulo={`Informações da linha ${linha.numero}`} ativa={aba} aoTrocar={setAba} abas={[
        { id: 'proximos', rotulo: 'Próximos', conteudo: <AbaProximos dados={dados} /> },
        { id: 'horarios', rotulo: 'Horários', conteudo: <AbaHorarios dados={dados} /> },
        { id: 'trajeto', rotulo: 'Trajeto', conteudo: <AbaTrajeto dados={dados} /> },
      ]} />

      <Link className="botao secundario largo" to={`/mapa?linha=${linha.id}`}>
        <MapIcon aria-hidden="true" size={20} /> Ver no mapa
      </Link>
    </div>
  );
}

function NumeroGrande({ segundos }: { segundos: number }) {
  const t = tempoDeChegada(segundos);
  if (t.estado !== 'minutos') return <span className={`tempo ${t.estado}`}>{t.principal}</span>;
  const [n, ...resto] = t.principal.split(' ');
  return (
    <span className="tempo minutos">
      <span className="n" aria-hidden="true">{n}</span> <span className="u" aria-hidden="true">{resto.join(' ')}</span>
      <span className="sr-only">{t.falado}</span>
    </span>
  );
}

function AbaProximos({ dados }: { dados: Detalhe }) {
  const { viagemAtual, embarcar } = usePreferencias();
  const anunciar = useAnunciar();
  const { linha, ponto } = dados;

  function aoEmbarcar(v: ProximoVeiculo) {
    if (!ponto) return;
    embarcar({
      id: `${Date.now()}`, linha_id: linha.id, numero: linha.numero, cor: linha.cor, cor_nome: linha.cor_nome, nome_linha: linha.nome,
      veiculo_id: v.veiculo_id, origem_id: ponto.id, origem_nome: ponto.nome, inicio: Date.now(),
    });
    anunciar(`Embarque registrado no ônibus ${v.veiculo_id}, no ponto ${ponto.nome}. Toque em Desembarquei ao descer.`);
  }

  if (!dados.proximos.length && !dados.sem_sinal.length) {
    return <p className="vazio">Nenhum ônibus desta linha está em operação agora.</p>;
  }
  return (
    <>
      <ul className="lista-veiculos">
        {dados.proximos.map((v) => (
          <li key={v.veiculo_id} className="cartao veiculo">
            <div className="veiculo-topo">
              <span className="veiculo-nome"><Bus aria-hidden="true" size={18} /> Ônibus {v.veiculo_id}</span>
              <TempoGrande segundos={v.eta_s} fonte="ao_vivo" />
            </div>
            <div className="medidor" role="img" aria-label={`Ocupação de ${v.ocupacao_pct}%`}>
              <span style={{ width: `${Math.min(100, v.ocupacao_pct)}%` }} className={`medidor-${v.lotacao}`} />
            </div>
            <div className="chegada-info">
              <EtiquetaLotacao lotacao={v.lotacao} pct={v.ocupacao_pct} />
              <EtiquetaAcessivel acessivel={v.acessivel} />
              <span className="etiqueta">próximo ponto: {v.proximo_ponto}</span>
            </div>
            {!viagemAtual && ponto && (
              <button type="button" className="botao secundario" onClick={() => aoEmbarcar(v)}>
                Embarquei neste ônibus
              </button>
            )}
          </li>
        ))}
        {dados.sem_sinal.map((v) => (
          <li key={v.veiculo_id} className="cartao veiculo sem-sinal">
            <span className="veiculo-nome"><Bus aria-hidden="true" size={18} /> Ônibus {v.veiculo_id}</span>
            <span className="etiqueta sem-sinal"><WifiOff aria-hidden="true" size={16} /> sem sinal no momento — sem previsão</span>
          </li>
        ))}
      </ul>
      <p className="nota">Tempos até o ponto {ponto?.nome}, sujeitos a variação.</p>
    </>
  );
}

const ROTULO_DIA: Record<TipoDia, string> = { uteis: 'Dias úteis', sabado: 'Sábado', domingo: 'Domingo e feriados' };

function agoraHHMM(): string {
  return new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date());
}

function AbaHorarios({ dados }: { dados: Detalhe }) {
  const q = dados.quadro;
  const [dia, setDia] = useState<TipoDia | null>(null);
  const diaAtual: TipoDia = dia ?? q?.tipo_dia_hoje ?? 'uteis';
  return (
    <>
      {dados.horarios.length > 0 && (
        <table className="tabela">
          <caption>Próximas passagens previstas no ponto {dados.ponto?.nome}</caption>
          <thead>
            <tr><th scope="col">Horário</th><th scope="col">Situação</th></tr>
          </thead>
          <tbody>
            {dados.horarios.map((h, i) => (
              <tr key={h + i}><td>{h}</td><td>programado</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {q ? (
        <section className="quadro" aria-labelledby="titulo-quadro">
          <h3 id="titulo-quadro">Quadro oficial de horários</h3>
          <fieldset className="filtro-busca">
            <legend className="sr-only">Dia da semana</legend>
            {(Object.keys(ROTULO_DIA) as TipoDia[]).map((d) => (
              <label key={d} className={`chip${diaAtual === d ? ' ativo' : ''}`}>
                <input type="radio" name="dia-quadro" value={d} checked={diaAtual === d} onChange={() => setDia(d)} />
                {ROTULO_DIA[d]}
              </label>
            ))}
          </fieldset>
          <ListaSaidas titulo="Saídas do Centro" sentido={`Centro → ${q.destino}`} horarios={q.do_centro[diaAtual]} hoje={diaAtual === q.tipo_dia_hoje} />
          <ListaSaidas titulo={`Saídas do bairro (${q.destino})`} sentido={`${q.destino} → Centro`} horarios={q.para_centro[diaAtual]} hoje={diaAtual === q.tipo_dia_hoje} />
          {q.observacoes && <p className="nota">{q.observacoes}</p>}
          <p className="nota">Fonte: {q.fonte}, quadro de {q.referencia}. Horários podem mudar; confirme com a operadora.</p>
        </section>
      ) : (
        <p className="nota">Uma partida a cada {dados.intervalo_min} min, das 05h à meia-noite. Os horários ao vivo aparecem na aba Próximos.</p>
      )}
    </>
  );
}

function ListaSaidas({ titulo, sentido, horarios, hoje }: { titulo: string; sentido: string; horarios: string[]; hoje: boolean }) {
  const agora = agoraHHMM();
  const proximo = hoje ? horarios.find((h) => h >= agora) : undefined;
  return (
    <div className="saidas">
      <h4>{titulo} <span className="nota">({sentido})</span></h4>
      {horarios.length === 0 ? <p className="vazio">Não há saídas neste dia.</p> : (
        <ul className="horas" aria-label={`${titulo}: ${horarios.length} saídas`}>
          {horarios.map((h) => (
            <li key={h} className={h === proximo ? 'proxima' : ''}>
              {h}{h === proximo && <span className="sr-only"> (próxima saída)</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AbaTrajeto({ dados }: { dados: Detalhe }) {
  return (
    <>
      <ol className="trajeto">
        {dados.trajeto.map((t) => {
          const noPonto = t.onibus.filter((o) => o.no_ponto);
          const aCaminho = t.onibus.filter((o) => !o.no_ponto);
          return (
            <li key={t.id} className={`${t.id === dados.ponto?.id ? 'seu-ponto' : ''}${!t.operando ? ' desativado' : ''}`}>
              <div className="trajeto-ponto">
                <span className="trajeto-num" aria-hidden="true">{t.ordem}</span>
                <span className="trajeto-nome">
                  {t.nome}
                  {t.id === dados.ponto?.id && <span className="etiqueta seu">seu ponto</span>}
                  {!t.operando && <span className="etiqueta">desativado</span>}
                </span>
              </div>
              <AcessibilidadePonto a={t.acessibilidade} />
              {noPonto.map((o) => (
                <p key={o.veiculo_id} className="onibus-aqui"><Bus aria-hidden="true" size={16} /> Ônibus {o.veiculo_id} está neste ponto agora</p>
              ))}
              {aCaminho.map((o) => (
                <p key={o.veiculo_id} className="onibus-caminho"><Bus aria-hidden="true" size={16} /> Ônibus {o.veiculo_id} saiu daqui e segue para o próximo ponto</p>
              ))}
            </li>
          );
        })}
      </ol>
      <p className="nota">Depois do último ponto, o ônibus volta ao ponto 1 e recomeça a viagem.</p>
    </>
  );
}
