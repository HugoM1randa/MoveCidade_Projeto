import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

/** Abas acessíveis (padrão WAI-ARIA): setas, Home e End trocam de aba. */
export function Abas({ abas, ativa, aoTrocar, rotulo }: {
  abas: { id: string; rotulo: string; conteudo: ReactNode }[]; ativa: string; aoTrocar: (id: string) => void; rotulo: string;
}) {
  const base = useId();
  const botoes = useRef<(HTMLButtonElement | null)[]>([]);
  const indice = Math.max(0, abas.findIndex((a) => a.id === ativa));

  function teclar(e: KeyboardEvent) {
    let novo = indice;
    if (e.key === 'ArrowRight') novo = (indice + 1) % abas.length;
    else if (e.key === 'ArrowLeft') novo = (indice - 1 + abas.length) % abas.length;
    else if (e.key === 'Home') novo = 0;
    else if (e.key === 'End') novo = abas.length - 1;
    else return;
    e.preventDefault();
    aoTrocar(abas[novo].id);
    botoes.current[novo]?.focus();
  }

  return (
    <div className="abas">
      <div role="tablist" aria-label={rotulo} className="abas-lista" onKeyDown={teclar}>
        {abas.map((a, i) => (
          <button key={a.id} ref={(el) => { botoes.current[i] = el; }} role="tab" type="button" id={`${base}-aba-${a.id}`}
            aria-selected={a.id === ativa} aria-controls={`${base}-painel-${a.id}`} tabIndex={a.id === ativa ? 0 : -1}
            onClick={() => aoTrocar(a.id)}>
            {a.rotulo}
          </button>
        ))}
      </div>
      {abas.map((a) => (
        <div key={a.id} role="tabpanel" id={`${base}-painel-${a.id}`} aria-labelledby={`${base}-aba-${a.id}`}
          hidden={a.id !== ativa} tabIndex={0} className="abas-painel">
          {a.id === ativa && a.conteudo}
        </div>
      ))}
    </div>
  );
}
