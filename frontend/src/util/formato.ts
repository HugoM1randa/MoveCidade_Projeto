import type { Fonte, Lotacao, Padrao } from '../tipos';

export interface TempoChegada {
  /** texto principal, ex.: "4 min", "agora", "chegando" */
  principal: string;
  /** texto para leitor de tela, ex.: "chega em 4 minutos" */
  falado: string;
  estado: 'agora' | 'chegando' | 'minutos' | 'sem';
}

/** Converte segundos (relógio do usuário) em texto curto de chegada. */
export function tempoDeChegada(segundos: number | null | undefined): TempoChegada {
  if (segundos === null || segundos === undefined || Number.isNaN(segundos)) {
    return { principal: 'sem previsão', falado: 'sem previsão no momento', estado: 'sem' };
  }
  if (segundos <= 20) return { principal: 'agora', falado: 'chegando agora', estado: 'agora' };
  if (segundos <= 60) return { principal: 'chegando', falado: 'chegando em menos de 1 minuto', estado: 'chegando' };
  const min = Math.round(segundos / 60);
  if (min >= 60) {
    const h = Math.floor(min / 60);
    const m = min % 60;
    const curto = m ? `${h} h ${m} min` : `${h} h`;
    return { principal: curto, falado: `chega em ${h} hora${h > 1 ? 's' : ''}${m ? ` e ${m} minutos` : ''}`, estado: 'minutos' };
  }
  return { principal: `${min} min`, falado: `chega em ${min} minuto${min > 1 ? 's' : ''}`, estado: 'minutos' };
}

export function textoSeguinte(segundos: number | null | undefined): string | null {
  if (segundos === null || segundos === undefined) return null;
  return `depois: ${tempoDeChegada(segundos).principal}`;
}

export function distancia(metros: number): string {
  if (metros < 10) return "menos de 10 m";
  if (metros < 1000) return `${Math.round(metros / 10) * 10} m`;
  return `${(metros / 1000).toFixed(1).replace('.', ',')} km`;
}

/** Tempo a pé a 80 m por minuto (mínimo de 1 minuto). */
export function caminhada(metros: number): string {
  return `~${Math.max(1, Math.round(metros / 80))} min a pé`;
}

export function textoLotacao(l: Lotacao | null | undefined): string {
  if (l === 'baixa') return 'lotação baixa';
  if (l === 'media') return 'lotação média';
  if (l === 'alta') return 'lotação alta';
  return 'lotação sem informação';
}

export function textoFonte(f: Fonte): string {
  if (f === 'ao_vivo') return 'ao vivo';
  if (f === 'programado') return 'programado';
  return 'sem previsão no momento';
}

/** Padrão do traçado no mapa: a cor nunca é o único diferencial entre linhas. */
export function tracoDoPadrao(p: Padrao): string | undefined {
  switch (p) {
    case 'tracejado':
      return '14 9';
    case 'pontilhado':
      return '1 10';
    case 'traco_ponto':
      return '16 8 1 8';
    default:
      return undefined;
  }
}

export function nomePadrao(p: Padrao): string {
  return { continuo: 'contínuo', tracejado: 'tracejado', pontilhado: 'pontilhado', traco_ponto: 'traço-ponto' }[p];
}

export function rotuloLinha(numero: string, corNome: string, nome: string): string {
  return `Linha ${numero}, cor ${corNome}, ${nome}`;
}

export function trajetoCurto(nome: string): string {
  return nome.replace(/\s+[–-]\s+/g, ' ↔ ');
}

/** Contraste WCAG entre duas cores #RRGGBB (usado na prévia de cor do gestor). */
export function contraste(a: string, b: string): number {
  const lum = (hex: string) => {
    const v = hex.replace('#', '');
    const c = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

export function duracao(ms: number): string {
  const min = Math.max(1, Math.round(ms / 60000));
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${min % 60} min`;
}

const DIAS = ['domingo', 'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado'];

/** Rótulo do dia para agrupar o histórico: Hoje, Ontem, nome do dia (até 6 dias) ou data. */
export function rotuloDia(data: Date, hoje = new Date()): string {
  const inicio = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const dias = Math.round((inicio(hoje) - inicio(data)) / 86400000);
  if (dias === 0) return 'Hoje';
  if (dias === 1) return 'Ontem';
  if (dias < 7) {
    const n = DIAS[data.getDay()];
    return n.charAt(0).toUpperCase() + n.slice(1);
  }
  return data.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long' });
}

export function horaMinuto(ts: number | string): string {
  return new Date(ts).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
