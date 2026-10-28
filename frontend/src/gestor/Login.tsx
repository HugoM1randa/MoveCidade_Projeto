import { LogIn } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ErroApi } from '../api';
import { usePagina } from '../componentes/comuns';

export function Login() {
  const titulo = usePagina('Entrar no painel do gestor');
  const navegar = useNavigate();
  const [params] = useSearchParams();
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function entrar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setErro(null);
    try {
      await api.post('/api/gestor/login', { usuario, senha });
      const voltar = params.get('voltar');
      navegar(voltar && voltar.startsWith('/gestor') ? voltar : '/gestor', { replace: true });
    } catch (e2) {
      setErro(e2 instanceof ErroApi ? e2.message : 'Não foi possível entrar.');
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="pagina-login" id="conteudo">
      <form className="cartao form-login" onSubmit={entrar} aria-describedby={erro ? 'erro-login' : undefined}>
        <p className="marca"><img src="/icone.svg" alt="" width={32} height={32} /> MoveCidade</p>
        <h1 ref={titulo} tabIndex={-1}>Painel do gestor</h1>
        <div className="campo">
          <label htmlFor="usuario">Usuário</label>
          <input id="usuario" autoComplete="username" value={usuario} onChange={(e) => setUsuario(e.target.value)} required />
        </div>
        <div className="campo">
          <label htmlFor="senha">Senha</label>
          <input id="senha" type="password" autoComplete="current-password" value={senha} onChange={(e) => setSenha(e.target.value)} required />
        </div>
        {erro && <p id="erro-login" className="aviso-erro" role="alert">{erro}</p>}
        <button type="submit" className="botao primario largo" disabled={enviando}>
          <LogIn aria-hidden="true" size={20} /> Entrar
        </button>
        <p className="nota">O usuário e a senha ficam no arquivo <code>.env</code> do servidor.</p>
        <Link to="/">Ir para o app do passageiro</Link>
      </form>
    </main>
  );
}
