import type L from 'leaflet';
import { ArrowDown, ArrowUp, Plus, Save, Trash2, X } from 'lucide-react';
import { useEffect, useId, useMemo, useState, type FormEvent } from 'react';
import { api, ErroApi } from '../api';
import { AvisoErro, BadgeLinha, Esqueleto, usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { useCatalogo } from '../estado/Catalogo';
import { usePolling } from '../estado/usePolling';
import { MapaBase, useCamadaPontos, useCamadaRotas } from '../mapa/Mapa';
import type { Linha, LinhaGestor, Padrao } from '../tipos';
import { contraste, nomePadrao } from '../util/formato';
import { Status } from './comuns';

interface Formulario {
  numero: string;
  nome: string;
  cor: string;
  padrao: Padrao;
  intervalo_min: number;
  pontos: string[];
}

export function LinhasGestor() {
  const titulo = usePagina('Linhas');
  const { dados, erro, carregando, atualizar } = usePolling<LinhaGestor[]>('/api/gestor/linhas', 4000);
  const { linhas: catLinhas, pontos, recarregar } = useCatalogo();
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [mapa, setMapa] = useState<L.Map | null>(null);
  const [form, setForm] = useState<Formulario | null>(null);

  const linhaSel = dados?.find((l) => l.id === selecionada) ?? null;
  const linhaCat = catLinhas.find((l) => l.id === selecionada);

  async function novaLinha() {
    const prox = await api.get<{ cor: string; padrao: Padrao }>('/api/gestor/cores/proxima').catch(() => ({ cor: '#334155', padrao: 'continuo' as Padrao }));
    setSelecionada('__nova__');
    setForm({ numero: '', nome: '', cor: prox.cor || '#334155', padrao: prox.padrao, intervalo_min: 15, pontos: [] });
    window.setTimeout(() => document.getElementById('campo-numero')?.focus(), 50);
  }

  function selecionar(l: LinhaGestor) {
    setSelecionada(l.id);
    setForm({ numero: l.numero, nome: l.nome, cor: l.cor, padrao: l.padrao, intervalo_min: l.intervalo_min, pontos: [...l.pontos] });
  }

  // mapa: traçado da linha selecionada e os pontos numerados na ordem do formulário
  const visiveis = useMemo(() => new Set(selecionada && selecionada !== '__nova__' ? [selecionada] : []), [selecionada]);
  useCamadaRotas(mapa, catLinhas, { visiveis });
  useCamadaPontos(mapa, pontos, {
    destacados: form?.pontos ?? [], interativo: !!form, mostrarDesativados: true,
    aoSelecionar: (p) => setForm((f) => (f && !f.pontos.includes(p.id) ? { ...f, pontos: [...f.pontos, p.id] } : f)),
  });
  useEffect(() => {
    if (mapa && linhaCat?.rota?.length) mapa.fitBounds(linhaCat.rota, { padding: [20, 20] });
  }, [mapa, linhaCat?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="pagina-gestor">
      <div className="cabecalho-pagina entre">
        <h1 ref={titulo} tabIndex={-1}>Linhas cadastradas</h1>
        <button type="button" className="botao primario" onClick={novaLinha}><Plus aria-hidden="true" size={20} /> Nova linha</button>
      </div>
      <AvisoErro texto={erro} />
      {carregando && !dados ? <Esqueleto /> : dados && (
        <div className="tabela-rolagem" tabIndex={0} role="region" aria-label="Tabela de linhas">
          <table className="tabela">
            <caption className="sr-only">Linhas, trajeto, número de pontos e de veículos e situação</caption>
            <thead>
              <tr><th scope="col">Linha</th><th scope="col">Trajeto</th><th scope="col">Pontos</th><th scope="col">Veículos</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Ações</span></th></tr>
            </thead>
            <tbody>
              {dados.map((l) => (
                <tr key={l.id} className={selecionada === l.id ? 'selecionada' : ''} aria-current={selecionada === l.id ? 'true' : undefined}>
                  <th scope="row"><BadgeLinha numero={l.numero} cor={l.cor} corNome={l.cor_nome} nome={l.nome} grande /></th>
                  <td>{l.nome}</td>
                  <td>{l.qtd_pontos}</td>
                  <td>{l.qtd_veiculos}</td>
                  <td><Status s={l.status} /></td>
                  <td><button type="button" className="botao texto" onClick={() => selecionar(l)}>Editar<span className="sr-only"> linha {l.numero}</span></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="edicao-grade">
        <section className="cartao" aria-labelledby="t-mapa-linha">
          <h2 id="t-mapa-linha">{linhaSel ? `Trajeto da linha ${linhaSel.numero}` : form ? 'Trajeto da nova linha' : 'Mapa'}</h2>
          <MapaBase rotulo="Mapa do trajeto da linha selecionada com os pontos numerados" className="mapa-gestor" aoPronto={setMapa} zoom={14} />
          <p className="nota">{form ? 'Pontos numerados na ordem do trajeto. Clique num ponto do mapa para adicioná-lo ao fim da lista.' : 'Escolha uma linha na tabela para ver e editar o trajeto.'}</p>
        </section>
        {form && selecionada && (
          <FormLinha key={selecionada} nova={selecionada === '__nova__'} linhaId={selecionada === '__nova__' ? null : selecionada}
            form={form} setForm={setForm} linhaGestor={linhaSel}
            aoSalvar={async (id) => { await recarregar(); atualizar(); setSelecionada(id); }}
            aoExcluir={async () => { setSelecionada(null); setForm(null); await recarregar(); atualizar(); }}
            aoCancelar={() => { setSelecionada(null); setForm(null); }} />
        )}
      </div>
    </div>
  );
}

function FormLinha({ nova, linhaId, form, setForm, linhaGestor, aoSalvar, aoExcluir, aoCancelar }: {
  nova: boolean; linhaId: string | null; form: Formulario; setForm: (f: Formulario) => void; linhaGestor: LinhaGestor | null;
  aoSalvar: (id: string) => void; aoExcluir: () => void; aoCancelar: () => void;
}) {
  const { pontoPorId, pontos } = useCatalogo();
  const anunciar = useAnunciar();
  const [validacaoCor, setValidacaoCor] = useState<{ aprovada: boolean; mensagem: string | null } | null>(null);
  const [mensagem, setMensagem] = useState<{ texto: string; ok: boolean } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [novoPonto, setNovoPonto] = useState('');
  const ids = { cor: useId(), corTexto: useId(), add: useId(), corMsg: useId() };

  useEffect(() => {
    const t = window.setTimeout(async () => {
      try {
        setValidacaoCor(await api.post('/api/gestor/cores/validar', { cor: form.cor, linha_id: linhaId }));
      } catch {
        setValidacaoCor(null);
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [form.cor, linhaId]);

  const mover = (i: number, d: -1 | 1) => {
    const p = [...form.pontos];
    const j = i + d;
    if (j < 0 || j >= p.length) return;
    [p[i], p[j]] = [p[j], p[i]];
    setForm({ ...form, pontos: p });
    anunciar(`${pontoPorId.get(p[j])?.nome} agora é o ponto ${j + 1}.`);
    window.setTimeout(() => document.getElementById(`mover-${d < 0 ? 'cima' : 'baixo'}-${p[j]}`)?.focus(), 0);
  };
  const remover = (id: string) => {
    setForm({ ...form, pontos: form.pontos.filter((x) => x !== id) });
    anunciar(`${pontoPorId.get(id)?.nome} removido do trajeto.`);
  };
  const adicionar = () => {
    if (!novoPonto || form.pontos.includes(novoPonto)) return;
    setForm({ ...form, pontos: [...form.pontos, novoPonto] });
    anunciar(`${pontoPorId.get(novoPonto)?.nome} adicionado como ponto ${form.pontos.length + 1}.`);
    setNovoPonto('');
  };

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setMensagem(null);
    try {
      const r = nova ? await api.post<Linha>('/api/linhas', form) : await api.put<Linha>(`/api/linhas/${linhaId}`, form);
      const t = nova ? `Linha ${r.numero} criada. Ela já aparece no app do passageiro.` : `Trajeto da linha ${r.numero} salvo. O app do passageiro já usa a nova versão.`;
      setMensagem({ texto: t, ok: true });
      anunciar(t);
      aoSalvar(r.id);
    } catch (e2) {
      const t = e2 instanceof ErroApi ? e2.message : 'Não foi possível salvar.';
      setMensagem({ texto: t, ok: false });
      anunciar(t, true);
    } finally {
      setSalvando(false);
    }
  }

  async function excluir() {
    if (!linhaId || !window.confirm(`Excluir a linha ${form.numero} e todos os ônibus dela?`)) return;
    try {
      await api.del(`/api/linhas/${linhaId}`);
      anunciar(`Linha ${form.numero} excluída.`);
      aoExcluir();
    } catch (e2) {
      setMensagem({ texto: e2 instanceof ErroApi ? e2.message : 'Não foi possível excluir.', ok: false });
    }
  }

  const disponiveis = pontos.filter((p) => !form.pontos.includes(p.id));
  const corValida = /^#[0-9a-fA-F]{6}$/.test(form.cor);

  return (
    <section className="cartao" aria-labelledby="t-form-linha">
      <div className="cartao-topo">
        <h2 id="t-form-linha">{nova ? 'Nova linha' : `Editar linha ${form.numero}`}</h2>
        <button type="button" className="botao-icone" onClick={aoCancelar} aria-label="Fechar edição"><X aria-hidden="true" size={20} /></button>
      </div>
      <form onSubmit={salvar} className="form-gestor">
        <div className="campos-linha">
          <div className="campo">
            <label htmlFor="campo-numero">Número</label>
            <input id="campo-numero" value={form.numero} onChange={(e) => setForm({ ...form, numero: e.target.value })} disabled={!nova} required maxLength={6} inputMode="numeric" />
          </div>
          <div className="campo grow">
            <label htmlFor="campo-nome">Nome (origem – destino)</label>
            <input id="campo-nome" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} required placeholder="Ex.: Centro – Jardim Paraíso" />
          </div>
        </div>
        <div className="campos-linha">
          <div className="campo">
            <label htmlFor={ids.cor}>Cor</label>
            <div className="cor-escolha">
              <input id={ids.cor} type="color" value={corValida ? form.cor : '#000000'} onChange={(e) => setForm({ ...form, cor: e.target.value.toUpperCase() })} aria-describedby={ids.corMsg} />
              <label htmlFor={ids.corTexto} className="sr-only">Código da cor</label>
              <input id={ids.corTexto} value={form.cor} onChange={(e) => setForm({ ...form, cor: e.target.value.toUpperCase() })} maxLength={7} className="curto" aria-describedby={ids.corMsg} />
              {corValida && <span className="badge-linha grande" style={{ background: form.cor }} aria-hidden="true">{form.numero || '000'}</span>}
            </div>
            <p id={ids.corMsg} className={validacaoCor?.aprovada ? 'aviso-ok' : 'aviso-erro'} aria-live="polite">
              {validacaoCor ? (validacaoCor.aprovada ? `Cor aprovada: contraste ${contraste(form.cor, '#FFFFFF').toFixed(1).replace('.', ',')}:1 com texto branco.` : validacaoCor.mensagem) : ' '}
            </p>
          </div>
          <div className="campo">
            <label htmlFor="campo-padrao">Traçado no mapa</label>
            <select id="campo-padrao" value={form.padrao} onChange={(e) => setForm({ ...form, padrao: e.target.value as Padrao })}>
              {(['continuo', 'tracejado', 'pontilhado', 'traco_ponto'] as Padrao[]).map((p) => <option key={p} value={p}>{nomePadrao(p)}</option>)}
            </select>
          </div>
          <div className="campo">
            <label htmlFor="campo-intervalo">Intervalo programado (min)</label>
            <input id="campo-intervalo" type="number" min={3} max={120} value={form.intervalo_min} onChange={(e) => setForm({ ...form, intervalo_min: Number(e.target.value) })} className="curto" />
          </div>
        </div>

        <fieldset>
          <legend>Ordem dos pontos ({form.pontos.length})</legend>
          {form.pontos.length === 0 ? <p className="vazio">Adicione pelo menos 2 pontos.</p> : (
            <ol className="ordem-pontos">
              {form.pontos.map((id, i) => {
                const nome = pontoPorId.get(id)?.nome ?? id;
                return (
                  <li key={id}>
                    <span className="trajeto-num" aria-hidden="true">{i + 1}</span>
                    <span className="grow">{nome}</span>
                    <button type="button" id={`mover-cima-${id}`} className="botao-icone pequeno" onClick={() => mover(i, -1)} disabled={i === 0} aria-label={`Mover ${nome} para cima`}><ArrowUp aria-hidden="true" size={18} /></button>
                    <button type="button" id={`mover-baixo-${id}`} className="botao-icone pequeno" onClick={() => mover(i, 1)} disabled={i === form.pontos.length - 1} aria-label={`Mover ${nome} para baixo`}><ArrowDown aria-hidden="true" size={18} /></button>
                    <button type="button" className="botao-icone pequeno perigo" onClick={() => remover(id)} aria-label={`Remover ${nome} do trajeto`}><Trash2 aria-hidden="true" size={18} /></button>
                  </li>
                );
              })}
            </ol>
          )}
          <div className="campos-linha">
            <div className="campo grow">
              <label htmlFor={ids.add}>Adicionar ponto</label>
              <select id={ids.add} value={novoPonto} onChange={(e) => setNovoPonto(e.target.value)}>
                <option value="">Escolha um ponto</option>
                {disponiveis.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.status !== 'operando' ? ' (desativado)' : ''}</option>)}
              </select>
            </div>
            <button type="button" className="botao secundario alinhar-base" onClick={adicionar} disabled={!novoPonto}><Plus aria-hidden="true" size={18} /> Adicionar</button>
          </div>
        </fieldset>

        {mensagem && <p className={mensagem.ok ? 'aviso-ok' : 'aviso-erro'}>{mensagem.texto}</p>}
        <div className="acoes">
          <button type="submit" className="botao primario" disabled={salvando}><Save aria-hidden="true" size={18} /> {nova ? 'Criar linha' : 'Salvar trajeto'}</button>
          {!nova && <button type="button" className="botao perigo" onClick={excluir}><Trash2 aria-hidden="true" size={18} /> Excluir linha</button>}
        </div>
      </form>
      {!nova && linhaGestor && <VeiculosDaLinha linha={linhaGestor} />}
    </section>
  );
}

function VeiculosDaLinha({ linha }: { linha: LinhaGestor }) {
  const anunciar = useAnunciar();
  const [capacidade, setCapacidade] = useState(70);
  const [acessivel, setAcessivel] = useState(true);
  const [msg, setMsg] = useState<{ texto: string; ok: boolean } | null>(null);
  const [lista, setLista] = useState(linha.veiculos);
  useEffect(() => setLista(linha.veiculos), [linha.veiculos]);

  async function adicionar(e: FormEvent) {
    e.preventDefault();
    try {
      const v = await api.post<{ id: string }>('/api/veiculos', { linha_id: linha.id, capacidade, acessivel });
      const t = `Ônibus ${v.id} adicionado à linha ${linha.numero} e já em operação.`;
      setMsg({ texto: t, ok: true });
      anunciar(t);
    } catch (e2) {
      setMsg({ texto: e2 instanceof ErroApi ? e2.message : 'Não foi possível adicionar.', ok: false });
    }
  }
  async function remover(id: string) {
    if (!window.confirm(`Remover o ônibus ${id} da linha ${linha.numero}?`)) return;
    try {
      await api.del(`/api/veiculos/${id}`);
      setLista((l) => l.filter((v) => v.id !== id));
      const t = `Ônibus ${id} removido.`;
      setMsg({ texto: t, ok: true });
      anunciar(t);
    } catch (e2) {
      setMsg({ texto: e2 instanceof ErroApi ? e2.message : 'Não foi possível remover.', ok: false });
    }
  }

  return (
    <div className="veiculos-linha">
      <h3>Veículos da linha {linha.numero}</h3>
      {lista.length === 0 ? <p className="vazio">Nenhum ônibus nesta linha.</p> : (
        <ul className="lista-simples">
          {lista.map((v) => (
            <li key={v.id}>
              <span className="grow"><strong>{v.id}</strong> · {v.capacidade} lugares{v.acessivel ? ' · acessível' : ''}</span>
              <Status s={v.status} />
              <button type="button" className="botao texto perigo" onClick={() => remover(v.id)}>Remover<span className="sr-only"> ônibus {v.id}</span></button>
            </li>
          ))}
        </ul>
      )}
      <form className="campos-linha" onSubmit={adicionar}>
        <div className="campo">
          <label htmlFor="cap-novo">Capacidade</label>
          <input id="cap-novo" type="number" min={10} max={200} value={capacidade} onChange={(e) => setCapacidade(Number(e.target.value))} className="curto" />
        </div>
        <div className="campo-check alinhar-base">
          <input id="acess-novo" type="checkbox" checked={acessivel} onChange={(e) => setAcessivel(e.target.checked)} />
          <label htmlFor="acess-novo">Acessível</label>
        </div>
        <button type="submit" className="botao secundario alinhar-base"><Plus aria-hidden="true" size={18} /> Adicionar veículo</button>
      </form>
      {msg && <p className={msg.ok ? 'aviso-ok' : 'aviso-erro'}>{msg.texto}</p>}
    </div>
  );
}
