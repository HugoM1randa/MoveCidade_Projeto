import { Accessibility } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { api, ErroApi, query } from '../api';
import { usePagina } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { usePreferencias, type TamanhoTexto } from '../estado/Preferencias';
import { usePolling } from '../estado/usePolling';
import type { RespostaProximos, VeiculoMapa } from '../tipos';
import { tempoDeChegada } from '../util/formato';

function Interruptor({ rotulo, descricao, ligado, aoMudar }: { rotulo: string; descricao?: string; ligado: boolean; aoMudar: (v: boolean) => void }) {
  const id = useId();
  return (
    <div className="interruptor">
      <input id={id} type="checkbox" role="switch" checked={ligado} onChange={(e) => aoMudar(e.target.checked)}
        aria-describedby={descricao ? `${id}-d` : undefined} />
      <label htmlFor={id}>{rotulo}</label>
      {descricao && <p id={`${id}-d`} className="nota">{descricao}</p>}
    </div>
  );
}

export function Acessibilidade() {
  const titulo = usePagina('Acessibilidade');
  const { filtros, setFiltro, altoContraste, setAltoContraste, tamanhoTexto, setTamanhoTexto, pino, veiculoSelecionado, setVeiculoSelecionado } = usePreferencias();
  const anunciar = useAnunciar();
  const [msg, setMsg] = useState<{ texto: string; ok: boolean } | null>(null);
  const [enviando, setEnviando] = useState(false);
  const idSelect = useId();

  const { dados: frota } = usePolling<{ veiculos: VeiculoMapa[] }>('/api/veiculos/mapa', 4000);
  const { dados: perto } = usePolling<RespostaProximos>(`/api/pontos/proximos${query({ lat: pino.lat, lon: pino.lon, limite: 1 })}`, 4000);
  const pontoPerto = perto?.pontos[0];

  // ônibus que chegam ao ponto mais próximo aparecem primeiro na lista
  const opcoes = useMemo(() => {
    const vivos = (frota?.veiculos ?? []).filter((v) => v.ao_vivo);
    const chegando = new Map<string, number>();
    for (const l of pontoPerto?.linhas ?? []) if (l.veiculo_id && l.eta_s !== null) chegando.set(l.veiculo_id, l.eta_s);
    return vivos.sort((a, b) => (chegando.get(a.id) ?? 1e9) - (chegando.get(b.id) ?? 1e9) || a.id.localeCompare(b.id))
      .map((v) => ({ v, eta: chegando.get(v.id) }));
  }, [frota, pontoPerto]);

  async function acionar() {
    if (!veiculoSelecionado) {
      const t = 'Escolha primeiro o ônibus em que você vai embarcar.';
      setMsg({ texto: t, ok: false });
      anunciar(t);
      return;
    }
    setEnviando(true);
    try {
      const r = await api.post<{ mensagem: string }>(`/api/veiculos/${veiculoSelecionado}/acessibilidade`);
      setMsg({ texto: r.mensagem, ok: true });
      anunciar(r.mensagem);
    } catch (e) {
      const t = e instanceof ErroApi ? e.message : 'Não foi possível enviar o pedido. Tente de novo.';
      setMsg({ texto: t, ok: false });
      anunciar(t);
    } finally {
      setEnviando(false);
    }
  }

  const tamanhos: { valor: TamanhoTexto; rotulo: string; desc: string }[] = [
    { valor: 'normal', rotulo: 'A', desc: 'texto normal' },
    { valor: 'grande', rotulo: 'A+', desc: 'texto grande' },
    { valor: 'maior', rotulo: 'A++', desc: 'texto maior' },
  ];

  return (
    <div className="pagina estreita">
      <h1 ref={titulo} tabIndex={-1}>Acessibilidade</h1>

      <section className="cartao secao" aria-labelledby="t-filtros">
        <h2 id="t-filtros">Filtrar resultados</h2>
        <p className="nota">Vale para a tela Início, a busca e o mapa.</p>
        <Interruptor rotulo="Somente veículos acessíveis" descricao="Mostra só ônibus com elevador ou rampa: na previsão, nas listas e no mapa."
          ligado={filtros.somenteAcessiveis} aoMudar={(v) => setFiltro('somenteAcessiveis', v)} />
      </section>

      <section className="cartao secao" aria-labelledby="t-leitura">
        <h2 id="t-leitura">Leitura</h2>
        <Interruptor rotulo="Alto contraste" ligado={altoContraste} aoMudar={setAltoContraste} />
        <fieldset className="tamanho-texto">
          <legend>Tamanho do texto</legend>
          <div className="segmentado">
            {tamanhos.map((t) => (
              <label key={t.valor} className={tamanhoTexto === t.valor ? 'ativo' : ''}>
                <input type="radio" name="tamanho" value={t.valor} checked={tamanhoTexto === t.valor} onChange={() => setTamanhoTexto(t.valor)} />
                <span aria-hidden="true">{t.rotulo}</span>
                <span className="sr-only">{t.desc}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </section>

      <section className="cartao secao" aria-labelledby="t-botao">
        <h2 id="t-botao">Ao chegar ao veículo</h2>
        <p>Avise o motorista que você precisa de apoio para embarcar (rampa, elevador ou mais tempo).</p>
        <label htmlFor={idSelect}>Ônibus</label>
        <select id={idSelect} value={veiculoSelecionado ?? ''} onChange={(e) => setVeiculoSelecionado(e.target.value || null)}>
          <option value="">Escolha o ônibus</option>
          {opcoes.map(({ v, eta }) => (
            <option key={v.id} value={v.id}>
              Linha {v.numero} · ônibus {v.id}{v.acessivel ? ' · acessível' : ''}
              {eta !== undefined && pontoPerto ? ` · ${tempoDeChegada(eta).principal} em ${pontoPerto.nome}` : ''}
            </option>
          ))}
        </select>
        <button type="button" className="botao primario largo botao-acess" onClick={acionar} disabled={enviando}>
          <Accessibility aria-hidden="true" size={24} /> Acionar botão de acessibilidade
        </button>
        {msg && <p className={msg.ok ? 'aviso-ok' : 'aviso-erro'}>{msg.texto}</p>}
      </section>
    </div>
  );
}
