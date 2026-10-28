// Prepara tudo na primeira vez: .env, ambiente Python (FastAPI) e dependências do front.
// Nas próximas vezes só confere e segue (rápido).
import { spawnSync } from 'node:child_process';
import { copyFileSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { acharPython, BACKEND, existe, FRONTEND, PYTHON_VENV, RAIZ, rodar } from './comum.mjs';

if (!existe(join(RAIZ, '.env'))) {
  copyFileSync(join(RAIZ, '.env.example'), join(RAIZ, '.env'));
  console.log('[MoveCidade] .env criado a partir do .env.example (login do gestor: gestor / movecidade).');
}

const requisitos = join(BACKEND, 'requirements.txt');
const venvDir = join(BACKEND, '.venv');
const marca = join(venvDir, '.instalado');

// Um venv copiado de outro computador (ex.: pasta .venv de Windows) pode existir e não funcionar aqui,
// porque o pyvenv.cfg aponta para o Python da máquina original. Testa de verdade antes de aceitar.
function venvFunciona() {
  if (!existe(PYTHON_VENV)) return false;
  return spawnSync(PYTHON_VENV, ['-c', 'import sys'], { stdio: 'ignore' }).status === 0;
}

if (!venvFunciona()) {
  const py = acharPython();
  if (!py) {
    console.error('[MoveCidade] Não encontrei Python 3.11 ou mais novo. Instale em https://www.python.org/downloads/ e rode de novo.');
    process.exit(1);
  }
  if (existe(venvDir)) {
    console.log('[MoveCidade] backend/.venv não funciona neste computador; recriando …');
    rmSync(venvDir, { recursive: true, force: true });
  }
  console.log('[MoveCidade] Criando o ambiente Python em backend/.venv …');
  rodar(py[0], [...py[1], '-m', 'venv', venvDir]);
}
const req = readFileSync(requisitos, 'utf8');
if (!existe(marca) || readFileSync(marca, 'utf8') !== req) {
  console.log('[MoveCidade] Instalando dependências do backend …');
  rodar(PYTHON_VENV, ['-m', 'pip', 'install', '-q', '-r', requisitos]);
  writeFileSync(marca, req);
}

const nm = join(FRONTEND, 'node_modules');
if (!existe(nm) || statSync(join(FRONTEND, 'package.json')).mtimeMs > statSync(nm).mtimeMs) {
  console.log('[MoveCidade] Instalando dependências do front-end …');
  rodar('npm', ['install', '--no-fund', '--no-audit'], { cwd: FRONTEND });
}
