import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';

// ckvladadivljan.rs/wp — «Центар за културу „Влада Дивљан“» (Палилула,
// Белград), WordPress на плагине The Events Calendar с открытым REST API
// (никакой авторизации, обычный JSON): /wp-json/tribe/events/v1/events.
//
// Афиша площадки смешанная: детские спектакли соседствуют с концертами,
// презентациями книг и трибунами для взрослых, а рубрик на площадке нет —
// у всех событий пустые tribe_events_cat и post_tag. Берём только записи,
// где в заголовке или описании явно написано «za decu» / «dečija» / «dečji»
// — лучше пропустить детский спектакль без явной пометки (как «Asteriks i
// Obeliks», который значится просто «vesela predstava»), чем протащить в
// афишу взрослый концерт или презентацию книги.
const BASE = 'https://ckvladadivljan.rs/wp';
const KIDS_RE = /za\s+decu\b|de[cč]j[a-zžćč]*|de[cč]ij[a-zžćč]*/i;

export async function collectCkvladadivljan(source, now = new Date()) {
  const data = await fetchJson(BASE + '/wp-json/tribe/events/v1/events?per_page=50');
  const events = [];
  for (const row of data.events || []) {
    const title = squeeze(clean(row.title));
    const full = stripTags(row.description || '');
    if (!KIDS_RE.test(title) && !KIDS_RE.test(full)) continue;
    const desc = synopsisOf(full) || title;

    const [date, time] = String(row.start_date || '').split(' ');
    if (!date) continue;

    const raw = {
      title,
      desc,
      short: desc.slice(0, 150),
      date,
      time: (time || '10:00').slice(0, 5),
      dur: parseDur(full),
      price: priceOf(row),
      url: row.url || source.url
    };
    const ev = normalize(source, raw, now);
    if (!ev) continue;
    if (row.image && row.image.url) {
      ev.imageRemote = row.image.url;
      ev.imageKey = 'ckvladadivljan-' + row.id;
    }
    events.push(ev);
  }
  return events;
}

// «BESPLATNO» → «бесплатно»; числовая цена — как есть, с RSD; иначе цену
// на странице не разобрать, пусть normalize() подставит «уточняется».
function priceOf(row) {
  const cost = String(row.cost || '').trim();
  if (!cost) return null;
  if (/besplatn/i.test(cost)) return 'бесплатно';
  const m = cost.match(/(\d[\d.,]*)/);
  return m ? m[1].replace(/[.,]/g, '') + ' RSD' : null;
}

// Описание на странице — вперемешку служебные строки (дата/время/выдача
// билетов эмодзи-заголовком), сам синопсис и титры («Igraju: …»). Оставляем
// только синопсис: без служебных строк (дата и время уже разобраны отдельно)
// и без титров в конце.
function synopsisOf(text) {
  const lines = String(text).split('\n').map((s) => s.trim()).filter(Boolean);
  const isPractical = (l) => /^[🗓⏰🎫]/u.test(l) || /^\d{1,2}\s*[.:]\s*\d{1,2}/.test(l) || /^(podela|besplatne?\s+karte)/i.test(l);
  const isCredits = (l) => /^(va[sš]\b|centar za kulturu|tekst i re[zž]ija|re[zž]ija|scenografija|kostim|muzika|igraju|dramatizacija|adaptacija|koreograf)/i.test(l);
  return lines.filter((l) => !isPractical(l) && !isCredits(l)).join(' ');
}

// «Trajanje predstave oko 45 min.» → «45 минут». Даты в описании (`start_date`
// у площадки часто ставят формальный блок в 2-3 часа, не длительность показа)
// точнее не разобрать — если в тексте фразы нет, normalize() подставит «1 час».
function parseDur(text) {
  const m = String(text || '').match(/(\d{1,3})\s*min\b/i);
  return m ? m[1] + ' минут' : null;
}

async function fetchJson(url) {
  const res = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json' } });
  if (!res.ok) throw new Error('ckvladadivljan ' + url + ': HTTP ' + res.status);
  return res.json();
}

function stripTags(html) {
  return clean(
    String(html)
      .replace(/<br\s*\/?>/gi, ' ')
      .replace(/<\/p>/gi, '\n')
      .replace(/<[^>]+>/g, '')
  ).replace(/\n{2,}/g, '\n').trim();
}

const squeeze = (s) => s.replace(/[ \t]{2,}/g, ' ').trim();

const clean = (s) => decode(String(s || '')).replace(/[ \t]+/g, ' ').trim();

const decode = (s) => String(s)
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;/g, '"')
  .replace(/&#0?39;|&apos;/g, "'")
  .replace(/&laquo;|&raquo;/g, '"')
  .replace(/&#8217;|&rsquo;/g, "'")
  .replace(/&#8220;|&#8221;|&#8222;|&ldquo;|&rdquo;/g, '"')
  .replace(/&#8230;|&hellip;/g, '…')
  .replace(/&ndash;|&#8211;/g, '–')
  .replace(/&mdash;/g, '—');
