// Категория события определяет заглушку-фото (data/images/placeholder-<category>.jpg),
// которая показывается вместо реального фото, если его нет. Список категорий
// жёстко привязан к именам файлов в data/images/.
const RULES = [
  ['school_prep', /подготовка к школ|математик/i],
  ['robotics', /робот|lego/i],
  ['dance', /балет|танц|хореограф/i],
  // Только готовые представления, на которые приходят смотреть — не студии/
  // кружки актёрского мастерства (это другая по сути активность, «театр» в
  // названии студии сюда специально не ловим).
  ['theatre', /спектакл|кукольн\w*\s*(театр|представлен|спектакл)/i],
  ['music', /вокал|музык|фортепиано|пианино|скрипк|гитар/i],
  ['reading', /чита|чтени|рассказ|сторител|storytell|эрудит|топотушк|профориентац|сказк|книжк/i],
  ['languages', /английск|english|язык|серб|немецк|французск|испанск|итальянск|кита[йи]ск|турецк/i],
  ['early_dev', /малыш|тоддлер|toddler|логоритмик|логопед/i],
  ['cooking', /кулинар/i],
  ['art', /живопис|керамик|лепк|скетч|график|пленер|арт[- ]|art[- ]|изостуди|рисова|столярн|деревом|мастерск|глину|глины|глине|рукодел/i],
  ['swimming', /плаван|бассейн|swim/i],
  ['sport', /гимнастик|спорт|дзюдо|карате|самооборон|единоборств|борьб[аеы]|капоэйр/i],
  ['games', /шахмат|настольн\w*\s*игр|d&d|днд/i],
  ['science', /триз|биолог|мнемотехник|ментальная арифметик|умники и умниц|инженерный кружок|опыты и эксперимент/i]
];

// Источники, где вообще все события — одного рода, и по заголовку это не
// понять (например «Пинокио» — кукольный театр, а в заголовках только
// названия сказок). source.id -> категория.
const SOURCE_OVERRIDES = {
  pinokio: 'theatre',
  panteatar: 'theatre',
  bgf: 'theatre'
};

const LABELS = {
  school_prep: 'Подготовка к школе',
  robotics: 'Робототехника',
  theatre: 'Спектакли',
  dance: 'Танцы',
  music: 'Музыка',
  reading: 'Чтение',
  languages: 'Языки',
  early_dev: 'Раннее развитие',
  art: 'Творчество',
  swimming: 'Плаванье',
  sport: 'Спорт',
  games: 'Шахматы и игры',
  science: 'Наука и логика',
  cooking: 'Кулинария'
};

export function categorize(title, sourceId) {
  if (sourceId && SOURCE_OVERRIDES[sourceId]) {
    const category = SOURCE_OVERRIDES[sourceId];
    return { category, categoryLabel: LABELS[category] };
  }
  const t = String(title || '');
  for (const [category, re] of RULES) {
    if (re.test(t)) return { category, categoryLabel: LABELS[category] };
  }
  return { category: null, categoryLabel: null };
}
