import { Bell, LayoutDashboard, LogOut, MapPin, Route } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { usePolling } from '../estado/usePolling';
import type { Painel } from '../tipos';

export interface ContextoGestor {
  painel: Painel | null;
  erroPainel: string | null;
}

// Menu com SOMENTE quatro itens, como pedido pelo cliente.
const MENU = [
  { para: '/gestor', rotulo: 'Painel', Icone: LayoutDashboard, fim: true },
  { para: '/gestor/alertas', rotulo: 'Alertas', Icone: Bell },
  { para: '/gestor/linhas', rotulo: 'Linhas', Icone: Route },
  { para: '/gestor/pontos', rotulo: 'Pontos', Icone: MapPin },
];

export function LayoutGestor() {
  const local = useLocation();
  const navegar = useNavigate();
  const [sessao, setSessao] = useState<'verificando' | 'ok' | 'sair'>('verificando');
  const { dados: painel, erro } = usePolling<Painel>(sessao === 'ok' ? '/api/gestor/painel' : null, 2000);

  useEffect(() => {
    api.get<{ autenticado: boolean }>('/api/gestor/sessao')
      .then((s) => setSessao(s.autenticado ? 'ok' : 'sair'))
      .catch(() => setSessao('sair'));
  }, [local.pathname]);

  useEffect(() => {
    if (erro && /Entre com o usuário/.test(erro)) setSessao('sair');
  }, [erro]);

  async function sair() {
    await api.post('/api/gestor/logout').catch(() => undefined);
    navegar('/gestor/login', { replace: true });
  }

  if (sessao === 'sair') return <Navigate to={`/gestor/login?voltar=${encodeURIComponent(local.pathname)}`} replace />;
  if (sessao === 'verificando') return <p className="pagina">Verificando acesso…</p>;

  const pendentes = painel?.alertas_pendentes ?? 0;
  return (
    <div className="app-gestor">
      <a className="pular" href="#conteudo">Pular para o conteúdo</a>
      <header className="topo-gestor">
        <p className="marca"><img src="/icone.svg" alt="" width={28} height={28} /> MoveCidade <span className="sub">· painel do gestor</span></p>
        <p className="status-frota" aria-live="off">
          <span className="ponto-vivo" aria-hidden="true" />
          {painel ? `${painel.veiculos_ativos} de ${painel.veiculos_cadastrados} veículos ativos · turno da ${painel.turno}` : 'Carregando…'}
        </p>
        <button type="button" className="botao texto" onClick={sair}>
          <LogOut aria-hidden="true" size={18} /> Sair
        </button>
      </header>
      <div className="gestor-corpo">
        <nav aria-label="Menu do gestor" className="menu-lateral">
          <ul>
            {MENU.map(({ para, rotulo, Icone, fim }) => (
              <li key={para}>
                <NavLink to={para} end={fim}>
                  <Icone aria-hidden="true" size={20} />
                  {rotulo}
                  {rotulo === 'Alertas' && pendentes > 0 && <span className="contador">{pendentes}<span className="sr-only"> pendentes</span></span>}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main id="conteudo" tabIndex={-1} className="gestor-conteudo">
          <Outlet context={{ painel, erroPainel: erro } satisfies ContextoGestor} />
        </main>
      </div>
    </div>
  );
}
