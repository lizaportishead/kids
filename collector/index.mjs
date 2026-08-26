import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { collectInstagram } from './sources/instagram.mjs';
import { collectProdlenka } from './sources/prodlenka.mjs';
import { collectEnterspace } from './sources/enterspace.mjs';
import { collectMathline } from './sources/mathline.mjs';
import { dedupe, filterEvents } from './lib/normalize.mjs';
import { saveImage } from './lib/images.mjs';
import { fetchPublicEvents, pushEvents, supabaseEnabled } from './lib/supabase.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const OUT = resolve(root, 'data/events.json');
const IMG_DIR = resolve(root, 'data/images');

const RUNNERS = { instagram: collectInstagram, prodlenka: collectProdlenka, enterspace: collectEnterspace, mathline: collectMathline };

const now = new Date();
const sources = JSON.parse(await readFile(resolve(here, 'sources.json'), 'utf8'));
const collected = [];
const report = [];

for (const source of sources) {
  const run = RUNNERS[source.type];
  if (!run) { report.push({ source: source.id, status: 'skipped', reason: 'нет обработчика для типа ' + source.type }); continue; }
  if (source.type === 'prodlenka' && process.env.SKIP_BROWSER) { report.push({ source: source.id, status: 'skipped', reason: 'SKIP_BROWSER=1' }); continue; }
  try {
    const events = await run(source, now);
    for (const ev of events) {
      if (ev.imageRemote) {
        ev.image = (await saveImage(ev.imageRemote, ev.imageKey || ev.id, IMG_DIR)) || null;
        delete ev.imageRemote; delete ev.imageKey;
      }
      collected.push(ev);
    }
    report.push({ source: source.id, status: 'ok', events: events.length });
  } catch (err) {
    report.push({ source: source.id, status: 'error', reason: String(err.message || err) });
  }
}

const events = filterEvents(dedupe(collected));

// Пустой прогон не должен обнулять афишу — оставляем прошлый файл.
let previous = null;
try { previous = JSON.parse(await readFile(OUT, 'utf8')); } catch { /* первый запуск */ }
if (!events.length && previous && previous.events && previous.events.length) {
  console.error('Ничего не собрано — оставляю предыдущий events.json');
  previous.updatedAt = now.toISOString();
  previous.report = report;
  await writeFile(OUT, JSON.stringify(previous, null, 2) + '\n');
} else {
  await mkdir(dirname(OUT), { recursive: true });
  await writeFile(OUT, JSON.stringify({ updatedAt: now.toISOString(), city: 'Белград', count: events.length, report, events }, null, 2) + '\n');
}

if (supabaseEnabled && events.length) {
  try {
    const r = await pushEvents(events);
    report.push({ source: 'supabase', status: 'ok', events: r.written });
  } catch (err) {
    report.push({ source: 'supabase', status: 'error', reason: String(err.message || err) });
  }
} else if (!supabaseEnabled) {
  console.error('SUPABASE_URL/SUPABASE_SERVICE_KEY не заданы — пишу только data/events.json');
}

// Зеркалим data/events.json с базы: там могут быть площадки, заведённые
// вручную мимо коллектора (например, Индиго) — их не потерять при перезаписи.
let mirrored = 0;
if (supabaseEnabled) {
  try {
    const all = filterEvents(await fetchPublicEvents());
    if (Array.isArray(all) && all.length) {
      await writeFile(OUT, JSON.stringify({ updatedAt: now.toISOString(), city: 'Белград', count: all.length, report, events: all }, null, 2) + '\n');
      mirrored = all.length;
    }
  } catch (err) {
    report.push({ source: 'supabase-mirror', status: 'error', reason: String(err.message || err) });
  }
}

console.table(report);
console.log('Событий в афише:', mirrored || events.length);
if (report.some((r) => r.status === 'error') && !events.length && !mirrored) process.exitCode = 1;
