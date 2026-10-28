import L from 'leaflet';
import { Plus, Save, Trash2, X } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, ErroApi } from '../api';
import { AvisoErro, BadgeLinha, usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { useCatalogo } from '../estado/Catalogo';
import { MapaBase, useCamadaPontos } from '../mapa/Mapa';
import type { Ponto } from '../tipos';
import { CENTRO_MATAO } from '../util/geo';

interface FormPonto {
  nome: string;
  referencia: string;
  lat: string;
  lon: string;
  rampa: boolean;
  piso_tatil: boolean;
  abrigo: boolean;
  status: 'operando' | 'desativado';
}

function paraForm(p: Ponto): FormPonto {
  return { nome: p.nome, referencia: p.referencia, lat: String(p.lat), lon: String(p.lon), rampa: p.acessibilidade.rampa,
    piso_tatil: p.acessibilidade.piso_tatil, abrigo: p.acessibilidade.abrigo, status: p.status };
}

function textoAcess(p: Ponto): string {
  const a = [p.acessibilidade.rampa && 'rampa', p.acessibilidade.piso_tatil && 'piso tátil', p.acessibilidade.abrigo && 'abrigo'].filter(Boolean);
  return a.length ? a.join(' · ') : 'sem informação';
}

export function PontosGestor() {
  const titulo = usePagina('Pontos');
  const { pontos, linhas, erro, recarregar } = useCatalogo();
  const anunciar = useAnunciar();
  const [mapa, setMapa] = useState<L.Map | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [form, setForm] = useState<FormPonto | null>(null);
  const [msg, setMsg] = useState<{ texto: string; ok: boolean } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const formRef = useRef(form);
  formRef.current = form;

  useCamadaPontos(mapa, pontos, { mostrarDesativados: true, interativo: true, selecionado: sel, aoSelecionar: (p) => selecionar(p) });

  // ponto selecionado: círculo de 50 m; clique no mapa escolhe as coordenadas durante a edição
  useEffect(() => {
    if (!mapa || !form) return;
    const lat = Number(form.lat);
    const lon = Number(form.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || !form.lat || !form.lon) return;
    const camada = L.layerGroup([
      L.circle([lat, lon], { radius: 50, color: '#0F4C5C', weight: 2, fillOpacity: 0.12, interactive: false }),
      L.circleMarker([lat, lon], { radius: 6, color: '#0F4C5C', fillColor: '#0F4C5C', fillOpacity: 1, interactive: false }),
    ]).addTo(mapa);
    return () => {
      camada.remove();
    };
  }, [mapa, form?.lat, form?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!mapa) return;
    const clicar = (e: L.LeafletMouseEvent) => {
      if (!formRef.current) return;
      setForm({ ...formRef.current, lat: e.latlng.lat.toFixed(6), lon: e.latlng.lng.toFixed(6) });
      anunciar('Coordenadas do ponto atualizadas pelo clique no mapa.');
    };
    mapa.on('click', clicar);
    return () => {
      mapa.off('click', clicar);
    };
  }, [mapa, anunciar]);

  function selecionar(p: Ponto) {
    setSel(p.id);
    setForm(paraForm(p));
    setMsg(null);
    mapa?.setView([p.lat, p.lon], 17);
  }

  function novo() {
    setSel('__novo__');
    const c = mapa?.getCenter();
    setForm({ nome: '', referencia: '', lat: c ? c.lat.toFixed(6) : String(CENTRO_MATAO[0]), lon: c ? c.lng.toFixed(6) : String(CENTRO_MATAO[1]),
      rampa: false, piso_tatil: false, abrigo: false, status: 'operando' });
    setMsg(null);
    window.setTimeout(() => document.getElementById('ponto-nome')?.focus(), 50);
  }

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSalvando(true);
    const corpo = { nome: form.nome, referencia: form.referencia, lat: Number(form.lat.replace(',', '.')), lon: Number(form.lon.replace(',', '.')),
      status: form.status, acessibilidade: { rampa: form.rampa, piso_tatil: form.piso_tatil, abrigo: form.abrigo } };
    try {
      const r = sel === '__novo__' ? await api.post<Ponto>('/api/pontos', corpo) : await api.put<Ponto>(`/api/pontos/${sel}`, corpo);
      const t = `Ponto ${r.nome} salvo. A mudança já aparece no app do passageiro.`;
      setMsg({ texto: t, ok: true });
      anunciar(t);
      setSel(r.id);
      await recarregar();
    } catch (e2) {
      const t = e2 instanceof ErroApi ? e2.message : 'Não foi possível salvar o ponto.';
      setMsg({ texto: t, ok: false });
      anunciar(t, true);
    } finally {
      setSalvando(false);
    }
  }

  async function excluir() {
    if (!sel || sel === '__novo__' || !form || !window.confirm(`Excluir o ponto ${form.nome}?`)) return;
    try {
      await api.del(`/api/pontos/${sel}`);
      anunciar(`Ponto ${form.nome} excluído.`);
      setSel(null);
      setForm(null);
      await recarregar();
    } catch (e2) {
      setMsg({ texto: e2 instanceof ErroApi ? e2.message : 'Não foi possível excluir.', ok: false });
    }
  }

  const linhaPorNumero = new Map(linhas.map((l) => [l.numero, l]));

  return (
    <div className="pagina-gestor">
      <div className="cabecalho-pagina entre">
        <h1 ref={titulo} tabIndex={-1}>Pontos de parada</h1>
        <button type="button" className="botao primario" onClick={novo}><Plus aria-hidden="true" size={20} /> Novo ponto</button>
      </div>
      <AvisoErro texto={erro} />
      <div className="tabela-rolagem" tabIndex={0} role="region" aria-label="Tabela de pontos">
        <table className="tabela">
          <caption className="sr-only">Pontos com referência, linhas, acessibilidade e situação</caption>
          <thead>
            <tr><th scope="col">Ponto</th><th scope="col">Referência</th><th scope="col">Linhas</th><th scope="col">Acessibilidade</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Ações</span></th></tr>
          </thead>
          <tbody>
            {pontos.map((p) => (
              <tr key={p.id} className={sel === p.id ? 'selecionada' : ''} aria-current={sel === p.id ? 'true' : undefined}>
                <th scope="row">{p.nome}</th>
                <td>{p.referencia || '—'}</td>
                <td>
                  <span className="badges">
                    {p.linhas_atendidas.length ? p.linhas_atendidas.map((n) => {
                      const l = linhaPorNumero.get(n);
                      return l ? <BadgeLinha key={n} numero={n} cor={l.cor} corNome={l.cor_nome} nome={l.nome} /> : null;
                    }) : 'nenhuma'}
                  </span>
                </td>
                <td>{textoAcess(p)}</td>
                <td>{p.status === 'operando' ? 'operando' : 'desativado'}</td>
                <td><button type="button" className="botao texto" onClick={() => selecionar(p)}>Editar<span className="sr-only"> ponto {p.nome}</span></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="edicao-grade">
        <section className="cartao" aria-labelledby="t-mapa-ponto">
          <h2 id="t-mapa-ponto">Localização do ponto</h2>
          <MapaBase rotulo="Mapa com os pontos de parada; o ponto selecionado aparece com um círculo de 50 metros" className="mapa-gestor" aoPronto={setMapa} zoom={14} />
          <p className="nota">{form ? 'Clique no mapa para escolher as coordenadas do ponto. O círculo mostra um raio de 50 m.' : 'Escolha um ponto na tabela ou no mapa.'}</p>
        </section>

        {form && (
          <section className="cartao" aria-labelledby="t-form-ponto">
            <div className="cartao-topo">
              <h2 id="t-form-ponto">{sel === '__novo__' ? 'Novo ponto' : 'Editar ponto'}</h2>
              <button type="button" className="botao-icone" onClick={() => { setSel(null); setForm(null); }} aria-label="Fechar edição"><X aria-hidden="true" size={20} /></button>
            </div>
            <form onSubmit={salvar} className="form-gestor">
              <div className="campo">
                <label htmlFor="ponto-nome">Nome do ponto</label>
                <input id="ponto-nome" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} required />
              </div>
              <div className="campo">
                <label htmlFor="ponto-ref">Referência (rua ou local)</label>
                <input id="ponto-ref" value={form.referencia} onChange={(e) => setForm({ ...form, referencia: e.target.value })} />
              </div>
              <fieldset>
                <legend>Coordenadas (ou clique no mapa)</legend>
                <div className="campos-linha">
                  <div className="campo">
                    <label htmlFor="ponto-lat">Latitude</label>
                    <input id="ponto-lat" value={form.lat} onChange={(e) => setForm({ ...form, lat: e.target.value })} inputMode="decimal" required />
                  </div>
                  <div className="campo">
                    <label htmlFor="ponto-lon">Longitude</label>
                    <input id="ponto-lon" value={form.lon} onChange={(e) => setForm({ ...form, lon: e.target.value })} inputMode="decimal" required />
                  </div>
                </div>
              </fieldset>
              <fieldset>
                <legend>Acessibilidade</legend>
                {([['rampa', 'Rampa de acesso'], ['piso_tatil', 'Piso tátil'], ['abrigo', 'Abrigo (cobertura)']] as const).map(([k, r]) => (
                  <div key={k} className="campo-check">
                    <input id={`ponto-${k}`} type="checkbox" checked={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} />
                    <label htmlFor={`ponto-${k}`}>{r}</label>
                  </div>
                ))}
              </fieldset>
              <div className="campo">
                <label htmlFor="ponto-status">Status</label>
                <select id="ponto-status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as FormPonto['status'] })}>
                  <option value="operando">operando</option>
                  <option value="desativado">desativado (ônibus não param)</option>
                </select>
              </div>
              {msg && <p className={msg.ok ? 'aviso-ok' : 'aviso-erro'}>{msg.texto}</p>}
              <div className="acoes">
                <button type="submit" className="botao primario" disabled={salvando}><Save aria-hidden="true" size={18} /> Salvar ponto</button>
                {sel !== '__novo__' && <button type="button" className="botao perigo" onClick={excluir}><Trash2 aria-hidden="true" size={18} /> Excluir ponto</button>}
              </div>
            </form>
          </section>
        )}
      </div>
    </div>
  );
}
