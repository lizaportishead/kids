import { ageLabel, normalize } from '../lib/normalize.mjs';
import { iso, parseDate } from '../lib/text.mjs';

// Детский центр «Crno-bela mačka» (Скадарлия). Сайта и расписания у центра
// нет: на каждые выходные с открытыми занятиями он правит одну и ту же
// гугл-форму предзаписи (ссылка в шапке instagram.com/crnobelamacka_centar).
// Расписание — это сама анкета: вопрос «Какие занятия вы хотели бы посетить
// 3 октября (сб)?» и варианты ответа «10:30 – 11:15 Раннее развитие 2 - 3 года».
//
// Страница формы отдаёт всю анкету JSON-ом в переменной FB_PUBLIC_LOAD_DATA_
// без логина: [1][8] — заголовок, [1][0] — описание, [1][1] — вопросы вида
// [id, заголовок, описание, тип, [[entryId, [[вариант, …], …], …]]].
// Дата берётся из заголовка вопроса (года в ней нет), остальное — из варианта.
const MONTH_RE = /(\d{1,2})\s+(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-яё]*/i;
const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const SLOT_RE = /^\s*(\d{1,2})[:.](\d{2})\s*[–—-]\s*(\d{1,2})[:.](\d{2})\s+(.+?)\s*$/;
// «2 - 3 года», «3.5 - 4.5 года», «4-7 лет» — границы бывают дробными.
const AGE_RE = /(\d{1,2}(?:[.,]\d)?)\s*[–—-]\s*(\d{1,2}(?:[.,]\d)?)\s*(?:лет|года|год)/i;
// «(уровень знаний 3-4 кл)» — у русского языка вместо возраста класс.
const GRADE_RE = /\(?\s*(?:уровень\s+знаний\s+)?(\d{1,2})\s*[–—-]\s*(\d{1,2})\s*кл[а-яё]*\.?\s*\)?/i;

// В названиях занятий центра нет слов, по которым категорию находит общий
// categorize() («Раннее развитие», «Творческая студия»).
const CATEGORY = [
  ['early_dev', 'Раннее развитие', /раннее\s+развити/i],
  ['art', 'Творчество', /творческ/i]
];

export async function collectCrnobelamacka(source, now = new Date()) {
  const form = await fetchForm(source.url);
  const info = (form[1] && form[1][8] || '') + ' ' + (form[1] && form[1][0] || '');
  const open = /открыт/i.test(info);
  // В самой анкете про цену ни слова; «бесплатное пробное занятие по ссылке»
  // написано в шапке инстаграма — поэтому цена задаётся в sources.json.
  const price = /бесплатн/i.test(info) ? 'бесплатно' : source.price || null;
  const today = iso(now);

  const events = [];
  for (const item of (form[1] && form[1][1]) || []) {
    const md = String(item[1] || '').match(MONTH_RE);
    if (!md) continue;
    const date = parseDate(md[0], now);
    if (!date || date < today) continue;
    const dayLabel = Number(md[1]) + ' ' + MONTHS_GEN[Number(date.slice(5, 7)) - 1];

    for (const field of item[4] || []) {
      for (const opt of field[1] || []) {
        const slot = String(opt[0] || '').match(SLOT_RE);
        if (!slot) continue;
        const time = slot[1].padStart(2, '0') + ':' + slot[2];
        const minutes = (Number(slot[3]) * 60 + Number(slot[4])) - (Number(slot[1]) * 60 + Number(slot[2]));
        const who = audienceOf(slot[5]);
        if (!who.name) continue;

        const kind = open ? 'открытое занятие' : 'занятие';
        const raw = {
          title: who.name + (who.label ? ' (' + who.label + ')' : ''),
          short: cap(kind) + (who.forWhom ? ' ' + who.forWhom : '') + ' в детском центре «' + source.place + '», ' + dayLabel + ' в ' + time + '.',
          desc: who.name + ' — ' + kind + (who.forWhom ? ' ' + who.forWhom : '') + ' в детском центре «' + source.place + '». ' +
            cap(dayLabel) + ', ' + time + '–' + slot[3].padStart(2, '0') + ':' + slot[4] + '. ' +
            'Нужна предварительная запись через анкету: мест в группах немного, после заполнения центр свяжется с вами и подтвердит время.',
          date,
          time,
          dur: durOf(minutes),
          age: who.age,
          ageLabel: who.ageText,
          price
        };
        const ev = normalize(source, raw, now);
        if (!ev) continue;
        if (!ev.category) {
          const hit = CATEGORY.find(([, , re]) => re.test(who.name));
          if (hit) { ev.category = hit[0]; ev.categoryLabel = hit[1]; }
        }
        events.push(ev);
      }
    }
  }
  return events;
}

// «Раннее развитие 3.5 - 4.5 года» → название + возраст; «Русский язык,
// "продолжающие" (уровень знаний 3-4 кл)» → название + класс (возраст по
// классу оценочный: 1 класс — 7 лет).
function audienceOf(text) {
  const t = String(text).replace(/\s+/g, ' ').trim();
  let m = t.match(AGE_RE);
  if (m) {
    const a = m[1].replace('.', ','), b = m[2].replace('.', ',');
    const age = [Math.floor(parseFloat(m[1].replace(',', '.'))), Math.floor(parseFloat(m[2].replace(',', '.')))];
    // «3,5–4,5 года» — подпись сохраняет дробные границы, которых нет в age.
    const ageText = a + '–' + b + ' ' + (age[1] < 5 ? 'года' : 'лет');
    return { name: nameOf(t.replace(m[0], '')), age, ageText, label: ageText, forWhom: 'для детей ' + a + '–' + b + ' лет' };
  }
  m = t.match(GRADE_RE);
  if (m) {
    const age = [Number(m[1]) + 6, Number(m[2]) + 7];
    const grades = m[1] + '–' + m[2] + ' класса';
    return { name: nameOf(t.replace(m[0], '')), age, ageText: ageLabel(age), label: 'уровень ' + grades, forWhom: 'для детей с уровнем знаний ' + grades };
  }
  return { name: nameOf(t), age: null, ageText: null, label: '', forWhom: '' };
}

// Прямые кавычки → «ёлочки», хвостовые знаки и пустые скобки — долой.
function nameOf(s) {
  return String(s)
    .replace(/"([^"]+)"/g, '«$1»')
    .replace(/\(\s*\)/g, '')
    .replace(/\s+/g, ' ')
    .replace(/[\s,;:.–—-]+$/, '')
    .trim();
}

function durOf(minutes) {
  if (!(minutes > 0)) return null;
  if (minutes % 60 === 0) return minutes === 60 ? '1 час' : minutes / 60 + ' часа';
  return minutes + ' минут';
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// Браузерный user-agent здесь вреден: короткой ссылке forms.gle гугл отвечает
// на него страницей-прокладкой «открыть в приложении» вместо редиректа на форму.
async function fetchForm(url) {
  const res = await fetch(url, { headers: { 'accept-language': 'ru,en;q=0.8' }, signal: AbortSignal.timeout(30000) });
  if (!res.ok) throw new Error('crnobelamacka ' + url + ': HTTP ' + res.status);
  const html = await res.text();
  const m = html.match(/FB_PUBLIC_LOAD_DATA_\s*=\s*([\s\S]*?);\s*<\/script>/);
  if (!m) throw new Error('crnobelamacka: анкета недоступна (форму закрыли или заменили новой — проверьте ссылку в шапке инстаграма)');
  return JSON.parse(m[1]);
}
