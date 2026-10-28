import { Bus } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import { api } from '../api';
import { BadgeLinha } from '../componentes/comuns';
import { useAnunciar } from '../estado/Anunciador';
import { useCatalogo } from '../estado/Catalogo';
import { usePreferencias } from '../estado/Preferencias';
import type { VeiculoMapa } from '../tipos';
import { duracao } from '../util/formato';

/** Viagem em andamento ("Embarquei") e o registro do desembarque — tudo só no aparelho (LGPD). */
export function BannerViagem() {
  const { viagemAtual, desembarcar, cancelarViagem } = usePreferencias();
  const { linhaPorId, pontoPorId } = useCatalogo();
  const anunciar = useAnunciar();
  const [aberto, setAberto] = useState(false);
  const [destino, setDestino] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [, setTique] = useState(0);
  const idSelect = useId();

  useEffect(() => {
    const id = window.setInterval(() => setTique((t) => t + 1), 30000);
    return () => window.clearInterval(id);
  }, []);

  const linha = viagemAtual ? linhaPorId.get(viagemAtual.linha_id) : undefined;
  const pontosDaLinha = (linha?.pontos ?? []).map((id) => pontoPorId.get(id)).filter(Boolean);

  async function abrir() {
    setAberto(true);
    if (!viagemAtual) return;
    try {
      const dados = await api.get<{ veiculos: VeiculoMapa[] }>('/api/veiculos/mapa');
      const v = dados.veiculos.find((x) => x.id === viagemAtual.veiculo_id);
      const sugestao = v?.ponto_atual_id ?? v?.proximo_ponto_id;
      if (sugestao && sugestao !== viagemAtual.origem_id) setDestino(sugestao);
    } catch {
      /* sem sugestão: o passageiro escolhe */
    }
  }

  async function confirmar() {
    if (!viagemAtual || !destino) return;
    setSalvando(true);
    const nome = pontoPorId.get(destino)?.nome ?? destino;
    let atraso = 0;
    try {
      const r = await api.get<{ segundos: number }>(`/api/linhas/${viagemAtual.linha_id}/tempo-planejado?de=${viagemAtual.origem_id}&ate=${destino}`);
      const real = (Date.now() - viagemAtual.inicio) / 1000;
      atraso = Math.max(0, Math.round((real - r.segundos) / 60));
    } catch {
      atraso = 0;
    }
    desembarcar(destino, nome, atraso);
    setSalvando(false);
    setAberto(false);
    anunciar(`Viagem registrada no histórico: linha ${viagemAtual.numero}, de ${viagemAtual.origem_nome} até ${nome}.`);
  }

  if (!viagemAtual) return null;
  return (
    <section className="banner-viagem" aria-label="Viagem em andamento">
      <div className="banner-linha">
        <Bus aria-hidden="true" size={20} />
        <BadgeLinha numero={viagemAtual.numero} cor={viagemAtual.cor} corNome={viagemAtual.cor_nome} nome={viagemAtual.nome_linha} />
        <span>
          Você embarcou em <strong>{viagemAtual.origem_nome}</strong> · há {duracao(Date.now() - viagemAtual.inicio)}
        </span>
      </div>
      {!aberto ? (
        <div className="acoes">
          <button type="button" className="botao primario" onClick={abrir}>Desembarquei</button>
          <button type="button" className="botao texto" onClick={cancelarViagem}>Cancelar viagem</button>
        </div>
      ) : (
        <div className="desembarque">
          <label htmlFor={idSelect}>Onde você desceu?</label>
          <select id={idSelect} value={destino} onChange={(e) => setDestino(e.target.value)}>
            <option value="">Escolha o ponto</option>
            {pontosDaLinha.map((p) => p && p.id !== viagemAtual.origem_id && (
              <option key={p.id} value={p.id}>{p.nome}</option>
            ))}
          </select>
          <div className="acoes">
            <button type="button" className="botao primario" onClick={confirmar} disabled={!destino || salvando}>Registrar viagem</button>
            <button type="button" className="botao texto" onClick={() => setAberto(false)}>Voltar</button>
          </div>
        </div>
      )}
    </section>
  );
}
