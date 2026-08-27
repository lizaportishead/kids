// Категория события определяет заглушку-фото (data/images/placeholder-<category>.jpg),
// которая показывается вместо реального фото, если его нет. Список категорий
// жёстко привязан к именам файлов в data/images/.
const RULES = [
  ['school_prep', /подготовка к школ|математик/i],
  ['robotics', /робот|lego/i],
  ['dance', /балет|танц|хореограф/i],
  ['music', /вокал|музык/i],
  ['reading', /чита|чтени|рассказ|сторител|storytell/i],
  ['languages', /английск|english|язык/i],
  ['early_dev', /малыш|тоддлер|toddler|логоритмик/i],
  ['art', /живопис|керамик|лепк|скетч|график|пленер|арт[- ]|art[- ]|изостуди|рисова|столярн|деревом|мастерск|глину|глины|глине/i],
  ['sport', /гимнастик|спорт/i]
];

const LABELS = {
  school_prep: 'Подготовка к школе',
  robotics: 'Робототехника',
  dance: 'Танцы',
  music: 'Музыка',
  reading: 'Чтение',
  languages: 'Языки',
  early_dev: 'Раннее развитие',
  art: 'Творчество',
  sport: 'Спорт'
};

export function categorize(title) {
  const t = String(title || '');
  for (const [category, re] of RULES) {
    if (re.test(t)) return { category, categoryLabel: LABELS[category] };
  }
  return { category: null, categoryLabel: null };
}
