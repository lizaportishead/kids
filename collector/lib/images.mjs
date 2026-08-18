import { mkdir, writeFile } from 'node:fs/promises';
import { extname } from 'node:path';

// Скачиваем картинки к себе: CDN-ссылки инстаграма подписаны и живут недолго.
export async function saveImage(url, name, outDir) {
  if (!url) return null;
  try {
    const res = await fetch(url, { headers: { 'user-agent': UA } });
    if (!res.ok) return null;
    const type = res.headers.get('content-type') || '';
    const ext = type.includes('png') ? '.png' : type.includes('webp') ? '.webp' : extname(new URL(url).pathname) || '.jpg';
    await mkdir(outDir, { recursive: true });
    const file = name + (ext.startsWith('.') ? ext : '.' + ext);
    await writeFile(new URL(file, 'file://' + outDir + '/'), Buffer.from(await res.arrayBuffer()));
    return 'data/images/' + file;
  } catch {
    return null;
  }
}

export const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
