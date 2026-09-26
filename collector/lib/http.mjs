import { UA } from './images.mjs';

// Загрузка HTML-страницы с повтором и запасным путём.
//
// С 22.09.2026 сайты pinokio.rs и pozoristancepuz.com (один сербский хостинг,
// 94.127.7.x) из GitHub Actions отвечают «fetch failed», хотя из браузера
// открываются. Поэтому: две прямые попытки с таймаутом, а если обе упали —
// та же страница через r.jina.ai (публичный «читатель», ходит к сайту со своих
// адресов). Он отдаёт отрисованный DOM: атрибуты в двойных кавычках, а не как
// в исходнике, — парсеры, которые им пользуются, не должны зависеть от вида
// кавычек.
const DIRECT_TIMEOUT_MS = 25000;
const PROXY_TIMEOUT_MS = 60000;

// Хосты, до которых в этом прогоне напрямую уже не достучались: к ним сразу
// идём через запасной путь, чтобы не ждать таймауты на каждой странице.
const directDown = new Set();
const PROXY_GAP_MS = 3500;
let lastProxyAt = 0;

export async function fetchHtml(url, { label = 'fetch', proxy = true } = {}) {
  const host = new URL(url).host;
  const errors = [];
  for (let attempt = 1; attempt <= 2 && !(proxy && directDown.has(host)); attempt++) {
    try {
      return await get(url, {
        'user-agent': UA,
        'accept-language': 'sr,ru;q=0.8,en;q=0.6',
        accept: 'text/html,application/xhtml+xml'
      }, DIRECT_TIMEOUT_MS);
    } catch (err) {
      errors.push(describe(err));
      if (attempt === 1) await sleep(3000);
    }
  }
  if (proxy) {
    if (errors.length) directDown.add(host);
    try {
      // Без ключа r.jina.ai пускает ~20 запросов в минуту — не чаще раза в 3,5 с.
      const wait = lastProxyAt + PROXY_GAP_MS - Date.now();
      if (wait > 0) await sleep(wait);
      lastProxyAt = Date.now();
      const html = await get('https://r.jina.ai/' + url, { 'x-return-format': 'html' }, PROXY_TIMEOUT_MS);
      if (errors.length) console.error(label + ': ' + url + ' напрямую не открылся (' + errors.join('; ') + ') — взял через r.jina.ai');
      return html;
    } catch (err) {
      errors.push('r.jina.ai: ' + describe(err));
    }
  }
  throw new Error(label + ' ' + url + ': ' + errors.join('; '));
}

async function get(url, headers, timeoutMs) {
  const res = await fetch(url, { headers, signal: AbortSignal.timeout(timeoutMs) });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.text();
}

// У undici настоящая причина лежит в err.cause («ECONNRESET», «UND_ERR_CONNECT_TIMEOUT»…),
// а в message — только «fetch failed»; без неё в отчёте ничего не понять.
function describe(err) {
  const cause = err && err.cause;
  const code = cause && (cause.code || cause.message);
  return String((err && err.message) || err) + (code ? ' (' + code + ')' : '');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
