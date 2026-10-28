// Utilidades compartilhadas pelos scripts de desenvolvimento (sem dependências externas).
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..');
export const BACKEND = join(RAIZ, 'backend');
export const FRONTEND = join(RAIZ, 'frontend');
export const WINDOWS = process.platform === 'win32';
export const PYTHON_VENV = join(BACKEND, '.venv', WINDOWS ? 'Scripts' : 'bin', WINDOWS ? 'python.exe' : 'python');

/** Procura um Python 3.11+ no sistema para criar o ambiente virtual. */
export function acharPython() {
  const candidatos = WINDOWS ? [['py', ['-3']], ['python', []], ['python3', []]] : [['python3', []], ['python', []]];
  for (const [cmd, args] of candidatos) {
    const r = spawnSync(cmd, [...args, '-c', 'import sys; print(sys.version_info >= (3, 11))'], { encoding: 'utf8', shell: false });
    if (r.status === 0 && r.stdout.trim() === 'True') return [cmd, args];
  }
  return null;
}

export function rodar(cmd, args, opcoes = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', shell: WINDOWS && cmd === 'npm', ...opcoes });
  if (r.status !== 0) {
    console.error(`\n[MoveCidade] Falhou: ${cmd} ${args.join(' ')}`);
    process.exit(r.status ?? 1);
  }
}

export const existe = existsSync;
