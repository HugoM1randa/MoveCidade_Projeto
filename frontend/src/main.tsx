import { lazy, StrictMode, Suspense, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { registerSW } from 'virtual:pwa-register';
import { ProvedorAnunciador } from './estado/Anunciador';
import { ProvedorCatalogo } from './estado/Catalogo';
import { ProvedorPreferencias } from './estado/Preferencias';
import { Acessibilidade } from './passageiro/Acessibilidade';
import { Busca } from './passageiro/Busca';
import { DetalheLinha } from './passageiro/DetalheLinha';
import { Historico } from './passageiro/Historico';
import { Inicio } from './passageiro/Inicio';
import { LayoutPassageiro } from './passageiro/Layout';
import { MapaAoVivo } from './passageiro/MapaAoVivo';
import { NaoEncontrada } from './passageiro/NaoEncontrada';
import './estilos.css';
import './tema.css';

// O painel do gestor é carregado só quando alguém abre /gestor (o app do passageiro fica mais leve).
const Login = lazy(() => import('./gestor/Login').then((m) => ({ default: m.Login })));
const LayoutGestor = lazy(() => import('./gestor/Layout').then((m) => ({ default: m.LayoutGestor })));
const PainelGestor = lazy(() => import('./gestor/Painel').then((m) => ({ default: m.PainelGestor })));
const Alertas = lazy(() => import('./gestor/Alertas').then((m) => ({ default: m.Alertas })));
const LinhasGestor = lazy(() => import('./gestor/Linhas').then((m) => ({ default: m.LinhasGestor })));
const PontosGestor = lazy(() => import('./gestor/Pontos').then((m) => ({ default: m.PontosGestor })));

const carregando = (el: ReactNode) => <Suspense fallback={<p className="pagina">Carregando…</p>}>{el}</Suspense>;

const roteador = createBrowserRouter([
  {
    path: '/',
    element: <LayoutPassageiro />,
    children: [
      { index: true, element: <Inicio /> },
      { path: 'mapa', element: <MapaAoVivo /> },
      { path: 'busca', element: <Busca /> },
      { path: 'linha/:id', element: <DetalheLinha /> },
      { path: 'historico', element: <Historico /> },
      { path: 'acessibilidade', element: <Acessibilidade /> },
      { path: '*', element: <NaoEncontrada /> },
    ],
  },
  { path: '/gestor/login', element: carregando(<Login />) },
  {
    path: '/gestor',
    element: carregando(<LayoutGestor />),
    children: [
      { index: true, element: carregando(<PainelGestor />) },
      { path: 'alertas', element: carregando(<Alertas />) },
      { path: 'linhas', element: carregando(<LinhasGestor />) },
      { path: 'pontos', element: carregando(<PontosGestor />) },
    ],
  },
]);

if (import.meta.env.PROD) registerSW({ immediate: true });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ProvedorPreferencias>
      <ProvedorAnunciador>
        <ProvedorCatalogo>
          <RouterProvider router={roteador} />
        </ProvedorCatalogo>
      </ProvedorAnunciador>
    </ProvedorPreferencias>
  </StrictMode>,
);
