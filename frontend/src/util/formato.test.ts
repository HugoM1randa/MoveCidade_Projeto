import { describe, expect, it } from 'vitest';
import { caminhada, contraste, distancia, rotuloDia, tempoDeChegada, textoLotacao, textoSeguinte, tracoDoPadrao, trajetoCurto } from './formato';
import { deslocar, haversine } from './geo';

describe('tempoDeChegada', () => {
  it('mostra "agora", "chegando" e minutos', () => {
    expect(tempoDeChegada(10).principal).toBe('agora');
    expect(tempoDeChegada(45).principal).toBe('chegando');
    expect(tempoDeChegada(240).principal).toBe('4 min');
    expect(tempoDeChegada(240).falado).toBe('chega em 4 minutos');
    expect(tempoDeChegada(3900).principal).toBe('1 h 5 min');
  });
  it('sem dado não inventa número', () => {
    expect(tempoDeChegada(null).principal).toBe('sem previsão');
    expect(tempoDeChegada(undefined).estado).toBe('sem');
  });
  it('texto do ônibus seguinte', () => {
    expect(textoSeguinte(840)).toBe('depois: 14 min');
    expect(textoSeguinte(null)).toBeNull();
  });
});

describe('distância e caminhada', () => {
  it('formata metros e quilômetros em pt-BR', () => {
    expect(distancia(123)).toBe('120 m');
    expect(distancia(4)).toBe('menos de 10 m');
    expect(distancia(1530)).toBe('1,5 km');
  });
  it('caminhada a 80 m por minuto, mínimo 1 min', () => {
    expect(caminhada(120)).toBe('~2 min a pé');
    expect(caminhada(10)).toBe('~1 min a pé');
  });
});

describe('textos acessíveis', () => {
  it('lotação sempre em texto', () => {
    expect(textoLotacao('baixa')).toBe('lotação baixa');
    expect(textoLotacao('alta')).toBe('lotação alta');
    expect(textoLotacao(null)).toBe('lotação sem informação');
  });
  it('padrões de traçado diferentes para cada tipo', () => {
    const padroes = new Set([tracoDoPadrao('tracejado'), tracoDoPadrao('pontilhado'), tracoDoPadrao('traco_ponto')]);
    expect(padroes.size).toBe(3);
    expect(tracoDoPadrao('continuo')).toBeUndefined();
  });
  it('trajeto com seta dupla', () => {
    expect(trajetoCurto('Centro – Bairro Jardim')).toBe('Centro ↔ Bairro Jardim');
  });
});

describe('contraste das cores de linha', () => {
  it('paleta passa 4,5:1 com branco', () => {
    for (const cor of ['#1D4ED8', '#B91C1C', '#047857', '#7E22CE', '#C2410C', '#BE185D', '#A16207']) {
      expect(contraste(cor, '#FFFFFF')).toBeGreaterThanOrEqual(4.5);
    }
  });
  it('cor clara do protótipo antigo reprova', () => {
    expect(contraste('#38BDF8', '#FFFFFF')).toBeLessThan(4.5);
  });
});

describe('geo', () => {
  it('seta do teclado move ~25 m', () => {
    const a = { lat: -21.60353, lon: -48.36632 };
    expect(haversine(a, deslocar(a, 25, 0))).toBeCloseTo(25, 0);
    expect(haversine(a, deslocar(a, 0, -100))).toBeCloseTo(100, 0);
  });
});

describe('rotuloDia', () => {
  it('agrupa por hoje, ontem e dia da semana', () => {
    const hoje = new Date(2026, 9, 22, 15);
    expect(rotuloDia(new Date(2026, 9, 22, 8), hoje)).toBe('Hoje');
    expect(rotuloDia(new Date(2026, 9, 21, 8), hoje)).toBe('Ontem');
    expect(rotuloDia(new Date(2026, 9, 19, 8), hoje)).toBe('Segunda-feira');
  });
});
