import { useCallback, useEffect, useRef, useState } from 'react';
import { CENTRO_MATAO, haversine, type Posicao } from '../util/geo';

export type EstadoGps = 'desligado' | 'buscando' | 'ativo' | 'negado' | 'indisponivel' | 'fora';

const LIMITE_MATAO_M = 15000;   // acima disso a pessoa está longe das linhas de Matão
const MOVIMENTO_MIN_M = 15;     // ignora ruído do GPS: só atualiza se andou mais que isso

export const MENSAGENS_GPS: Record<EstadoGps, string> = {
  desligado: '',
  buscando: 'Procurando sua localização…',
  ativo: 'Localização em tempo real ativa.',
  negado: 'Permissão de localização negada. Libere o acesso no navegador ou mova o pino no mapa.',
  indisponivel: 'Não foi possível obter sua localização agora. Mova o pino no mapa.',
  fora: 'Você parece estar fora de Matão. Mostrando o Centro; mova o pino para simular.',
};

/**
 * Localização real do aparelho (navigator.geolocation.watchPosition), atualizada enquanto o app estiver
 * aberto. LGPD: a posição só vai para a consulta de pontos próximos; nada é gravado no servidor
 * (o log de acesso omite lat/lon) nem no aparelho.
 */
export function useLocalizacaoReal(aoMudar: (p: Posicao) => void) {
  const [estado, setEstado] = useState<EstadoGps>('desligado');
  const [precisaoM, setPrecisaoM] = useState<number | null>(null);
  const watch = useRef<number | null>(null);
  const ultima = useRef<Posicao | null>(null);
  const callback = useRef(aoMudar);
  callback.current = aoMudar;

  const desligar = useCallback(() => {
    if (watch.current !== null && 'geolocation' in navigator) navigator.geolocation.clearWatch(watch.current);
    watch.current = null;
    ultima.current = null;
    setPrecisaoM(null);
    setEstado('desligado');
  }, []);

  const ligar = useCallback(() => {
    if (!('geolocation' in navigator)) {
      setEstado('indisponivel');
      return;
    }
    if (watch.current !== null) return;
    setEstado('buscando');
    watch.current = navigator.geolocation.watchPosition(
      (pos) => {
        const p = { lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) };
        setPrecisaoM(Math.round(pos.coords.accuracy));
        if (haversine(p, { lat: CENTRO_MATAO[0], lon: CENTRO_MATAO[1] }) > LIMITE_MATAO_M) {
          setEstado('fora');
          return;
        }
        setEstado('ativo');
        if (!ultima.current || haversine(ultima.current, p) >= MOVIMENTO_MIN_M) {
          ultima.current = p;
          callback.current(p);
        }
      },
      (erro) => setEstado(erro.code === erro.PERMISSION_DENIED ? 'negado' : 'indisponivel'),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
    );
  }, []);

  useEffect(() => () => {
    if (watch.current !== null && 'geolocation' in navigator) navigator.geolocation.clearWatch(watch.current);
  }, []);

  return { estado, precisaoM, ligar, desligar };
}
