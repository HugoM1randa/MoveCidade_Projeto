import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';

/**
 * Região aria-live única do app. `anunciar` fala uma frase no leitor de tela sem mover o foco.
 * Usada só em mudanças importantes (pino movido, ônibus "chegando", ações confirmadas).
 */
const Contexto = createContext<(texto: string, urgente?: boolean) => void>(() => {});

export function ProvedorAnunciador({ children }: { children: ReactNode }) {
  const [educado, setEducado] = useState('');
  const [urgente, setUrgente] = useState('');
  const temporizador = useRef<number>(0);

  const anunciar = useCallback((texto: string, ehUrgente = false) => {
    const set = ehUrgente ? setUrgente : setEducado;
    set('');
    window.clearTimeout(temporizador.current);
    // pequeno atraso para o leitor de tela perceber a troca mesmo com o mesmo texto
    temporizador.current = window.setTimeout(() => set(texto), 60);
  }, []);

  return (
    <Contexto.Provider value={anunciar}>
      {children}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {educado}
      </div>
      <div className="sr-only" aria-live="assertive" aria-atomic="true">
        {urgente}
      </div>
    </Contexto.Provider>
  );
}

export function useAnunciar() {
  return useContext(Contexto);
}
