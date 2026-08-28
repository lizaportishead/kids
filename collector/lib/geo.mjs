// Координаты площадок — статическая таблица (geocode OpenStreetMap/Nominatim, авг. 2026).
// Коллектор сознательно НЕ ходит в сеть за геокодингом: список площадок меняется
// редко, а сетевой запрос в CI — лишняя точка отказа и риск rate-limit у Nominatim.
// Новую площадку добавляем сюда руками (или правим координаты прямо в public.place).
//
// Ключ — нормализованное имя площадки (см. normName), значение — [lat, lng].
// Значения синхронизированы с таблицей VENUE_GEO во фронтенде (index.html).
const VENUE_GEO = {
  'kinder garden': [44.791847, 20.445722],
  'индиго врачар': [44.801573, 20.476805],
  'sreda kids': [44.81306, 20.464867],
  'индиго новый белград': [44.813808, 20.425282],
  'mathline': [44.830516, 20.455607],
  'enter': [44.807157, 20.464701]
};

// Скобки → пробел, остальные разделители схлопываем: «Индиго (Врачар)» → «индиго врачар».
const normName = (s) =>
  String(s || '')
    .toLowerCase()
    .replace(/[()]/g, ' ')
    .replace(/[^a-zа-яё0-9]+/gi, ' ')
    .trim();

export function geoForPlace(name) {
  return VENUE_GEO[normName(name)] || null;
}

// Проставляет ev.lat/ev.lng по имени площадки. Не трогает события, где координаты
// уже пришли от парсера, и молча пропускает неизвестные площадки.
export function attachGeo(events) {
  for (const ev of events) {
    if (ev.lat != null && ev.lng != null) continue;
    const geo = geoForPlace(ev.place);
    if (geo) {
      ev.lat = geo[0];
      ev.lng = geo[1];
    }
  }
  return events;
}
