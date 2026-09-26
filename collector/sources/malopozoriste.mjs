import { fetchHtml } from '../lib/http.mjs';
import { normalize } from '../lib/normalize.mjs';
import { iso } from '../lib/text.mjs';

// malopozoriste.co.rs — «Мало позориште „Душко Радовић“» (Абердарева 1, Ташмајдан,
// Палилула). WordPress, сербская кириллица. У театра две сцены: «Сцена за децу»
// (детская) и «Вечерња сцена» (взрослая, 20:00). Берём только детскую.
//
// Расписание — страница `/repertoar/`: серверный список `<div class="event-box…">`
// на ~месяц вперёд. В каждом показе день и месяц без года («26 <span>сеп</span>»),
// время, ссылка на спектакль `/theater-post/<slug>/` и кнопка покупки.
//
// Какая сцена — на странице репертуара не видно, поэтому спектакли берём из
// WP REST API: `/wp-json/wp/v2/theater-post?theater-performance-category=116`
// («Сцена за децу»). Оттуда же синопсис (content), возраст (таксономия age-group:
// «Узраст 0-3 / 4-7 / 8-11 / 12-99»), длительность («Трајање 75'») и афиша.
//
// SiteGround закрывает сайт капчей для адресов дата-центров: из GitHub Actions
// API и страницы спектаклей не открываются даже через r.jina.ai, а списки
// открываются через него. Поэтому, если API недоступен, берём спектакли со
// страницы `/predstave/scena-za-decu/` (карточки `theater-card`: название,
// ссылка, афиша, краткое описание, «Узраст …») — без длительности и полного
// синопсиса; у переведённых спектаклей описание всё равно из translations.json.
//
// Молодёжные спектакли той же рубрики (без возрастной группы или в 20:00) и
// показы без ссылки на tickets.rs не берём: это утренние показы в будни для
// организованных групп (школы, садики — «Купи карту» ведёт на страницу билетарницы
// с контактом «Организована продаја») и распроданные («Распродато»).
// Цена — с `/ulaznice/`: детская сцена 800 дин., «Књига лутања» и «Нежне силе
// космичке» — 1000 дин.
const BASE = 'https://malopozoriste.co.rs';
const KIDS_SCENE = 116;
const KIDS_LAST_START = '19:00';
const PRICE_DEFAULT = '800 RSD';
const PRICE_SPECIAL = { 'књига-лутања': '1000 RSD', 'нежне-силе-космичке': '1000 RSD' };
const MONTHS = ['јан', 'феб', 'мар', 'апр', 'мај', 'јун', 'јул', 'авг', 'сеп', 'окт', 'нов', 'дец'];

export async function collectMalopozoriste(source, now = new Date()) {
  const today = iso(now);
  const html = await fetchHtml(BASE + '/repertoar/', { label: 'malopozoriste' });
  const shows = await fetchShows().catch(async (err) => {
    console.error('malopozoriste: API недоступен (' + (err.message || err) + ') — беру список «Сцена за децу»');
    return fetchShowsFromList();
  });

  const events = [];
  for (const box of html.split(/<div class=["']event-box/).slice(1)) {
    const row = parseBox(box.split('<!-- event-box -->')[0], now);
    if (!row || row.date < today || !row.tickets) continue;
    const show = shows.get(row.slug);
    if (!show) continue; // вечерняя сцена или спектакль не из «Сцены за децу»
    // В «Сцене за децу» лежат и молодёжные спектакли («Крокодил» 13+, «Тесла»):
    // у них нет детского возраста или они идут вечером, в 20:00.
    if (!show.age || row.time >= KIDS_LAST_START) continue;

    const title = sentenceCase(show.title || row.title);
    const desc = show.desc || row.teaser || title;
    const raw = {
      title,
      desc,
      short: desc.slice(0, 150),
      date: row.date,
      time: row.time,
      dur: show.dur,
      age: show.age,
      price: PRICE_SPECIAL[row.slug] || PRICE_DEFAULT,
      url: row.tickets
    };
    const ev = normalize(source, raw, now);
    if (!ev) continue;
    const image = show.image || row.image;
    if (image) {
      ev.imageRemote = image;
      ev.imageKey = 'malopozoriste-' + (show.id || imageName(image));
    }
    events.push(ev);
  }
  return events;
}

// Один показ со страницы репертуара. Года нет: берём текущий, а если дата
// оказалась больше чем на 3 месяца в прошлом — это уже январь и далее
// следующего года.
function parseBox(box, now) {
  const mDate = box.match(/<h3>\s*(\d{1,2})\s*<span>\s*([^<\s]+)\s*<\/span>/);
  const mTime = box.match(/<span>\s*(\d{1,2}:\d{2})\s*<\/span>/);
  const mLink = box.match(/theater-header-link["']?\s+href=["']([^"']+)["']/);
  if (!mDate || !mTime || !mLink) return null;
  const month = MONTHS.indexOf(mDate[2].toLowerCase().slice(0, 3));
  if (month < 0) return null;

  let year = now.getFullYear();
  const candidate = new Date(year, month, Number(mDate[1]));
  if (now - candidate > 92 * 86400000) year++;
  const date = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(mDate[1]).padStart(2, '0');

  const slug = slugOf(mLink[1]);
  const title = decode((box.match(/<h4[^>]*>([\s\S]*?)<\/h4>/) || [])[1] || '').replace(/\s+/g, ' ').trim();
  const teaser = decode(((box.match(/<\/a>\s*<p>([\s\S]*?)<\/p>/) || [])[1] || '').replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').replace(/\.{3}$/, '…').trim();
  const tickets = (box.match(/href=["'](https:\/\/(?:www\.)?tickets\.rs\/event\/[^"']+)["']/) || [])[1] || null;
  const image = (box.match(/event-image[\s\S]*?<img[^>]+src=["']([^"']+)["']/) || [])[1] || null;
  return { date, time: mTime[1].padStart(5, '0'), slug, title, teaser, tickets, image };
}

// Спектакли детской сцены из WP REST API, ключ — декодированный slug.
async function fetchShows() {
  const url = BASE + '/wp-json/wp/v2/theater-post?per_page=100&theater-performance-category=' + KIDS_SCENE +
    '&_fields=id,slug,title,content,_links,_embedded&_embed=wp:featuredmedia,wp:term';
  const list = JSON.parse(await fetchHtml(url, { label: 'malopozoriste', proxy: false }));
  const shows = new Map();
  for (const p of list) {
    const terms = ((p._embedded && p._embedded['wp:term']) || []).flat();
    const media = ((p._embedded && p._embedded['wp:featuredmedia']) || [])[0] || {};
    const sizes = (media.media_details && media.media_details.sizes) || {};
    const image = (sizes.large || sizes.medium_large || {}).source_url || media.source_url || null;
    shows.set(slugOf(p.slug), {
      id: p.id,
      title: decode((p.title && p.title.rendered) || '').trim(),
      desc: textOf((p.content && p.content.rendered) || ''),
      age: ageOf(terms.filter((t) => t.taxonomy === 'age-group').map((t) => t.name)),
      dur: durOf(terms.filter((t) => t.taxonomy === 'theater-performance-category').map((t) => t.name)),
      image
    });
  }
  return shows;
}

// Запасной путь: карточки страницы «Сцена за децу».
async function fetchShowsFromList() {
  const html = await fetchHtml(BASE + '/predstave/scena-za-decu/', { label: 'malopozoriste' });
  const shows = new Map();
  for (const card of html.split(/<div class=["']theater-card["']/).slice(1)) {
    const mLink = card.match(/theater-header-link["']?\s+href=["']([^"']+)["'][^>]*>([^<]+)</);
    if (!mLink) continue;
    const image = (card.match(/<img[^>]+src=["']([^"']+)["'][^>]*theater-rectangle/) ||
      card.match(/<img[^>]+src=["'](https?:[^"']+)["']/) || [])[1] || null;
    const excerpt = decode(((card.match(/theater-excerpt["']?>\s*<span>([\s\S]*?)<\/span>/) || [])[1] || '').replace(/<[^>]+>/g, ''))
      .replace(/\s+/g, ' ').replace(/\.{3}$/, '…').trim();
    const ages = [...card.matchAll(/<span>\s*(Узраст[^<]*?)\s*<\/span>/g)].map((m) => m[1]);
    shows.set(slugOf(mLink[1]), {
      id: null,
      title: decode(mLink[2]).trim(),
      desc: excerpt,
      age: ageOf(ages),
      dur: null,
      image
    });
  }
  if (!shows.size) throw new Error('malopozoriste: на странице «Сцена за децу» не нашлось спектаклей');
  return shows;
}

// «…/2024/09/pepeljuga-naslovna.png» → «pepeljuga-naslovna».
function imageName(url) {
  return String(url).split('/').pop().replace(/\.[a-z0-9]+$/i, '').replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
}

// «Узраст 0-3» + «Узраст 4-7» → [0, 7]; «12-99» → верх 16. Малышам 0 лет
// показывать нечего — нижняя граница не меньше 1.
function ageOf(names) {
  let lo = null, hi = null;
  for (const n of names) {
    const m = n.match(/(\d{1,2})\s*[-–]\s*(\d{1,2})/);
    if (!m) continue;
    lo = lo === null ? Number(m[1]) : Math.min(lo, Number(m[1]));
    hi = hi === null ? Number(m[2]) : Math.max(hi, Number(m[2]));
  }
  if (lo === null) return null;
  return [Math.max(lo, 1), Math.min(hi, 16)];
}

function durOf(names) {
  for (const n of names) {
    const m = n.match(/Трајање\s*(\d{2,3})/);
    if (m) return m[1] + ' минут';
  }
  return null;
}

function slugOf(s) {
  let t = String(s);
  try { t = decodeURIComponent(t); } catch { /* уже декодирован */ }
  return t.replace(/\/+$/, '').split('/').pop().toLowerCase();
}

function textOf(htmlText) {
  const paras = [...String(htmlText).matchAll(/<p[^>]*>([\s\S]*?)<\/p>/g)].map((m) => m[1]);
  const text = (paras.length ? paras : [htmlText])
    .map((p) => decode(p.replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .join(' ');
  return text;
}

// «СУДБИНА ЈЕДНОГ ЧАРЛИЈА» → «Судбина једног чарлија».
function sentenceCase(s) {
  const t = String(s).toLowerCase();
  return t.replace(/\p{L}/u, (c) => c.toUpperCase());
}

const decode = (s) => String(s)
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;|&#0?38;/g, '&')
  .replace(/&quot;|&#0?34;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&#8216;|&#8217;|&rsquo;/g, "'")
  .replace(/&#8220;|&#8221;|&#8222;|&ldquo;|&rdquo;|&bdquo;/g, '"')
  .replace(/&#8230;|&hellip;/g, '…')
  .replace(/&ndash;|&#8211;/g, '–')
  .replace(/&mdash;|&#8212;/g, '—')
  .replace(/&#8242;|&prime;/g, "'");
