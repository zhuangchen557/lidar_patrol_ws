import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { extname, relative, resolve } from 'node:path'
import { build } from 'vite'

await build()

const projectRoot = resolve(new URL('..', import.meta.url).pathname.replace(/^\/(?:[A-Za-z]:)/, (match) => match.slice(1)))
const distRoot = resolve(projectRoot, 'dist')
const serverRoot = resolve(distRoot, 'server')
const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
}

async function collectFiles(directory) {
  const result = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === 'server') continue
    const absolute = resolve(directory, entry.name)
    if (entry.isDirectory()) result.push(...await collectFiles(absolute))
    else result.push(absolute)
  }
  return result
}

const staticFiles = await collectFiles(distRoot)
const entries = []
for (const file of staticFiles) {
  const route = `/${relative(distRoot, file).replaceAll('\\', '/')}`
  const bytes = await readFile(file)
  entries.push([route, bytes.toString('base64'), mimeTypes[extname(file)] || 'application/octet-stream'])
}

const workerSource = `
const files = new Map(${JSON.stringify(entries)});
function decode(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}
export default {
  async fetch(request) {
    const url = new URL(request.url);
    const requestedPath = url.pathname === '/' ? '/index.html' : url.pathname;
    const path = files.has(requestedPath) ? requestedPath : '/index.html';
    const file = files.get(path);
    if (!file) return new Response('Not Found', { status: 404 });
    const headers = {
      'content-type': file[2],
      'cache-control': path === '/index.html' ? 'no-cache' : 'public, max-age=31536000, immutable',
      'x-content-type-options': 'nosniff',
      'referrer-policy': 'same-origin',
    };
    return new Response(request.method === 'HEAD' ? null : decode(file[1]), { status: 200, headers });
  },
};
`

await mkdir(serverRoot, { recursive: true })
await writeFile(resolve(serverRoot, 'index.js'), workerSource)
