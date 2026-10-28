/** Cliente HTTP do MoveCidade. Mensagens de erro em português simples, sem jargão técnico. */

export class ErroApi extends Error {
  status: number;
  constructor(mensagem: string, status: number) {
    super(mensagem);
    this.status = status;
  }
}

async function pedir<T>(metodo: string, url: string, corpo?: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(url, {
      method: metodo,
      headers: corpo !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
      credentials: 'same-origin',
    });
  } catch {
    throw new ErroApi(navigator.onLine ? 'Não foi possível falar com o servidor.' : 'Sem conexão com a internet.', 0);
  }
  if (!resp.ok) {
    let mensagem = 'Algo deu errado. Tente de novo.';
    try {
      const dados = await resp.json();
      if (typeof dados?.erro === 'string') mensagem = dados.erro;
    } catch {
      /* resposta sem JSON */
    }
    throw new ErroApi(mensagem, resp.status);
  }
  return (await resp.json()) as T;
}

export const api = {
  get: <T>(url: string) => pedir<T>('GET', url),
  post: <T>(url: string, corpo?: unknown) => pedir<T>('POST', url, corpo ?? {}),
  put: <T>(url: string, corpo: unknown) => pedir<T>('PUT', url, corpo),
  del: <T>(url: string) => pedir<T>('DELETE', url),
};

export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === false || v === '') continue;
    qs.set(k, String(v === true ? 1 : v));
  }
  const s = qs.toString();
  return s ? `?${s}` : '';
}
