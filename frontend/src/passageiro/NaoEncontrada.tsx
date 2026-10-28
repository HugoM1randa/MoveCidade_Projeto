import { Link } from 'react-router-dom';
import { usePagina } from '../componentes/comuns';

export function NaoEncontrada() {
  const titulo = usePagina('Página não encontrada');
  return (
    <div className="pagina estreita">
      <h1 ref={titulo} tabIndex={-1}>Página não encontrada</h1>
      <p>O endereço que você abriu não existe no MoveCidade.</p>
      <Link to="/" className="botao primario">Voltar ao início</Link>
    </div>
  );
}
