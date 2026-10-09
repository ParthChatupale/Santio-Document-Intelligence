import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const root = fileURLToPath(new URL('../', import.meta.url));
const python = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
if (!existsSync(python)) {
  console.error('Create .venv and install the Python dependencies first. See docs/GUI_USAGE.md.');
  process.exit(1);
}
process.env.SANTIO_API_PORT ||= '8766';
const child = spawn(python, ['-m', 'pbl_docintel.gui.cli', '--workspace', root, '--port', process.env.SANTIO_API_PORT], { cwd: root, stdio: 'inherit', windowsHide: true });
let server;
let stopping = false;
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  await server?.close();
  if (process.platform === 'win32' && child.pid && child.exitCode === null) {
    // Windows venv launchers create a second Python process. Stop the owned
    // process tree so Ctrl+C cannot leave the API or converter behind.
    await new Promise(resolve => {
      const kill = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {windowsHide:true, stdio:'ignore'});
      kill.on('exit', resolve); kill.on('error', resolve);
    });
  } else child.kill();
  process.exitCode = code;
}
child.on('error', error => { console.error(error); void stop(1); });
child.on('exit', code => { if (!stopping) { console.error('Python service stopped.'); void stop(code || 1); } });
process.on('SIGINT', () => void stop());
process.on('SIGTERM', () => void stop());
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (child.exitCode !== null) throw new Error('Python service failed to start.');
    try {
      const response = await fetch(`http://127.0.0.1:${process.env.SANTIO_API_PORT}/api/papers`);
      if (response.ok) break;
      throw new Error(await response.text());
    } catch (error) {
      if (attempt === 99) throw error;
      await new Promise(resolve => setTimeout(resolve, 150));
    }
  }
  server = await createServer({ configFile: fileURLToPath(new URL('../frontend/vite.config.ts', import.meta.url)) });
  await server.listen();
  console.log('\nSantio: http://127.0.0.1:5173 · Ctrl+C stops both services\n');
} catch (error) { console.error(error); await stop(1); }
