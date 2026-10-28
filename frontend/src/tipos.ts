export type Padrao = 'continuo' | 'tracejado' | 'pontilhado' | 'traco_ponto';
export type Lotacao = 'baixa' | 'media' | 'alta';
export type Fonte = 'ao_vivo' | 'programado' | 'sem_previsao';

export interface Acessibilidade {
  rampa: boolean;
  piso_tatil: boolean;
  abrigo: boolean;
}

export interface Linha {
  id: string;
  numero: string;
  nome: string;
  cor: string;
  cor_nome: string;
  padrao: Padrao;
  intervalo_min: number;
  destino: string;
  origem: string;
  pontos: string[];
  comprimento_m: number;
  rota?: [number, number][];
}

export interface Ponto {
  id: string;
  nome: string;
  referencia: string;
  lat: number;
  lon: number;
  acessibilidade: Acessibilidade;
  status: 'operando' | 'desativado';
  linhas_atendidas: string[];
}

export interface PrevisaoLinha {
  linha_id: string;
  numero: string;
  nome: string;
  cor: string;
  cor_nome: string;
  padrao: Padrao;
  destino: string;
  fonte: Fonte;
  eta_s: number | null;
  eta_seguinte_s: number | null;
  lotacao: Lotacao | null;
  acessivel: boolean | null;
  veiculo_id: string | null;
  horario: string | null;
}

export interface PontoComChegadas extends Ponto {
  distancia_m?: number;
  caminhada_min?: number;
  linhas: PrevisaoLinha[];
}

export interface RespostaProximos {
  pontos: PontoComChegadas[];
  fora_do_raio: boolean;
  raio_m: number;
}

export interface VeiculoMapa {
  id: string;
  linha_id: string;
  numero: string;
  cor: string;
  cor_nome: string;
  lat: number;
  lon: number;
  ao_vivo: boolean;
  acessivel: boolean;
  lotacao: Lotacao | null;
  no_ponto: boolean;
  proximo_ponto: string | null;
  proximo_ponto_id: string | null;
  ponto_atual_id: string | null;
  eta_proximo_s: number | null;
}

export interface ProximoVeiculo {
  veiculo_id: string;
  eta_s: number;
  acessivel: boolean;
  lotacao: Lotacao;
  ocupacao_pct: number;
  proximo_ponto: string;
  no_ponto: boolean;
}

export interface DetalheLinha {
  linha: Linha;
  ponto: Ponto | null;
  previsao: PrevisaoLinha | null;
  proximos: ProximoVeiculo[];
  sem_sinal: { veiculo_id: string; acessivel: boolean }[];
  horarios: string[];
  intervalo_min: number;
  trajeto: {
    ordem: number;
    id: string;
    nome: string;
    operando: boolean;
    acessibilidade: Acessibilidade;
    onibus: { veiculo_id: string; no_ponto: boolean; acessivel: boolean }[];
  }[];
}

export interface ResultadoBusca {
  linhas: (Linha & { previsao: PrevisaoLinha | null; ponto_ref: { id: string; nome: string } | null })[];
  pontos: PontoComChegadas[];
}

export interface Viagem {
  id: string;
  linha_id: string;
  numero: string;
  cor: string;
  cor_nome: string;
  nome_linha: string;
  veiculo_id: string;
  origem_id: string;
  origem_nome: string;
  destino_id?: string;
  destino_nome?: string;
  inicio: number;
  fim?: number;
  atraso_min?: number;
}

// ---------------------------------------------------------------- gestor
export interface StatusCodigo {
  codigo: string;
  texto: string;
}

export interface VeiculoGestor {
  id: string;
  linha_id: string;
  numero: string;
  cor: string;
  capacidade: number;
  acessivel: boolean;
  status: StatusCodigo;
  ao_vivo: boolean;
  lat: number | null;
  lon: number | null;
  ocupacao_pct: number | null;
  lotacao: Lotacao | null;
  proximo_ponto: string | null;
  atraso_min: number | null;
}

export interface Kpi {
  valor: number | null;
  unidade: string;
  ajuda: string;
  [extra: string]: unknown;
}

export interface Alerta {
  id: string;
  tipo: 'atraso' | 'comboio' | 'lotacao' | 'acessibilidade';
  tipo_texto: string;
  linha_id: string;
  veiculo_id: string | null;
  titulo: string;
  descricao: string;
  sugestao: string;
  criado_em: string;
}

export interface Decisao {
  id: number;
  alerta_id: string;
  tipo: string;
  linha_id: string | null;
  veiculo_id: string | null;
  titulo: string;
  sugestao: string;
  decisao: 'aceito' | 'ignorado';
  resultado: string;
  decidido_em: string;
}

export interface Painel {
  turno: string;
  veiculos_ativos: number;
  veiculos_cadastrados: number;
  kpis: Record<'pontualidade' | 'tempo_espera' | 'ocupacao_horario' | 'duracao_viagem' | 'disponibilidade', Kpi>;
  frota: VeiculoGestor[];
  avisos: Alerta[];
  alertas_pendentes: number;
  fator_tempo: number;
}

export interface LinhaGestor extends Linha {
  status: StatusCodigo;
  qtd_pontos: number;
  qtd_veiculos: number;
  origem_tracado: string;
  veiculos: VeiculoGestor[];
}
