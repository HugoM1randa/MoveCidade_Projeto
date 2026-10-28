import type L from 'leaflet';
import { Megaphone, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';
import { AvisoErro, BadgeLinha, Esqueleto, usePagina } from '../componentes/comuns';
import { useCatalogo } from '../estado/Catalogo';
import { usePolling } from '../estado/usePolling';
import { MapaBase, useCamadaOnibus, useCamadaRotas } from '../mapa/Mapa';
import type { Kpi, VeiculoGestor, VeiculoMapa } from '../tipos';
import { Ajuda, Status } from './comuns';
import type { ContextoGestor } from './Layout';

const KPIS: { chave: 'pontualidade' | 'tempo_espera' | 'ocupacao_horario' | 'duracao_viagem' | 'disponibilidade'; titulo: string }[] = [
  { chave: 'pontualidade', titulo: 'Pontualidade' },
  { chave: 'tempo_espera', titulo: 'Tempo de espera' },
  { chave: 'ocupacao_horario', titulo: 'Ocupação por horário' },
  { chave: 'duracao_viagem', titulo: 'Duração da viagem' },
  { chave: 'disponibilidade', titulo: 'Disponibilidade' },
];

function valorKpi(k: Kpi): string {
  if (k.valor === null || k.valor === undefined) return '—';
  return `${String(k.valor).replace('.', ',')}${k.unidade === '%' ? '%' : ` ${k.unidade}`}`;
}

function detalheKpi(chave: string, k: Kpi): string {
  if (k.valor === null) return 'coletando dados…';
  if (chave === 'pontualidade') return `${k.amostras} chegadas medidas`;
  if (chave === 'ocupacao_horario') return `média às ${k.hora}h`;
  if (chave === 'duracao_viagem') return k.fonte === 'medida' ? `média de ${k.amostras} voltas` : 'estimada pelo trajeto';
  if (chave === 'disponibilidade') return `${k.ativos} de ${k.cadastrados} ônibus`;
  return 'metade do intervalo entre ônibus';
}

export function PainelGestor() {
  const titulo = usePagina('Painel operacional');
  const { painel, erroPainel } = useOutletContext<ContextoGestor>();
  const { linhas } = useCatalogo();
  const [mapa, setMapa] = useState<L.Map | null>(null);
  const [aberto, setAberto] = useState<string | null>(null);

  const veiculosMapa: VeiculoMapa[] = (painel?.frota ?? []).filter((v) => v.lat !== null).map((v) => ({
    id: v.id, linha_id: v.linha_id, numero: v.numero, cor: v.cor, cor_nome: linhas.find((l) => l.id === v.linha_id)?.cor_nome ?? '',
    lat: v.lat!, lon: v.lon!, ao_vivo: v.ao_vivo, acessivel: v.acessivel, lotacao: v.lotacao, no_ponto: false,
    proximo_ponto: v.proximo_ponto, proximo_ponto_id: null, ponto_atual_id: null, eta_proximo_s: null,
  }));
  useCamadaRotas(mapa, linhas, { fraco: true });
  useCamadaOnibus(mapa, veiculosMapa, { interativo: true, selecionado: aberto, aoSelecionar: (v) => setAberto(v.id) });

  return (
    <div className="pagina-gestor">
      <h1 ref={titulo} tabIndex={-1}>Painel operacional</h1>
      <AvisoErro texto={erroPainel} />
      {!painel ? <Esqueleto linhas={4} /> : (
        <>
          <section aria-labelledby="t-ind">
            <h2 id="t-ind" className="sr-only">Indicadores</h2>
            <ul className="kpis">
              {KPIS.map(({ chave, titulo: t }) => {
                const k = painel.kpis[chave];
                return (
                  <li key={chave} className="cartao kpi">
                    <div className="kpi-topo">
                      <h3>{t}</h3>
                      <Ajuda titulo={t} texto={k.ajuda} />
                    </div>
                    <p className="kpi-valor">{valorKpi(k)}</p>
                    <p className="nota">{detalheKpi(chave, k)}</p>
                  </li>
                );
              })}
            </ul>
            {painel.fator_tempo !== 1 && (
              <p className="nota">Simulação {String(painel.fator_tempo).replace('.', ',')}× mais rápida que o relógio: os tempos já estão no relógio da tela.</p>
            )}
          </section>

          <div className="painel-grade">
            <section className="cartao" aria-labelledby="t-frota">
              <h2 id="t-frota">Frota em tempo real</h2>
              <MapaBase rotulo="Mapa da frota em tempo real" className="mapa-gestor" aoPronto={setMapa} zoom={14} />
              <div className="tabela-rolagem" tabIndex={0} role="region" aria-label="Situação de cada ônibus">
              <table className="tabela compacta">
                <caption className="sr-only">Situação de cada ônibus</caption>
                <thead>
                  <tr><th scope="col">Ônibus</th><th scope="col">Linha</th><th scope="col">Situação</th><th scope="col">Ocupação</th><th scope="col"><span className="sr-only">Ações</span></th></tr>
                </thead>
                <tbody>
                  {painel.frota.map((v) => (
                    <tr key={v.id}>
                      <th scope="row">{v.id}</th>
                      <td><BadgeLinha numero={v.numero} cor={v.cor} corNome={linhas.find((l) => l.id === v.linha_id)?.cor_nome ?? ''} nome={linhas.find((l) => l.id === v.linha_id)?.nome ?? ''} /></td>
                      <td><Status s={v.status} /></td>
                      <td>{v.ocupacao_pct !== null && v.ao_vivo ? `${v.ocupacao_pct}%` : '—'}</td>
                      <td><button type="button" className="botao texto" onClick={() => setAberto(v.id)}>Detalhes<span className="sr-only"> do ônibus {v.id}</span></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </section>

            <aside className="cartao hermes" aria-labelledby="t-hermes">
              <h2 id="t-hermes"><Megaphone aria-hidden="true" size={20} /> Hermes · avisos</h2>
              {painel.avisos.length === 0 ? <p className="vazio">Nenhum aviso pendente agora.</p> : (
                <ul className="avisos">
                  {painel.avisos.map((a) => (
                    <li key={a.id}>
                      <BadgeLinha numero={a.linha_id} cor={linhas.find((l) => l.id === a.linha_id)?.cor ?? '#374151'}
                        corNome={linhas.find((l) => l.id === a.linha_id)?.cor_nome ?? ''} nome={linhas.find((l) => l.id === a.linha_id)?.nome ?? ''} />
                      <div>
                        <p className="aviso-titulo">{a.titulo}</p>
                        <p>Sugestão: {a.sugestao}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <Link to="/gestor/alertas" className="botao secundario">Ver todos os alertas ({painel.alertas_pendentes})</Link>
              <p className="nota">Toda sugestão exige o aceite do gestor.</p>
            </aside>
          </div>
        </>
      )}
      {aberto && <DetalheVeiculo id={aberto} aoFechar={() => setAberto(null)} />}
    </div>
  );
}

interface DetalheTec extends VeiculoGestor {
  ultimo_sinal_s: number | null;
  tecnico: null | Record<string, string | number>;
}

function DetalheVeiculo({ id, aoFechar }: { id: string; aoFechar: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const { dados } = usePolling<DetalheTec>(`/api/gestor/veiculos/${id}`, 2000);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);
  const t = dados?.tecnico;
  return (
    <dialog ref={ref} className="dialogo" aria-labelledby="t-veic" onClose={aoFechar}>
      <div className="dialogo-topo">
        <h2 id="t-veic">Ônibus {id}</h2>
        <button type="button" className="botao-icone" onClick={() => ref.current?.close()} aria-label="Fechar">
          <X aria-hidden="true" size={22} />
        </button>
      </div>
      {!dados ? <p>Carregando…</p> : (
        <>
          <p><Status s={dados.status} /> · linha {dados.numero} · capacidade {dados.capacidade}{dados.acessivel ? ' · acessível' : ''}</p>
          {dados.ultimo_sinal_s !== null && <p className="nota">Último sinal há {dados.ultimo_sinal_s} s.</p>}
          {t && (
            <dl className="dados-tecnicos">
              <dt>Próximo ponto</dt><dd>{dados.proximo_ponto}</dd>
              <dt>Ocupação</dt><dd>{t.passageiros} passageiros ({dados.ocupacao_pct}%)</dd>
              <dt>Desvio do horário</dt><dd>{dados.atraso_min === null ? '—' : dados.atraso_min > 0 ? `${String(dados.atraso_min).replace('.', ',')} min atrasado` : 'no horário ou adiantado'}</dd>
              <dt>Velocidade</dt><dd>{t.velocidade_kmh} km/h</dd>
              <dt>Média histórica do trecho</dt><dd>{t.velocidade_media_trecho_kmh} km/h</dd>
              <dt>ETA ao próximo ponto</dt><dd>{Math.round(Number(t.eta_proximo_ponto_s))} s</dd>
              <dt>Portas</dt><dd>{t.portas}</dd>
              <dt>Temperatura interna</dt><dd>{String(t.temperatura_c).replace('.', ',')} °C</dd>
              <dt>Odômetro</dt><dd>{String(t.odometro_km).replace('.', ',')} km</dd>
            </dl>
          )}
        </>
      )}
    </dialog>
  );
}
