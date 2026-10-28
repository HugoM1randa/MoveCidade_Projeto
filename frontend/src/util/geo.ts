export interface Posicao {
  lat: number;
  lon: number;
}

const R = 6371000;

export function haversine(a: Posicao, b: Posicao): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Desloca uma posição em metros para leste (+) e norte (+). Usado pelas setas do teclado no pino. */
export function deslocar(p: Posicao, lesteM: number, norteM: number): Posicao {
  const dLat = norteM / 111320;
  const dLon = lesteM / (111320 * Math.cos((p.lat * Math.PI) / 180));
  return { lat: +(p.lat + dLat).toFixed(6), lon: +(p.lon + dLon).toFixed(6) };
}

/** Praça da Matriz — posição inicial padrão do pino. */
export const PRACA_DA_MATRIZ: Posicao = { lat: -21.60353, lon: -48.36632 };
export const CENTRO_MATAO: [number, number] = [-21.6045, -48.3655];
