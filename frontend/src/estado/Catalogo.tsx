import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../api';
import type { Linha, Ponto } from '../tipos';

interface Catalogo {
  linhas: Linha[];
  pontos: Ponto[];
  linhaPorId: Map<string, Linha>;
  pontoPorId: Map<string, Ponto>;
  carregado: boolean;
  erro: string | null;
  recarregar: () => void;
}

const Contexto = createContext<Catalogo | null>(null);

/**
 * Linhas e pontos (com traçado e cores vindos do backend — as cores nunca ficam no front).
 * Verifica a versão do cadastro a cada 5 s: mudanças do gestor aparecem sozinhas no app.
 */
export function ProvedorCatalogo({ children }: { children: ReactNode }) {
  const [linhas, setLinhas] = useState<Linha[]>([]);
  const [pontos, setPontos] = useState<Ponto[]>([]);
  const [carregado, setCarregado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const versao = useRef<number | null>(null);

  const recarregar = useCallback(async () => {
    try {
      const [l, p] = await Promise.all([api.get<Linha[]>('/api/linhas'), api.get<Ponto[]>('/api/pontos')]);
      setLinhas(l);
      setPontos(p);
      setErro(null);
      setCarregado(true);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não foi possível carregar as linhas.');
    }
  }, []);

  useEffect(() => {
    let ativo = true;
    const verificar = async () => {
      try {
        const s = await api.get<{ versao_cadastro: number }>('/api/status');
        if (!ativo) return;
        if (versao.current !== s.versao_cadastro) {
          versao.current = s.versao_cadastro;
          await recarregar();
        }
      } catch {
        if (!carregado) await recarregar();
      }
    };
    verificar();
    const id = window.setInterval(() => document.visibilityState === 'visible' && verificar(), 5000);
    return () => {
      ativo = false;
      window.clearInterval(id);
    };
  }, [recarregar, carregado]);

  const valor = useMemo<Catalogo>(
    () => ({
      linhas, pontos, carregado, erro, recarregar,
      linhaPorId: new Map(linhas.map((l) => [l.id, l])),
      pontoPorId: new Map(pontos.map((p) => [p.id, p])),
    }),
    [linhas, pontos, carregado, erro, recarregar],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useCatalogo(): Catalogo {
  const c = useContext(Contexto);
  if (!c) throw new Error('useCatalogo fora do provedor');
  return c;
}
