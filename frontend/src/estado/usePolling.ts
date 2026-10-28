import { useCallback, useEffect, useRef, useState } from 'react';

export interface ResultadoPolling<T> {
  dados: T | null;
  erro: string | null;
  carregando: boolean;
  atualizar: () => void;
}

/**
 * Busca `url` a cada `intervaloMs` (padrão 2 s). Mantém os últimos dados em caso de falha
 * (a tela não "pisca" nem perde conteúdo) e pausa quando a aba está escondida.
 */
export function usePolling<T>(url: string | null, intervaloMs = 2000): ResultadoPolling<T> {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState<boolean>(!!url);
  const urlAtual = useRef(url);
  urlAtual.current = url;

  const buscar = useCallback(async () => {
    const alvo = urlAtual.current;
    if (!alvo) return;
    try {
      const resp = await fetch(alvo, { credentials: 'same-origin' });
      if (!resp.ok) {
        let msg = 'Não foi possível atualizar. Tentando de novo…';
        try {
          const j = await resp.json();
          if (resp.status < 500 && typeof j?.erro === 'string') msg = j.erro;
        } catch {
          /* sem corpo */
        }
        throw new Error(msg);
      }
      const json = (await resp.json()) as T;
      if (urlAtual.current === alvo) {
        setDados(json);
        setErro(null);
      }
    } catch (e) {
      if (urlAtual.current === alvo) {
        setErro(navigator.onLine ? (e instanceof Error && e.message ? e.message : 'Não foi possível atualizar. Tentando de novo…') : 'Sem conexão — mostrando últimos dados.');
      }
    } finally {
      if (urlAtual.current === alvo) setCarregando(false);
    }
  }, []);

  useEffect(() => {
    if (!url) {
      setCarregando(false);
      return;
    }
    setCarregando(true);
    buscar();
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') buscar();
    }, intervaloMs);
    const aoVoltar = () => document.visibilityState === 'visible' && buscar();
    document.addEventListener('visibilitychange', aoVoltar);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', aoVoltar);
    };
  }, [url, intervaloMs, buscar]);

  return { dados, erro, carregando, atualizar: buscar };
}
