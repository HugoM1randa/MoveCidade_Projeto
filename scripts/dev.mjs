// npm run dev → prepara o ambiente (se preciso) e sobe API + front juntos. Ctrl+C encerra os dois.
import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { FRONTEND, RAIZ, WINDOWS } from './comum.mjs';

await import('./setup.mjs');

const processos = [
  { nome: 'api', cor: '\x1b[34m', cmd: process.execPath, args: [join(RAIZ, 'scripts', 'api.mjs')], cwd: RAIZ },
  { nome: 'web', cor: '\x1b[32m', cmd: 'npm', args: ['run', 'dev'], cwd: FRONTEND },
];

const filhos = processos.map(({ nome, cor, cmd, args, cwd }) => {
  const p = spawn(cmd, args, { cwd, shell: WINDOWS && cmd === 'npm', env: { ...process.env, FORCE_COLOR: '1' } });
  const prefixo = `${cor}[${nome}]\x1b[0m `;
  const escrever = (dados) => process.stdout.write(dados.toString().split(/\r?\n/).filter(Boolean).map((l) => prefixo + l).join('\n') + '\n');
  p.stdout.on('data', escrever);
  p.stderr.on('data', escrever);
  p.on('exit', (c) => {
    console.log(`${prefixo}encerrado (código ${c}).`);
    encerrar();
  });
  return p;
});

console.log('\n  MoveCidade subindo…\n  Passageiro: http://localhost:5173/\n  Gestor:     http://localhost:5173/gestor  (usuário e senha no arquivo .env)\n');

let encerrando = false;
function encerrar() {
  if (encerrando) return;
  encerrando = true;
  for (const f of filhos) {
    if (WINDOWS && f.pid) spawn('taskkill', ['/pid', String(f.pid), '/T', '/F'], { stdio: 'ignore' });
    else f.kill('SIGTERM');
  }
  setTimeout(() => process.exit(0), 500);
}
process.on('SIGINT', encerrar);
process.on('SIGTERM', encerrar);
