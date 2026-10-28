import { CheckCircle2, CircleAlert, Clock, Info, Users, WifiOff } from 'lucide-react';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import type { StatusCodigo } from '../tipos';

/** Status operacional SEMPRE com ícone + texto (nunca só cor). */
export function Status({ s }: { s: StatusCodigo }) {
  const icones: Record<string, ReactNode> = {
    operando: <CheckCircle2 aria-hidden="true" size={18} />,
    atraso: <Clock aria-hidden="true" size={18} />,
    lotacao: <Users aria-hidden="true" size={18} />,
    sem_sinal: <WifiOff aria-hidden="true" size={18} />,
  };
  return (
    <span className={`status status-${s.codigo}`}>
      {icones[s.codigo] ?? <CircleAlert aria-hidden="true" size={18} />}
      {s.texto}
    </span>
  );
}

/** Botão ⓘ que mostra uma frase de ajuda (toggletip acessível). */
export function Ajuda({ titulo, texto }: { titulo: string; texto: string }) {
  const [aberto, setAberto] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setAberto(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setAberto(false);
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [aberto]);
  return (
    <span className="ajuda" ref={ref}>
      <button type="button" className="botao-icone pequeno" aria-expanded={aberto} aria-controls={id} onClick={() => setAberto((v) => !v)}>
        <Info aria-hidden="true" size={18} />
        <span className="sr-only">O que é {titulo}?</span>
      </button>
      <span id={id} role="status" className={`ajuda-balao${aberto ? ' aberto' : ''}`}>
        {aberto ? texto : ''}
      </span>
    </span>
  );
}
