import { Accessibility, History, House, Map as MapIcon, WifiOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { BannerViagem } from './BannerViagem';

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  return online;
}

const ITENS = [
  { para: '/', rotulo: 'Início', Icone: House, fim: true },
  { para: '/mapa', rotulo: 'Mapa', Icone: MapIcon },
  { para: '/historico', rotulo: 'Histórico', Icone: History },
  { para: '/acessibilidade', rotulo: 'Acessibilidade', Icone: Accessibility },
];

export function LayoutPassageiro() {
  const online = useOnline();
  return (
    <div className="app-passageiro">
      <a className="pular" href="#conteudo">Pular para o conteúdo</a>
      <header className="topo">
        <NavLink to="/" className="marca" aria-label="MoveCidade, início">
          <img src="/icone.svg" alt="" width={28} height={28} /> <span>MoveCidade</span>
        </NavLink>
        <nav aria-label="Principal" className="nav-principal">
          <ul>
            {ITENS.map(({ para, rotulo, Icone, fim }) => (
              <li key={para}>
                <NavLink to={para} end={fim}>
                  <Icone aria-hidden="true" size={22} />
                  <span>{rotulo}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      {!online && (
        <p className="faixa-offline" role="status">
          <WifiOff aria-hidden="true" size={18} /> Sem conexão — mostrando últimos dados.
        </p>
      )}
      <BannerViagem />
      <main id="conteudo" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
