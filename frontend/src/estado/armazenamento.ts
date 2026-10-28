/** localStorage com proteção: em modo privado ou com bloqueio, o app continua funcionando. */

export function ler<T>(chave: string, padrao: T): T {
  try {
    const bruto = window.localStorage.getItem(chave);
    if (bruto === null) return padrao;
    const valor = JSON.parse(bruto);
    if (padrao && typeof padrao === 'object' && !Array.isArray(padrao) && valor && typeof valor === 'object') {
      return { ...padrao, ...valor } as T;
    }
    return valor as T;
  } catch {
    return padrao;
  }
}

export function gravar<T>(chave: string, valor: T): void {
  try {
    window.localStorage.setItem(chave, JSON.stringify(valor));
  } catch {
    /* sem armazenamento disponível: segue só em memória */
  }
}

export function apagar(chave: string): void {
  try {
    window.localStorage.removeItem(chave);
  } catch {
    /* ignora */
  }
}
