// Sobe a API (FastAPI + simulador) ou roda os testes do backend.
//   node scripts/api.mjs            → http://127.0.0.1:8000
//   node scripts/api.mjs --pytest   → testes pytest
import { spawn } from 'node:child_process';
import { BACKEND, PYTHON_VENV } from './comum.mjs';

const pytest = process.argv.includes('--pytest');
const porta = process.env.PORTA ?? '8000';
const args = pytest
  ? ['-m', 'pytest', '-q', '-p', 'no:warnings']
  : ['-m', 'uvicorn', 'movecidade.main:app', '--host', '127.0.0.1', '--port', porta];

const filho = spawn(PYTHON_VENV, args, { cwd: BACKEND, stdio: 'inherit', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
filho.on('exit', (codigo) => process.exit(codigo ?? 0));
for (const sinal of ['SIGINT', 'SIGTERM']) process.on(sinal, () => filho.kill(sinal));
