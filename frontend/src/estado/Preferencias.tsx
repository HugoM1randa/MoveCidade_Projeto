import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Viagem } from '../tipos';
import { PRACA_DA_MATRIZ, type Posicao } from '../util/geo';
import { apagar, gravar, ler } from './armazenamento';

export interface Filtros {
  somenteAcessiveis: boolean;
}

export type TamanhoTexto = 'normal' | 'grande' | 'maior';

interface Estado {
  filtros: Filtros;
  setFiltro: (chave: keyof Filtros, valor: boolean) => void;
  altoContraste: boolean;
  setAltoContraste: (v: boolean) => void;
  tamanhoTexto: TamanhoTexto;
  setTamanhoTexto: (v: TamanhoTexto) => void;
  favoritos: { linhas: string[]; pontos: string[] };
  alternarFavorito: (tipo: 'linhas' | 'pontos', id: string) => void;
  pino: Posicao;
  setPino: (p: Posicao) => void;
  veiculoSelecionado: string | null;
  setVeiculoSelecionado: (id: string | null) => void;
  viagemAtual: Viagem | null;
  embarcar: (v: Viagem) => void;
  desembarcar: (destinoId: string, destinoNome: string, atrasoMin: number) => void;
  cancelarViagem: () => void;
  historico: Viagem[];
  apagarHistorico: () => void;
}

const Contexto = createContext<Estado | null>(null);

const K = {
  filtros: 'mc.filtros',
  contraste: 'mc.altoContraste',
  texto: 'mc.tamanhoTexto',
  favoritos: 'mc.favoritos',
  pino: 'mc.pino',
  veiculo: 'mc.veiculoSelecionado',
  viagem: 'mc.viagemAtual',
  historico: 'mc.historico',
};

function usePersistido<T>(chave: string, padrao: T): [T, (v: T | ((a: T) => T)) => void] {
  const [valor, setValor] = useState<T>(() => ler(chave, padrao));
  useEffect(() => gravar(chave, valor), [chave, valor]);
  return [valor, setValor];
}

export function ProvedorPreferencias({ children }: { children: ReactNode }) {
  const [filtros, setFiltros] = usePersistido<Filtros>(K.filtros, { somenteAcessiveis: false });
  const [altoContraste, setAltoContraste] = usePersistido<boolean>(K.contraste, false);
  const [tamanhoTexto, setTamanhoTexto] = usePersistido<TamanhoTexto>(K.texto, 'normal');
  const [favoritos, setFavoritos] = usePersistido<{ linhas: string[]; pontos: string[] }>(K.favoritos, { linhas: [], pontos: [] });
  const [pino, setPino] = usePersistido<Posicao>(K.pino, PRACA_DA_MATRIZ);
  const [veiculoSelecionado, setVeiculoSelecionado] = usePersistido<string | null>(K.veiculo, null);
  const [viagemAtual, setViagemAtual] = usePersistido<Viagem | null>(K.viagem, null);
  const [historico, setHistorico] = usePersistido<Viagem[]>(K.historico, []);

  useEffect(() => {
    document.documentElement.dataset.contraste = altoContraste ? 'alto' : 'normal';
  }, [altoContraste]);
  useEffect(() => {
    document.documentElement.dataset.texto = tamanhoTexto;
  }, [tamanhoTexto]);

  const setFiltro = useCallback((chave: keyof Filtros, valor: boolean) => setFiltros((f) => ({ ...f, [chave]: valor })), [setFiltros]);

  const alternarFavorito = useCallback(
    (tipo: 'linhas' | 'pontos', id: string) =>
      setFavoritos((f) => ({ ...f, [tipo]: f[tipo].includes(id) ? f[tipo].filter((x) => x !== id) : [...f[tipo], id] })),
    [setFavoritos],
  );

  const embarcar = useCallback((v: Viagem) => setViagemAtual(v), [setViagemAtual]);
  const cancelarViagem = useCallback(() => setViagemAtual(null), [setViagemAtual]);
  const desembarcar = useCallback(
    (destinoId: string, destinoNome: string, atrasoMin: number) => {
      if (viagemAtual) {
        const concluida: Viagem = { ...viagemAtual, destino_id: destinoId, destino_nome: destinoNome, fim: Date.now(), atraso_min: atrasoMin };
        setHistorico((h) => [concluida, ...h.filter((x) => x.id !== concluida.id)].slice(0, 300));
      }
      setViagemAtual(null);
    },
    [viagemAtual, setViagemAtual, setHistorico],
  );
  const apagarHistorico = useCallback(() => {
    setHistorico([]);
    apagar(K.historico);
  }, [setHistorico]);

  const valor = useMemo<Estado>(
    () => ({
      filtros, setFiltro, altoContraste, setAltoContraste, tamanhoTexto, setTamanhoTexto, favoritos, alternarFavorito,
      pino, setPino, veiculoSelecionado, setVeiculoSelecionado, viagemAtual, embarcar, desembarcar, cancelarViagem,
      historico, apagarHistorico,
    }),
    [filtros, setFiltro, altoContraste, setAltoContraste, tamanhoTexto, setTamanhoTexto, favoritos, alternarFavorito, pino,
      setPino, veiculoSelecionado, setVeiculoSelecionado, viagemAtual, embarcar, desembarcar, cancelarViagem, historico, apagarHistorico],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function usePreferencias(): Estado {
  const c = useContext(Contexto);
  if (!c) throw new Error('usePreferencias fora do provedor');
  return c;
}
