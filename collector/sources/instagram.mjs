import { UA } from '../lib/images.mjs';
import { normalize } from '../lib/normalize.mjs';
import { parseDate, parseDuration, parsePrice, parseTime, parseWeekdays, shortFrom, stripHtml, titleFrom } from '../lib/text.mjs';

// Публичный путь без токена: страница /embed/captioned/ отдаёт подпись и превью.
// Если задан IG_OEMBED_TOKEN, сначала пробуем официальный Graph oEmbed.
export async function collectInstagram(source, now = new Date()) {
  const code = (source.url.match(/\/p\/([^/?#]+)/) || [])[1];
  if (!code) return [];

  let caption = null, image = null;

  if (process.env.IG_OEMBED_TOKEN) {
    try {
      const api = 'https://graph.facebook.com/v20.0/instagram_oembed?omitscript=true&url=' +
        encodeURIComponent(source.url) + '&access_token=' + process.env.IG_OEMBED_TOKEN;
      const j = await (await fetch(api)).json();
      if (j && !j.error) { caption = j.title || null; image = j.thumbnail_url || null; }
    } catch { /* падаем в embed */ }
  }

  if (!caption) {
    const res = await fetch('https://www.instagram.com/p/' + code + '/embed/captioned/', {
      headers: { 'user-agent': UA, 'accept-language': 'ru,en;q=0.8' }
    });
    if (!res.ok) throw new Error('instagram ' + code + ': HTTP ' + res.status);
    const html = await res.text();
    const cap = html.match(/class="Caption"[\s\S]*?<\/div>/);
    if (cap) caption = stripHtml(cap[0]).replace(/^\S+\s*/, '');
    if (!caption) {
      const j = html.match(/"edge_media_to_caption".*?"text":"(.*?)"/);
      if (j) caption = JSON.parse('"' + j[1] + '"');
    }
    const img = html.match(/"display_url":"(.*?)"/) || html.match(/<img[^>]+class="EmbeddedMediaImage"[^>]+src="([^"]+)"/);
    if (img) image = JSON.parse('"' + img[1].replace(/"/g, '\\"') + '"').replace(/&amp;/g, '&');
  }

  if (!caption) throw new Error('instagram ' + code + ': подпись недоступна (пост закрыт или разметка изменилась)');

  const text = stripHtml(caption);
  const title = titleFrom(text);
  const raw = {
    title,
    short: shortFrom(text, title),
    desc: text.slice(0, 900),
    date: parseDate(text, now),
    wd: parseWeekdays(text),
    time: parseTime(text),
    dur: parseDuration(text),
    price: parsePrice(text),
    image,
    imageKey: 'ig-' + code
  };
  const ev = normalize(source, raw, now);
  if (!ev) return [];
  ev.imageKey = raw.imageKey;
  ev.imageRemote = image;
  return [ev];
}
