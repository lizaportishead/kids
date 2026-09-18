import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';

// bilet.bgf.rs/repertoar.php — Београдска филхармонија. Репертоар всего
// сезона отдаёт один POST на qrydata.php (тот же запрос, что страница шлёт
// сама при загрузке в режиме «цела сезона», tip_prikaza=1) — без логина и
// без кук, обычный JSON.
//
// В сезонном репертуаре вперемешку взрослые абонементные концерты и детские
// серии («Концерти за бебе», «...за предшколце», «...за школарце») —
// последние рассчитаны на организованные визиты садов/школ, и отдельная
// продажа билетов открывается лишь на отдельные сеансы. Признак такого
// сеанса — непустое поле `url` (ссылка на карточку концерта на www.bgf.rs);
// у обычных взрослых концертов оно пустое. Путь карточки детского концерта
// содержит «bebe»/«predskol(ce)»/«skolarc» — по этому и фильтруем. Со
// страницы карточки подтягиваем описание и цену (в JSON репертуара их нет).
const KIDS_URL_RE = /repertoar_cp\/[^"'\s]*(bebe|predskol|predshkol|skolarc|shkolart)/i;

export async function collectBgf(source, now = new Date()) {
  const rows = await fetchSeason(now);

  const events = [];
  for (const row of rows) {
    const url = row.url || '';
    if (!KIDS_URL_RE.test(url)) continue;

    const detail = await fetchDetail(url).catch((err) => {
      console.error('bgf: страница «' + url + '» не загрузилась: ' + (err.message || err));
      return null;
    });

    const rawTitle = (row.predstava_cyr || row.predstava || '').trim();
    const title = (detail && detail.title) || (rawTitle === rawTitle.toUpperCase() ? titleCase(rawTitle) : rawTitle);
    const desc = (detail && detail.desc) || title;
    const raw = {
      title,
      desc,
      short: desc.slice(0, 150),
      date: row.datum,
      time: (row.vreme || '10:00:00').slice(0, 5),
      dur: durationOf(row),
      age: ageOf(url),
      price: (detail && detail.price) || null,
      url: row.prostorterminid ? 'https://bilet.bgf.rs/scena.php?prostorterminid=' + row.prostorterminid : source.url
    };
    const ev = normalize(source, raw, now);
    if (!ev) continue;
    if (row.slika && /^https?:\/\//.test(row.slika)) {
      ev.imageRemote = row.slika;
      ev.imageKey = 'bgf-' + (row.prostorterminid || ev.id);
    }
    events.push(ev);
  }
  return events;
}

async function fetchSeason(now) {
  const body = new URLSearchParams({
    q: '1',
    godina: String(now.getFullYear()),
    mesec: String(now.getMonth() + 1),
    dan: '1',
    sdsp: '1',
    trazi: '',
    user_tipid: '',
    sap: '1', // только неоконченные показы
    ss: '0',
    tip_prikaza: '1', // «цела сезона» — весь сезон в одном ответе
    program: '0'
  });
  const res = await fetch('https://bilet.bgf.rs/qrydata.php', {
    method: 'POST',
    headers: {
      'user-agent': UA,
      'content-type': 'application/x-www-form-urlencoded; charset=utf-8',
      accept: 'application/json'
    },
    body: body.toString()
  });
  if (!res.ok) throw new Error('bgf qrydata.php: HTTP ' + res.status);
  const data = await res.json();
  return Array.isArray(data.resp) ? data.resp : [];
}

// «...бебе» — концерты для младенцев, «...предшколце» — для дошкольников,
// «...школарце» — для младших школьников.
function ageOf(url) {
  if (/bebe/i.test(url)) return [0, 3];
  if (/predskol|predshkol/i.test(url)) return [3, 7];
  if (/skolarc|shkolart/i.test(url)) return [7, 11];
  return null;
}

function durationOf(row) {
  if (!row.vreme || !row.vreme_do) return null;
  const [fh, fm] = row.vreme.split(':').map(Number);
  const [th, tm] = row.vreme_do.split(':').map(Number);
  const minutes = (th * 60 + tm) - (fh * 60 + fm);
  return minutes > 0 && minutes < 600 ? minutes + ' минут' : null;
}

// --- карточка концерта на www.bgf.rs ---------------------------------------

async function fetchDetail(url) {
  const html = await fetchText(url);
  const block = (html.match(/concert-content">([\s\S]*?)<!--\s*Tekst koncerta END/) || [])[1] || '';

  const titleM = block.match(/<(?:b|strong)>([^<]{6,120})<\/(?:b|strong)>/);
  const title = titleM ? decode(titleM[1]).trim() : null;

  const priceM = block.match(/(\d[\d.,]*)\s*динар/i);
  const price = priceM ? priceM[1].replace(/[.,]/g, '') + ' RSD' : null;

  const desc = stripPriceSentence(stripTags(block));

  return {
    title: title && title.length >= 6 ? title : null,
    desc: desc.length >= 20 ? desc : null,
    price
  };
}

// Вырезаем практическую фразу про групповые посещения и цену — она уже
// разобрана в price, дублировать её в описании незачем.
function stripPriceSentence(text) {
  return text.split(/(?<=[.!?])\s+/).filter((s) => !/динар/i.test(s)).join(' ').trim();
}

async function fetchText(url) {
  const res = await fetch(url, {
    headers: { 'user-agent': UA, 'accept-language': 'sr,ru;q=0.8,en;q=0.6', accept: 'text/html,application/xhtml+xml' }
  });
  if (!res.ok) throw new Error('bgf ' + url + ': HTTP ' + res.status);
  return res.text();
}

function stripTags(html) {
  return decode(html.replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();
}

// «КАРНЕВАЛ ЖИВОТИЊА» → «Карневал животиња» (запасной вариант, если на
// карточке не нашлось жирного заголовка).
function titleCase(s) {
  return String(s).toLowerCase().replace(/(^|[\s(«"„-])([\p{L}])/gu, (_, p, c) => p + c.toUpperCase());
}

const decode = (s) => String(s)
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&#8217;|&rsquo;/g, "'")
  .replace(/&#8220;|&#8221;|&ldquo;|&rdquo;/g, '"')
  .replace(/&#8230;|&hellip;/g, '…')
  .replace(/&ndash;/g, '–')
  .replace(/&mdash;/g, '—')
  .replace(/&#8211;/g, '–');
