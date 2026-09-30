#!/usr/bin/env python3
"""Генерирует страницы сайта с готовым текстом из data/events.json.

Приложение (index.html) одно на весь сайт, но у каждого раздела свой адрес.
Под каждый адрес здесь собирается HTML-страница: заголовок, описание и текст
для поиска, а поверх — загрузка приложения (страница скачивает /index.html и
подменяет им себя, приложение само открывает нужный раздел по адресу):

  venues/               — «Площадки»
  schedule/             — «Расписание»: регулярные занятия
  events/all/           — все ближайшие события
  favs/                 — «Избранное» (не индексируется)
  <venue>/              — площадка: адрес, расписание, ближайшие события
  <venue>/<event>/      — одно занятие или событие (без даты в адресе)
  category/<cat>/       — занятия одной категории (посадочная страница без
                          приложения: такого раздела в приложении нет)
  blog/                 — «Блог»: все посадочные страницы карточками-статьями
  blog/<slug>/          — авторские статьи из articles/<slug>.html (+ articles/articles.json)
  kruzhki/<район>/      — кружки в районе (DISTRICT_PAGES), kruzhki/malyshi/ —
                          занятия для малышей; тоже посадочные без приложения
  404.html              — всё остальное (например, /event/<id>/ для событий,
                          появившихся после сборки) тоже открывает приложение

Slug'и адресов пишутся в data/routes.json — по ним приложение строит ссылки.
Также перезаписывается sitemap.xml. Каталоги площадок перечислены в
static-pages.txt; venues/, category/ и всё из этого списка принадлежат
скрипту и пересоздаются целиком — руками их не править.
Запускается ежедневно в .github/workflows/collect.yml после сборки афиши.
"""
import html
import json
import re
import shutil
from collections import Counter
from urllib.parse import quote
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://klubok.kids"
OWNED_DIRS = ("venues", "category", "kruzhki", "blog", "events", "schedule", "favs")
MANIFEST = ROOT / "static-pages.txt"
# Каталоги в корне сайта, которые нельзя занимать под slug площадки.
RESERVED = {"en", "sr", "data", "docs", "db", "collector", "scripts", "supabase", "scratch",
            "venues", "category", "events", "assets", "kids", "api", "static",
            "schedule", "favs", "afisha", "event", "venue", "kruzhki", "blog", "articles"}

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS_DAT = ["понедельникам", "вторникам", "средам", "четвергам",
                "пятницам", "субботам", "воскресеньям"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]

TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", [
    "a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
    "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))

CSS = """
:root{--ink:#201e1d;--muted:#6d6357;--line:#e8dfc9;--chip:#f3f0ea;--orange:#ff6032}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font:16px/1.55 Figtree,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.site{display:flex;align-items:center;gap:12px;min-height:72px;padding:14px 28px;background:radial-gradient(1270px 1257px at 4.04% 6.11%,rgba(197,250,139,.6) 0%,rgba(237,241,243,.6) 50%,rgba(255,243,186,.6) 100%),#fff}
.brand{display:flex;align-items:center;gap:12px;flex:1 1 auto;min-width:0;text-decoration:none}
.brand img{height:52px;width:auto;display:block;margin-top:-6px}
.brand span{font-size:12px;line-height:15px;color:var(--muted);margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav{display:flex;gap:8px;align-items:center}
.nav a{padding:8px 14px;border-radius:999px;text-decoration:none;font-size:16px;font-weight:600;color:#4f483f}
.nav a.on{color:var(--ink)}
.nav a.add{background:var(--orange);color:#fff;padding:10px 20px;font-weight:700}
.page{max-width:720px;margin:0 auto;padding:28px 20px 56px}
.page.wide{max-width:1120px}
.back{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;padding:10px 18px;text-decoration:none;font-weight:500;margin-bottom:24px;background:#fff}
h1{font-size:32px;line-height:1.15;margin:0;font-weight:800;letter-spacing:-.3px;text-wrap:balance}
h2{font-size:22px;line-height:1.2;margin:36px 0 14px;font-weight:700}
.lead{color:var(--muted);margin:8px 0 24px}
.vcard{background:#fff;border-radius:24px;padding:28px;box-shadow:0 8px 30px rgba(32,30,29,.08);border:1px solid #f0ebe0}
.vhead{display:flex;align-items:center;gap:16px;margin-bottom:22px}
.logo{width:64px;height:64px;border-radius:16px;object-fit:cover;border:1px solid #eee6d6;flex:none;background:#fff}
.logo.mono{display:flex;align-items:center;justify-content:center;background:var(--chip);color:var(--muted);font-weight:800;font-size:26px}
.logo.sm{width:48px;height:48px;border-radius:12px;font-size:20px}
.lab{font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#8a8175;font-weight:600;margin:0 0 6px}
.addr{display:flex;gap:8px;align-items:flex-start;font-weight:600;margin:0 0 16px}
.addr svg{flex:none;margin-top:4px}
.pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.addr+.pill{margin-bottom:2px}
.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;padding:9px 16px;font-size:14px;font-weight:500;text-decoration:none;background:#fff}
.btn{display:block;text-align:center;background:var(--orange);color:#fff;text-decoration:none;font-weight:700;font-size:17px;padding:15px 20px;border-radius:999px;margin-top:16px}
.btn.alt{background:#fff;color:var(--ink);border:1px solid var(--line);font-weight:600;font-size:15px;padding:12px 20px;margin-top:10px}
.cards{display:grid;gap:12px;margin:0;padding:0;list-style:none}
.ecard{display:flex;gap:14px;align-items:center;background:#fff;border:1px solid #f0ebe0;border-radius:18px;padding:14px 16px;text-decoration:none;box-shadow:0 2px 10px rgba(32,30,29,.04)}
.ecard:hover{box-shadow:0 6px 20px rgba(32,30,29,.09)}
.ecard .thumb{width:64px;height:64px;border-radius:14px;object-fit:cover;flex:none}
.ecard .t{font-weight:700;font-size:17px;line-height:1.25}
.ecard .s{color:var(--muted);font-size:14px;margin-top:3px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0}
.chip{background:var(--chip);border-radius:999px;padding:7px 14px;font-size:14px;font-weight:600;text-decoration:none}
.detail{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:48px;align-items:start}
.detail h1{font-size:44px;line-height:1.1;letter-spacing:-.5px}
.when{font-size:26px;line-height:1.2;font-weight:800;color:var(--orange);margin:18px 0 0}
.desc{font-size:18px;line-height:1.6;margin-top:28px}.desc p{margin:0 0 16px}
.dur{font-size:18px;margin:0 0 4px}
.rule{border:0;border-top:1px solid #eee6d6;margin:28px 0}
.vrow{display:flex;gap:14px;align-items:center;text-decoration:none;padding:6px 0}
.vrow b{font-size:20px;font-weight:700}.vrow .a{color:var(--muted)}
.hero{width:100%;border-radius:24px;display:block;aspect-ratio:7/5;object-fit:cover;margin-bottom:16px}
.pricecard{border:1px solid #eee6d6;border-radius:24px;padding:22px;box-shadow:0 8px 30px rgba(32,30,29,.06)}
.price{font-size:26px;font-weight:800;line-height:1.2}.price.long{font-size:17px;font-weight:600}
.note{color:var(--muted);font-size:13px;text-align:center;margin-top:14px}
.vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin:0;padding:0;list-style:none}
.intro{font-size:17px;line-height:1.6;margin:14px 0 0}.intro p{margin:0 0 12px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 4px}.stats span{background:#fff4d6;border-radius:999px;padding:6px 14px;font-size:14px;font-weight:600}
.faq{margin:0;padding:0}.faq dt{font-weight:700;margin:18px 0 4px}.faq dd{margin:0;color:#3d3833}
.lead a,.intro a,.faq a{text-decoration:underline}
.clist{list-style:none;margin:0;padding:0;border-top:1px solid #f0ebe0}
.clist li{border-bottom:1px solid #f0ebe0}
.clist a{display:flex;gap:4px 16px;align-items:center;padding:10px 2px;text-decoration:none}
.clist a>div{flex:1 1 auto;min-width:0}
.clist .lg{width:36px;height:36px;border-radius:10px;font-size:15px;flex:none;align-self:center;object-fit:contain;padding:2px}
.clist a:hover .t{text-decoration:underline}
.clist .t{font-weight:600;font-size:16px;line-height:1.3}.clist .p{color:var(--muted);font-size:14px;margin-top:2px}
.clist .ag{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.clist .ag span{background:var(--chip);border-radius:10px;padding:4px 10px;font-size:13px;white-space:nowrap}.clist .ag b{font-weight:600;color:var(--muted);margin-right:2px}
.clist .w{flex:none;text-align:right;font-size:14px;font-weight:600;white-space:nowrap}
details.more summary{cursor:pointer;list-style:none;display:inline-block;margin-top:10px;font-weight:600;font-size:15px;color:var(--orange)}
details.more summary::-webkit-details-marker{display:none}details.more[open] summary{display:none}
.vgrid.sm{grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px}.vgrid.sm .ecard{padding:10px 12px}.vgrid.sm .t{font-size:15px}.vgrid.sm img.logo{object-fit:contain;padding:3px}.vgrid.sm .s{font-size:13px}
@media(max-width:640px){.clist a{flex-wrap:wrap;align-items:flex-start}.clist a>div{flex-basis:calc(100% - 52px)}.clist .w{flex-basis:100%;padding-left:52px;text-align:left;color:var(--orange);white-space:normal}}
.cover{margin:0 0 24px}.cover img{width:100%;aspect-ratio:36/13;object-fit:cover;border-radius:24px;display:block;background:var(--chip)}
.cover figcaption{font-size:12px;color:var(--muted);margin-top:6px;text-align:right}.cover a{color:inherit}
@media(max-width:760px){.cover img{aspect-ratio:2/1;border-radius:18px}}
.article{max-width:720px;margin:0 auto}.article h1{font-size:40px;line-height:1.1}
.article .meta{color:var(--muted);font-size:14px;margin:10px 0 0}
.article .lead{font-size:19px;color:#3d3833;margin:18px 0 22px}
.article p,.article li{font-size:17px;line-height:1.65}.article h2{font-size:26px;margin:40px 0 12px;scroll-margin-top:16px}
.article a{text-decoration:underline}.article ul,.article ol{padding-left:22px}.article li{margin:6px 0}
.toc{display:flex;flex-direction:column;gap:6px;background:var(--chip);border-radius:18px;padding:18px 22px;margin:0 0 20px}
.toc b{font-size:13px;letter-spacing:1px;text-transform:uppercase;color:#8a8175}.toc a{text-decoration:none;font-weight:600}
.note-box{border-left:4px solid var(--orange);background:#fff7f2;border-radius:0 14px 14px 0;padding:14px 18px;font-size:15px;line-height:1.55;margin:0 0 8px}
ol.check{list-style:none;padding:0;counter-reset:c}ol.check li{counter-increment:c;position:relative;padding-left:40px}
ol.check li::before{content:counter(c);position:absolute;left:0;top:1px;width:26px;height:26px;border-radius:50%;background:var(--orange);color:#fff;font-weight:700;font-size:14px;display:flex;align-items:center;justify-content:center}
@media(max-width:640px){.article h1{font-size:30px}.article h2{font-size:22px}}
.bsec{font-size:13px;letter-spacing:1.2px;text-transform:uppercase;color:#8a8175;font-weight:700;margin:40px 0 14px}
.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px;margin:0;padding:0;list-style:none}
.post{display:flex;flex-direction:column;height:100%;background:#fff;border:1px solid #f0ebe0;border-radius:22px;overflow:hidden;text-decoration:none;box-shadow:0 2px 10px rgba(32,30,29,.04);transition:box-shadow .15s}
.post:hover{box-shadow:0 10px 30px rgba(32,30,29,.1)}
.post img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;background:var(--chip)}
.post .pb{padding:16px 18px 18px;display:flex;flex-direction:column;gap:8px;flex:1}
.post .tag{align-self:flex-start;background:var(--chip);border-radius:999px;padding:3px 10px;font-size:12px;font-weight:700;color:#4f483f}
.post h3{margin:0;font-size:19px;line-height:1.25;font-weight:800}
.post p{margin:0;color:#4f483f;font-size:15px;line-height:1.5}
.post .meta{margin-top:auto;padding-top:6px;color:var(--muted);font-size:13px}
.post.big{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr)}.post.big img{height:100%;aspect-ratio:auto;min-height:260px}
.post.big h3{font-size:28px}.post.big .pb{padding:28px;justify-content:center}.post.big p{font-size:16px}
@media(max-width:760px){.post.big{display:flex}.post.big img{aspect-ratio:16/9;min-height:0}.post.big h3{font-size:22px}.post.big .pb{padding:16px 18px 18px}}
.foot{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:14px 24px;margin-top:24px;padding:22px 28px 16px;background:radial-gradient(1270px 1257px at 4.04% 6.11%,rgba(197,250,139,.6) 0%,rgba(237,241,243,.6) 50%,rgba(255,243,186,.6) 100%),#fff;border-top:1px solid #ebe0ca;font-size:13px;line-height:20px;color:#6d6357}
.foot .fl{display:flex;flex-direction:column;gap:6px;min-width:0}.foot .fa{display:flex;gap:16px}.foot .fa a{font-weight:500;text-decoration:underline;text-underline-offset:2px;padding:2px 0}
.friend{display:flex;align-items:center;gap:10px;padding:6px 14px 6px 6px;border-radius:8px;background:#fff;border:1px solid #ebe0ca;text-decoration:none}
.friend img{width:36px;height:36px;border-radius:6px;object-fit:cover;display:block}.friend span{display:flex;flex-direction:column;gap:1px}
.friend small{font-size:12px;font-weight:500;color:#9a8d79}.friend b{font-size:13px;font-weight:600;color:#35312c}
@media(max-width:900px){.detail{grid-template-columns:1fr;gap:28px}.detail h1{font-size:34px}}
.boot{display:none}
.booting .boot{display:flex;position:fixed;inset:0;z-index:9999;align-items:center;justify-content:center;background:#fffdf7}
.boot div{width:96px;height:96px;animation:bob 1.9s cubic-bezier(.45,0,.55,1) infinite}
.boot img{width:100%;height:100%;display:block;animation:spin 1.9s cubic-bezier(.65,0,.35,1) infinite}
@keyframes spin{to{transform:rotate(360deg)}}@keyframes bob{50%{transform:translateY(-12px)}}
@media(prefers-reduced-motion:reduce){.boot div,.boot img{animation:none}}
@media(max-width:640px){.site{padding:12px 16px}.brand span{display:none}.brand img{height:44px}.nav a{padding:8px 10px;font-size:15px}.nav a.add{display:none}h1{font-size:28px}.vcard{padding:20px}}
"""


def slugify(text):
    out = "".join(TRANSLIT.get(ch, ch) for ch in text.lower())
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return out or "place"


def esc(s):
    return html.escape(str(s), quote=True)


def today_belgrade():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Belgrade")).date()
    except Exception:
        return (datetime.now(timezone.utc) + timedelta(hours=2)).date()


_t = today_belgrade()
BUILT = f"{_t.day} {MONTHS[_t.month - 1]}"   # «Расписание обновлено …» в подвале


def fmt_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def when(e):
    """Человекочитаемое «когда» для строки события."""
    t = f" в {e['time']}" if e.get("time") else ""
    if e.get("date"):
        return fmt_date(e["date"]) + t
    wd = e.get("wd") or []
    if wd:
        if len(wd) == 7:
            return "ежедневно" + t
        names = [WEEKDAYS_DAT[i] for i in wd]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " и " + names[-1]
        return "по " + joined + t
    return t.strip()


def first_sentence(text, limit=150):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:—- ") + "…"


def plain(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def paragraphs(text):
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join("<p>" + esc(p).replace("\n", "<br>") + "</p>" for p in parts)


# --- данные приложения, которые хранятся прямо в index.html ---
def _app_source():
    t = (ROOT / "index.html").read_text(encoding="utf-8")
    return t.replace("\\n", "\n").replace('\\"', '"')


def _js_block(src, name):
    i = src.find(f"const {name} = {{")
    if i < 0:
        return ""
    return src[i:src.find("\n};", i)]


APP = _app_source()
VENUE_LOGO = dict(re.findall(r'"([^"\n]+)":\s*"(data/images/venue-[^"\n]+)"', _js_block(APP, "VENUE_LOGO")))
# Не детские площадки (ТЦ, арены, организаторы квестов): нет в списке /venues/.
_h = APP.find("const VENUE_HIDDEN = new Set([")
VENUE_HIDDEN = set(re.findall(r'^\s*"([^"\n]+)"', APP[_h:APP.find("]);", _h)], re.M)) if _h >= 0 else set()
VENUE_CONTACTS = {}
for _m in re.finditer(r'^\s*"([^"\n]+)":\s*\{([^}\n]*)\}', _js_block(APP, "VENUE_CONTACTS"), re.M):
    VENUE_CONTACTS[_m.group(1)] = dict(re.findall(r'(\w+):\s*"([^"]*)"', _m.group(2)))

# Поисковые заголовки категорий: slug -> (h1, «что это» для вступления, запросы для description)
CAT_SEO = {
    "art": ("Творческие студии и кружки для детей в Белграде", "рисование, лепка, рукоделие и мастер-классы", "рисование, лепка, творческие мастер-классы"),
    "languages": ("Иностранные языки для детей в Белграде", "курсы и кружки иностранных языков", "английский, сербский, языковые кружки"),
    "reading": ("Чтение и книжные занятия для детей в Белграде", "книжные встречи и занятия по чтению", "книжный клуб, чтение, литература"),
    "swimming": ("Плавание для детей в Белграде: бассейны и школы плавания", "занятия плаванием для малышей и школьников", "бассейн, школа плавания, плавание для малышей"),
    "early_dev": ("Раннее развитие: занятия для малышей в Белграде", "занятия для детей от года вместе с мамой и без", "занятия для малышей, монтессори, развитие с мамой"),
    "dance": ("Танцы для детей в Белграде: балет, хореография, современный танец", "танцы, балет, хореография и ритмика", "танцы для детей, балет, хореография"),
    "music": ("Музыка для детей в Белграде: студии и занятия", "музыкальные занятия и логоритмика", "музыкальные занятия, вокал, музыкальная студия"),
    "games": ("Шахматы и настольные игры для детей в Белграде", "шахматные секции, клубы настольных игр", "шахматы для детей, клуб настольных игр"),
    "school_prep": ("Подготовка к школе в Белграде: занятия для дошкольников", "подготовка к школе и занятия для дошкольников", "подготовка к школе, занятия для дошкольников"),
    "theatre": ("Детские театры в Белграде: афиша спектаклей для детей", "спектакли и представления для детей", "детский театр, спектакли, кукольный театр"),
    "sport": ("Спортивные секции для детей в Белграде", "спортивные секции и активные занятия", "спортивные секции, детский спорт, ролики"),
    "science": ("Наука и логика для детей в Белграде: математика и эксперименты", "математические кружки, логика и наука", "математический кружок, логика, наука для детей"),
    "robotics": ("Робототехника и программирование для детей в Белграде", "конструирование, робототехника и программирование", "робототехника, программирование для детей"),
    "cooking": ("Кулинарные мастер-классы для детей в Белграде", "детская кулинария и мастер-классы", "кулинарные мастер-классы для детей"),
}

# Вступительный текст посадочных страниц категорий (абзацы). Цифры и списки
# площадок подставляются из афиши, здесь — то, чего в данных нет.
CAT_INTRO = {
    "art": [
        "Творческие занятия — это рисование, живопись, лепка из глины, керамика, рукоделие, скетчинг и даже "
        "мультипликация. Для малышей это прежде всего сенсорный опыт и свобода, для школьников — техника, "
        "композиция и собственные проекты. Группы небольшие, есть занятия с полутора лет вместе с мамой.",
    ],
    "languages": [
        "Английский, сербский, китайский и другие языки: игровые группы для дошкольников, курсы и разговорные "
        "клубы для школьников. Детям, которые недавно переехали, особенно помогают занятия сербским — так проще "
        "в садике и школе. Малышам обычно подходит игровой формат, с 7–8 лет — занятия по учебнику и разговорные клубы.",
    ],
    "reading": [
        "Книжные клубы, чтение вслух для малышей, литературные кружки и занятия по развитию речи. Здесь дети "
        "учатся любить книгу и обсуждать прочитанное, а заодно поддерживают русский язык, если растут в сербской среде.",
    ],
    "swimming": [
        "Школы плавания работают в бассейнах разных районов Белграда: есть группы для дошкольников — игровые, "
        "на мелкой воде, — и секции для школьников с постановкой стилей. Тренировки обычно проходят два раза "
        "в неделю, группы делят по уровню: начинающие и продолжающие.",
    ],
    "music": [
        "Вокал, хор, фортепиано, музыкальные лаборатории и логоритмика. Малыши знакомятся с ритмом и мелодией "
        "через игру, дети постарше занимаются вокалом или инструментом и готовятся к выступлениям. Группы обычно "
        "делят по возрасту, так что занятие найдётся и для трёхлетки, и для подростка.",
    ],
    "games": [
        "Шахматы, настольные игры и ролевые клубы вроде «Подземелий и драконов». Такие занятия развивают логику, "
        "умение планировать и спокойно проигрывать — и это отличный способ найти друзей. В шахматы обычно "
        "начинают играть с 5–6 лет.",
    ],
    "school_prep": [
        "Занятия для дошкольников 5–7 лет: чтение, письмо, счёт, логика и привычка работать в группе. В Сербии "
        "за год до школы обязательна подготовительная программа в садике или школе («припремни предшколски "
        "програм»); кружки её дополняют, но не заменяют.",
    ],
    "sport": [
        "Гимнастика, футбол, капоэйра, скалолазание, ролики и другие активные секции. Малышам дают общую "
        "физическую подготовку и подвижные игры, детям постарше — технику выбранного вида спорта. Перед записью "
        "спросите о пробном занятии.",
    ],
    "science": [
        "Математические кружки, опыты и эксперименты, ТРИЗ, ментальная арифметика и 3D-моделирование. Здесь "
        "дети учатся задавать вопросы, рассуждать и решать нестандартные задачи — хорошее дополнение к школьной "
        "программе. Бывают и научные экскурсии, например в Музей Николы Теслы.",
    ],
    "robotics": [
        "Конструирование на LEGO WeDo и SPIKE, робототехника на Mindstorms, программирование в Scratch, "
        "Minecraft и Roblox. Малыши с 3–5 лет собирают простые движущиеся модели, школьники программируют роботов "
        "и создают свои игры. Группы делят по возрасту и уровню подготовки.",
    ],
    "cooking": [
        "Кулинарные мастер-классы, где дети сами готовят простые блюда: учатся обращаться с продуктами, "
        "следовать рецепту и работать в команде. Такие занятия чаще проходят разово — удобно записаться на выходные.",
    ],
    "dance": [
        "Танцы — одно из самых популярных направлений для детей в Белграде: в студиях есть группы "
        "от двух лет (хореография вместе с мамой) до школьников. Малышам обычно предлагают ритмику "
        "и игровую хореографию, с пяти-шести лет — классический балет и современный танец.",
        "Большинство занятий проходит по будням после 17:00, группы маленькие, а первое занятие "
        "во многих студиях можно посетить разово, без абонемента.",
    ],
    "theatre": [
        "В Белграде много театров для детей: кукольные театры, детские сцены больших театров и "
        "семейные концерты филармонии. Спектакли идут в основном по выходным, в полдень и ранним вечером, "
        "часть — на сербском языке, часть — без слов или с музыкой, так что их можно смотреть "
        "и без знания языка.",
        "Ниже — театры с ближайшими спектаклями и полная афиша по датам. Возраст указан по "
        "рекомендации театра; билеты обычно продаются в кассе и на сайте театра.",
    ],
    "early_dev": [
        "Занятия раннего развития — для детей примерно от года до трёх-четырёх лет, часто вместе "
        "с мамой или папой: сенсорика, пальчиковые игры, музыка, первые навыки общения в группе. "
        "Все занятия для самых маленьких, включая музыку, танцы и плавание, собраны на странице "
        "«Занятия для малышей».",
    ],
}

# Районы, у которых есть своя посадочная страница /kruzhki/<slug>/:
# slug -> (название, в каком районе (предложный), какие районы из адресов входят, вступление)
DISTRICT_PAGES = {
    "vracar": ("Врачар", "на Врачаре", ["Врачар"], [
        "Врачар — небольшой и очень плотный центральный район Белграда вокруг Храма Святого Саввы, "
        "Каленич-рынка и Црвеног крста. Здесь много семей, и детских студий на Врачаре, пожалуй, "
        "больше, чем где-либо в городе: робототехника, языки, творчество, шахматы, танцы, музыка и плавание.",
        "Почти все площадки — в пешей доступности друг от друга, так что кружки удобно совмещать: "
        "например, робототехнику и английский в один день.",
    ]),
    "stari-grad": ("Старый Град", "в Старом Граде", ["Старый Град", "Дорчол"], [
        "Старый Град — исторический центр Белграда: Дорчол, Калемегдан, Кнез Михаила, Студентский трг. "
        "Здесь работают детские центры с языками, подготовкой к школе и занятиями для "
        "малышей, а также большие театры и филармония с детскими программами.",
        "На этой странице — постоянные кружки в Старом Граде и на Дорчоле и ближайшие детские "
        "события в районе.",
    ]),
    "novi-beograd": ("Новый Белград", "в Новом Белграде", ["Новый Белград"], [
        "Новый Белград — большой семейный район за Савой с кварталами-блоками, Белвилем и Ушче. "
        "Детские центры здесь обычно расположены прямо в жилых блоках: робототехника и программирование, "
        "шахматы, языки, творческие студии, хореография и музыка.",
        "Здесь же — кукольный театр «Пинокио», где каждую неделю идут спектакли для малышей и "
        "дошкольников.",
    ]),
    "savski-venac": ("Савски венац", "на Савском венце", ["Савски венац"], [
        "Савски венац — район вдоль Савы: Сеньяк, Дедине, Топчидер, Савамала и новый квартал «Белград на воде». "
        "Много зелени и парков, а детские места здесь скорее для выходных, чем на каждый день.",
        "В районе — скалодром Pulse на Сеньяке с детскими тренировками, Музей африканского искусства с "
        "мастерскими для детей, детский театр «Змай» и книжный Bela Vrana с субботними занятиями.",
    ]),
    "palilula": ("Палилула", "на Палилуле", ["Палилула"], [
        "Палилула — большой район к востоку от центра: Ташмайдан с парком и церковью Святого Марка, "
        "Карабурма, Котеж и Борча за Дунаем.",
        "У Ташмайдана работает Малое позориште «Душко Радовић» — один из главных детских театров города. "
        "Рядом — детские клубы, книжные с занятиями, плавание и танцы.",
    ]),
    "vozdovac": ("Вождовац", "на Вождоваце", ["Вождовац"], [
        "Вождовац — зелёный район на юге Белграда: Баница, Шумице, Йайинци, а дальше — гора Авала "
        "с телебашней, куда удобно выбраться с детьми на выходные.",
        "Здесь спортивный центр «Шумице» с детскими программами и школа плавания SwimYou.",
    ]),
    "zvezdara": ("Звездара", "на Звездаре", ["Звездара"], [
        "Звездара — район на холме к востоку от центра, названный в честь обсерватории. Звездарский лес — "
        "одно из любимых мест Белграда для прогулок с детьми.",
        "В районе — «Пан театар» с детской сценой, где по выходным идут спектакли, и роллердром RollerLand.",
    ]),
}
# Площадки, у которых в адресе не указан район (подсказка для district_of).
VENUE_DISTRICT = {"Karavela": "Палилула", "Продлёнка": "Палилула", "Hobbit House": "Палилула",
                  "Мало позориште «Душко Радовић»": "Палилула", "Театр «Пуж»": "Врачар",
                  "Bela Vrana": "Савски венац"}
# Обложки районов в «Блоге» — фото реальных занятий (если файл пропал — берётся картинка из афиши).
DISTRICT_COVER = {"vracar": "data/images/nashemesto-lego.png",
                  "stari-grad": "data/images/lumos-teatr.jpg",
                  "novi-beograd": "data/images/nashemesto-3d-modelirovanie.jpg"}
DISTRICT_KEYWORDS = ["Врачар", "Дорчол", "Стари Град", "Старый Град", "Нови Београд", "Новый Белград", "Земун",
                     "Звездара", "Вождовац", "Чукарица", "Раковица", "Палилула", "Савски венац"]
DISTRICT_ALIASES = {"Стари Град": "Старый Град", "Нови Београд": "Новый Белград"}
# Слаги районов в фильтре приложения (?district=…)
DISTRICT_SLUGS = {"Врачар": "vracar", "Дорчол": "dorcol", "Старый Град": "stari-grad", "Новый Белград": "novi-beograd",
                  "Савски венац": "savski-venac", "Палилула": "palilula", "Вождовац": "vozdovac", "Звездара": "zvezdara"}


def district_of(e):
    """Район по адресу — так же, как в приложении (districtOf), но без учёта регистра."""
    if e.get("place") in VENUE_DISTRICT:
        return VENUE_DISTRICT[e["place"]]
    text = ", ".join(x for x in (e.get("address"), e.get("place")) if x).lower()
    for kw in DISTRICT_KEYWORDS:
        if kw.lower() in text:
            return DISTRICT_ALIASES.get(kw, kw)
    return "Другое"


MALYSHI_INTRO = [
    "Для самых маленьких в Белграде есть не только занятия раннего развития: малышей берут "
    "в группы хореографии, музыки, плавания, творчества и английского, многие — вместе с мамой "
    "или папой. Здесь собраны все постоянные занятия, куда можно прийти с ребёнком до четырёх лет.",
    "Есть и утренние группы — для тех, кто ещё не ходит в садик, — и вечерние, после 17:00. "
    "Ниже занятия разбиты по направлениям, а в конце страницы — ближайшие спектакли и события, "
    "куда можно прийти с ребёнком до четырёх лет.",
]

# Обложки статей с Unsplash (подключаются прямой ссылкой, как требуют правила
# Unsplash, с подписью автора): ключ -> (id фото, автор, username)
HERO = {
    "vracar": ("photo-1630610857799-36b59ff3412e", "Ben Asyö", "benasyo"),
    "stari-grad": ("photo-1632342966904-55e19bed82bf", "Dimitrije Milenkovic", "dimitrije_milenkovic"),
    "palilula": ("photo-1717572494480-ebaf5648f60c", "Suraj Tomer", "meditative"),
    "savski-venac": ("photo-1708253832369-ce7e621df31a", "Anton Lukin", "antonlukin"),
    "vozdovac": ("photo-1740701943103-8b29488de9a0", "Nikola Kojević", "nikolaskojevic"),
    "zvezdara": ("photo-1730205616254-a594de42cd3e", "Tanja Tepavac", "ttepavac"),
    "novi-beograd": ("photo-1686687997696-1afe8c95ed40", "Daniela Legotta", "comodinodimarmo"),
    "malyshi": ("photo-1515488042361-ee00e0ddd4e4", "Yuri Li", "itshoobastank"),
    "blog": ("photo-1606092195730-5d7b9af1efc5", "Artem Kniaz", "artem_kniaz"),
    "art": ("photo-1560421683-6856ea585c78", "Dragos Gontariu", "dragos126"),
    "cooking": ("photo-1615224299941-04a854c101d4", "Brooke Lark", "brookelark"),
    "dance": ("photo-1508807526345-15e9b5f4eaff", "Michael Afonso", "mafonso"),
    "early_dev": ("photo-1609811645795-f72ea07f47e9", "Jackie Hope", "jackieboylhart"),
    "games": ("photo-1714646793130-0dc0c5a04f64", "Vitaly Gariev", "silverkblack"),
    "languages": ("photo-1577896851231-70ef18881754", "National Cancer Institute", "nci"),
    "music": ("photo-1504484656217-38f8ffc617f9", "Jelleke Vanooteghem", "ilumire"),
    "reading": ("photo-1516042438821-0abd7a73c4b3", "Johnny McClung", "johnnymcclung"),
    "robotics": ("photo-1643199329419-1e46bbacf76c", "RUT MIIT", "rutmiit"),
    "school_prep": ("photo-1587323655395-b1c77a12c89a", "Gabe Pierce", "gaberce"),
    "science": ("photo-1613271752699-ede48a285196", "Clint Patterson", "cbpsc1"),
    "sport": ("photo-1609422644211-a85c36ee36a7", "Debra Brewster", "dbrewster66"),
    "swimming": ("photo-1627540458907-47a427507e20", "piratedea", "piratedea"),
    "theatre": ("photo-1432639020363-5632f7f04e0b", "Sagar Dani", "sagardani"),
}
UNSPLASH_UTM = "?utm_source=klubok&utm_medium=referral"


# Авторские статьи блога: текст — articles/<slug>.html, заголовки и обложка — articles/articles.json
ARTICLES = json.loads((ROOT / "articles" / "articles.json").read_text(encoding="utf-8")) \
    if (ROOT / "articles" / "articles.json").exists() else []
for _a in ARTICLES:
    HERO[_a["slug"]] = tuple(_a["hero"])


def hero_url(key, w, h):
    return f"https://images.unsplash.com/{HERO[key][0]}?w={w}&h={h}&fit=crop&auto=format&q=70"


def hero_block(key):
    """Широкая обложка над заголовком статьи + подпись автора фото."""
    if key not in HERO:
        return ""
    _, name, user = HERO[key]
    return (f'<figure class="cover"><img src="{esc(hero_url(key, 1440, 520))}" '
            f'srcset="{esc(hero_url(key, 720, 360))} 720w, {esc(hero_url(key, 1440, 520))} 1440w" '
            f'sizes="(max-width:760px) 100vw, 1080px" alt="" fetchpriority="high">'
            f'<figcaption>Фото: <a href="https://unsplash.com/@{esc(user)}{UNSPLASH_UTM}" rel="noopener">{esc(name)}</a>'
            f' / <a href="https://unsplash.com/{UNSPLASH_UTM}" rel="noopener">Unsplash</a></figcaption></figure>')


PIN = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#c05f45" stroke-width="2" '
       'stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/>'
       '<circle cx="12" cy="10" r="3"/></svg>')


def logo(name, small=False):
    cls = "logo lg" if small == "xs" else "logo sm" if small else "logo"
    if VENUE_LOGO.get(name):
        return f'<img class="{cls}" src="/{esc(VENUE_LOGO[name])}" alt="{esc(name)}" loading="lazy">'
    return f'<div class="{cls} mono">{esc((name or "?")[:1].upper())}</div>'


def link_label(url):
    if "instagram.com" in url:
        return "Instagram"
    if "t.me/" in url or "telegram" in url:
        return "Telegram"
    return "Сайт"


def maps_url(address, name):
    return "https://www.google.com/maps/search/?api=1&query=" + quote(", ".join(x for x in (address or name, "Белград") if x))


def crumbs_back(href, text):
    return f'<a class="back" href="{href}">‹ {esc(text)}</a>'



# Загрузка приложения: скачать /index.html и подменить им страницу. Приложение
# разберёт адрес само; __KLUBOK_ROUTE подсказывает раздел, пока грузится
# data/routes.json. Если приложение не скачалось, остаётся текст страницы.
BOOT = """<script>document.documentElement.className+=" booting";window.__KLUBOK_ROUTE=%s;
(function(){var q=function(s,a){var e=document.querySelector(s);return e?e.getAttribute(a):""};window.__KLUBOK_HEAD={path:window.__KLUBOK_ROUTE.path||"",canonical:q('link[rel="canonical"]',"href"),robots:q('meta[name="robots"]',"content"),description:q('meta[name="description"]',"content")}})();
fetch("/index.html").then(function(r){if(!r.ok)throw r.status;return r.text()}).then(function(t){document.open();document.write(t);document.close()}).catch(function(){document.documentElement.classList.remove("booting")});</script>"""


def page(path, title, description, body, canonical_path, image=None, jsonld=None, noindex=False, wide=False,
         route=None, out=None):
    """route — что открыть в приложении ({"id"|"venue"|"route": …}); None — страница без приложения."""
    out = out or ROOT / path / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    url = SITE + canonical_path
    img = SITE + "/" + image if image else SITE + "/og-cover.png"
    ld = f'\n<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    robots = "noindex, follow" if noindex else "index, follow, max-image-preview:large"
    boot = ""
    if route is not None:
        hint = dict(route, path=canonical_path, title=title) if route else {}
        boot = "\n" + BOOT % json.dumps(hint, ensure_ascii=False).replace("</", "<\\/")
    boot_img = '<div class="boot" aria-hidden="true"><div><img src="/loader.png" alt=""></div></div>\n' if route is not None else ""
    on = lambda p: ' class="on"' if path == p else ""
    body = f'<main class="page{" wide" if wide else ""}">{body}</main>'
    out.write_text(f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(url)}">
<meta name="robots" content="{robots}">
<meta name="theme-color" content="#edf1f3">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Клубок">
<meta property="og:locale" content="ru_RS">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(img)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>{ld}{boot}
</head>
<body>
{boot_img}<header class="site">
<a class="brand" href="/"><img src="/logo.png" alt="Клубок"><span>Куда сходить с ребёнком в Белграде</span></a>
<nav class="nav"><a href="/">Афиша</a><a href="/schedule/"{on("schedule")}>Расписание</a><a href="/venues/"{on("venues")}>Площадки</a></nav>
</header>
{body}
<footer class="foot">
<div class="fl"><span>Расписание обновлено {BUILT}</span>
<span class="fa"><a href="/blog/">Блог</a><a href="https://t.me/liza_portishead" target="_blank" rel="noopener">Обратная связь</a></span></div>
<a class="friend" href="https://t.me/mamakudaidem" target="_blank" rel="noopener"><img src="/data/images/friend-mamakudaidem.jpg" alt="Мама, куда идём сегодня?" width="36" height="36">
<span><small>Советуем telegram-канал</small><b>Мама, куда идём сегодня?</b></span></a>
</footer>
</body>
</html>
""", encoding="utf-8")


def redirect(path, to):
    """Бывшая страница: сразу уводит на to (GitHub Pages не умеет серверных редиректов)."""
    out = ROOT / path / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Клубок</title>
<meta name="robots" content="noindex, follow"><link rel="canonical" href="{SITE}{to}">
<meta http-equiv="refresh" content="0; url={to}"><script>location.replace("{to}")</script></head>
<body><a href="{to}">Перейти в блог Клубка</a></body></html>
""", encoding="utf-8")


EPATHS = {}


def epath(e):
    return EPATHS[e["id"]]


def event_line(e, with_place=True):
    bits = [when(e)]
    if e.get("ageLabel"):
        bits.append(e["ageLabel"])
    if with_place and e.get("place"):
        bits.append(e["place"])
    sub = " · ".join(b for b in bits if b)
    thumb = (f'<img class="thumb" src="/{esc(e["image"])}" alt="" loading="lazy">' if e.get("image")
             else logo(e.get("place"), True))
    return (f'<li><a class="ecard" href="/{epath(e)}/">{thumb}'
            f'<div><div class="t">{esc(e["title"])}</div><div class="s">{esc(sub)}</div></div></a></li>')


def sort_key(e):
    if e.get("date"):
        return (0, e["date"], e.get("time") or "")
    wd = e.get("wd") or [9]
    return (1, min(wd), e.get("time") or "")


def main():
    data = json.loads((ROOT / "data" / "events.json").read_text(encoding="utf-8"))
    today = today_belgrade()
    events = [e for e in data["events"] if not e.get("date") or e["date"] >= today.isoformat()]
    events.sort(key=sort_key)

    old_dirs = MANIFEST.read_text(encoding="utf-8").split() if MANIFEST.exists() else []
    for d in OWNED_DIRS + tuple(old_dirs):
        shutil.rmtree(ROOT / d, ignore_errors=True)

    # --- площадки ---
    venues = {}
    for e in events:
        venues.setdefault(e["place"], []).append(e)
    slugs, used = {}, set()
    for name in sorted(venues):
        s = base = slugify(name)
        if s in RESERVED:
            s = base = s + "-kids"
        n = 2
        while s in used:
            s, n = f"{base}-{n}", n + 1
        used.add(s)
        slugs[name] = s

    MANIFEST.write_text("\n".join(sorted(slugs.values())) + "\n", encoding="utf-8")

    # --- категории ---
    cats = {}
    for e in events:
        if e.get("category"):
            cats.setdefault(e["category"], {"label": e["categoryLabel"], "events": []})["events"].append(e)

    urls = [("/", "1.0"), ("/venues/", "0.8")]

    # страницы событий
    eslug = {}
    for e in events:
        v = slugs[e["place"]]
        cand = e["id"]
        for pre in (v + "-", (e.get("source") or {}).get("id", "") + "-"):
            if pre != "-" and cand.startswith(pre) and len(cand) > len(pre):
                cand = cand[len(pre):]
                break
        cand = slugify(cand) if cand != e["id"] else re.sub(r"[^A-Za-z0-9_-]+", "-", cand)
        if (v, cand) in eslug.values():
            cand = re.sub(r"[^A-Za-z0-9_-]+", "-", e["id"])
        eslug[e["id"]] = (v, cand)

    EPATHS.update({i: f"{v}/{c}" for i, (v, c) in eslug.items()})

    dup = Counter((e["title"], e.get("ageLabel"), e["place"]) for e in events)
    for e in events:
        v_slug = slugs[e["place"]]
        title_bits = [e["title"]]
        if e.get("ageLabel"):
            title_bits.append(e["ageLabel"])
        if dup[(e["title"], e.get("ageLabel"), e["place"])] > 1 and when(e):
            title_bits.append(when(e))
        title = f"{' · '.join(title_bits)} — {e['place']}, Белград | Клубок"
        desc = first_sentence(e.get("short") or e.get("desc") or e["title"], 110)
        desc = f"{when(e).capitalize()}. {e['place']}, Белград. {desc}".strip()
        src = e.get("source") or {}
        chips = ""
        if e.get("ageLabel"):
            chips += f'<span class="chip">{esc(e["ageLabel"])}</span>'
        if e.get("category"):
            chips += f'<a class="chip" href="/category/{esc(e["category"])}/">{esc(e["categoryLabel"])}</a>'
        chips = f'<div class="chips">{chips}</div>' if chips else ""
        dur = f'<p class="dur">Длится {esc(e["dur"])}</p>' if e.get("dur") else ""
        image = e.get("image")
        hero = f'<img class="hero" src="/{esc(image)}" alt="{esc(e["title"])}">' if image else ""
        price = ""
        if e.get("price"):
            long_ = " long" if len(e["price"]) > 28 else ""
            price = f'<div class="lab">Стоимость</div><div class="price{long_}">{esc(e["price"])}</div>'
        cta = ""
        if src.get("url"):
            cta = f'<a class="btn" href="{esc(src["url"])}" rel="noopener">{esc(src.get("cta") or "Записаться")}</a>'
        note = f'<div class="note">Информация взята из открытого источника — {esc(src["name"])}</div>' if src.get("name") else ""
        vaddr = f'<div class="a">{esc(e["address"])}</div>' if e.get("address") else ""
        body = f"""{crumbs_back("/" + v_slug + "/", "Назад к площадке")}
<div class="detail">
<div>
<h1>{esc(e["title"])}</h1>
<div class="when">{esc(when(e))}</div>
{chips}
<div class="desc">{paragraphs(e.get("desc") or e.get("short"))}{dur}</div>
<hr class="rule">
<a class="vrow" href="/{v_slug}/">{logo(e["place"])}<div><b>{esc(e["place"])} ›</b>{vaddr}</div></a>
</div>
<aside>{hero}<div class="pricecard">{price}{cta}{note}</div></aside>
</div>"""
        ld = None
        if e.get("date"):
            start = e["date"] + (f"T{e['time']}:00" if e.get("time") else "")
            ld = {"@context": "https://schema.org", "@type": "Event", "name": e["title"],
                  "startDate": start, "eventStatus": "https://schema.org/EventScheduled",
                  "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                  "description": plain(e.get("short") or e.get("desc")),
                  "location": {"@type": "Place", "name": e["place"],
                               "address": {"@type": "PostalAddress", "streetAddress": e.get("address") or "",
                                           "addressLocality": "Belgrade", "addressCountry": "RS"}}}
            if image:
                ld["image"] = f"{SITE}/{image}"
        page(epath(e), title, desc, body, f"/{epath(e)}/", image, ld, wide=True, route={"id": e["id"]})
        urls.append((f"/{epath(e)}/", "0.5"))

    # страницы площадок
    for name, evs in venues.items():
        s = slugs[name]
        address = next((e["address"] for e in evs if e.get("address")), "")
        phone = next((e["placePhone"] for e in evs if e.get("placePhone")), "")
        sources = {}
        for e in evs:
            src = e.get("source") or {}
            if src.get("url"):
                sources.setdefault(src["url"], src.get("cta") or "Сайт площадки")
        regular = [e for e in evs if not e.get("date")]
        dated = [e for e in evs if e.get("date")]
        cat_labels = sorted({e["categoryLabel"] for e in evs if e.get("categoryLabel")})
        title = f"{name} — детские занятия в Белграде: расписание и цены | Клубок"
        desc = f"{name}" + (f", {address}" if address else "") + ". "
        desc += (f"Занятия для детей: {', '.join(c.lower() for c in cat_labels)}. " if cat_labels else "Занятия для детей. ")
        desc += "Расписание, возраст, цены и запись."
        contacts = VENUE_CONTACTS.get(name, {})
        phone = phone or contacts.get("phone", "")
        pills = ""
        if phone:
            pills += f'<a class="pill" href="tel:{esc(re.sub(r"[^0-9+]", "", phone))}">{esc(phone)}</a>'
        seen = set()
        for key in ("website", "instagram", "telegram"):
            u = contacts.get(key)
            if u and u not in seen:
                seen.add(u)
                pills += f'<a class="pill" href="{esc(u)}" rel="noopener">{link_label(u)}</a>'
        for u, c in sources.items():
            if u not in seen and not any(u.rstrip("/") == x.rstrip("/") for x in seen):
                seen.add(u)
                pills += f'<a class="pill" href="{esc(u)}" rel="noopener">{link_label(u)}</a>'
        addr_html = ""
        if address:
            addr_html = (f'<div class="lab">Адрес</div><p class="addr">{PIN}<span>{esc(address)}</span></p>'
                         f'<a class="pill" href="{esc(maps_url(address, name))}" rel="noopener">Открыть на карте</a>')
        vcats = {e["category"]: e["categoryLabel"] for e in evs if e.get("category")}
        sub = ('<div class="chips" style="margin-top:8px">' + "".join(
            f'<a class="chip" href="/category/{esc(c)}/">{esc(l)}</a>' for c, l in sorted(vcats.items(), key=lambda kv: kv[1]))
            + "</div>") if vcats else ""
        sections = ""
        if regular:
            sections += '<h2>Регулярные занятия</h2><ul class="cards">' + "".join(event_line(e, False) for e in regular) + "</ul>"
        if dated:
            sections += '<h2>Ближайшие события</h2><ul class="cards">' + "".join(event_line(e, False) for e in dated) + "</ul>"
        body = f"""{crumbs_back("/venues/", "Назад к площадкам")}
<div class="vcard">
<div class="vhead">{logo(name)}<div><h1>{esc(name)}</h1>{sub}</div></div>
{addr_html}
<div class="pills">{pills}</div>
</div>
{sections}"""
        ld = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": name,
              "address": {"@type": "PostalAddress", "streetAddress": address, "addressLocality": "Belgrade",
                          "addressCountry": "RS"}}
        if phone:
            ld["telephone"] = phone
        page(s, title, desc, body, f"/{s}/", None, ld, route={"venue": name})
        urls.append((f"/{s}/", "0.7"))

    # список площадок
    items = "".join(
        f'<li><a class="ecard" href="/{slugs[n]}/">{logo(n)}<div><div class="t">{esc(n)}</div>'
        f'<div class="s">{esc(next((e["address"] for e in venues[n] if e.get("address")), ""))} · занятий: {len(venues[n])}</div></div></a></li>'
        for n in sorted(venues) if n not in VENUE_HIDDEN)
    page("venues", "Площадки: детские студии, кружки и клубы в Белграде | Клубок",
         "Русскоязычные детские студии, кружки, секции и театры в Белграде: адреса, расписание занятий, возраст и цены.",
         f'<h1>Площадки в Белграде</h1><p class="lead">Детские студии, кружки, секции и театры. <a href="/blog/"><u>Гайды по районам и направлениям</u></a></p><ul class="vgrid">{items}</ul>',
         "/venues/", route={"route": "venues"})

    # категории
    def age_range(evs):
        lo = [e["age"][0] for e in evs if isinstance(e.get("age"), list) and len(e["age"]) == 2 and e["age"][0] is not None]
        hi = [e["age"][1] for e in evs if isinstance(e.get("age"), list) and len(e["age"]) == 2 and e["age"][1] is not None and e["age"][1] < 90]
        return (min(lo), max(hi)) if lo and hi else None

    def plural(n, forms):
        m10, m100 = n % 10, n % 100
        return forms[0] if m10 == 1 and m100 != 11 else forms[1] if 2 <= m10 <= 4 and not 12 <= m100 <= 14 else forms[2]

    WHO = ("занятие", "занятия", "занятий")
    SHOWS = ("спектакль", "спектакля", "спектаклей")

    def price_from(e):
        """Разовая цена в RSD из свободного текста цены (первое число перед RSD/дин)."""
        m = re.search(r"(\d[\d  .]*)\s*(?:RSD|рсд|дин|din)", e.get("price") or "", re.I)
        if not m:
            return None
        n = int(re.sub(r"\D", "", m.group(1)))
        return n if 200 <= n <= 20000 else None

    def fmt_rsd(n):
        return f"{n:,}".replace(",", " ") + " RSD"

    def faq(evs, where, upper=True):
        """Частые вопросы, ответы — из самой афиши. where — «на Врачаре», «в Белграде»…"""
        regular = [e for e in evs if not e.get("date")]
        qa = []
        pool = regular or evs
        ages = age_range(pool)
        if ages:
            youngest = min((e for e in pool if (e.get("age") or [None])[0] is not None), key=lambda e: e["age"][0])
            since = "с первых месяцев" if ages[0] == 0 else f"с {ages[0]} {plural(ages[0], ('года', 'лет', 'лет'))}"
            qa.append((f"С какого возраста есть занятия {where}?",
                       f"Самые младшие группы — {since} "
                       f"(например, «{esc(youngest['title'])}», {esc(youngest['place'])})"
                       + (f", самые старшие — до {ages[1]} лет" if upper else "") + ". Возраст указан у каждого занятия."))
        if regular:
            per = Counter(i for e in regular for i in (e.get("wd") or []))
            top = [WEEKDAYS_DAT[i] for i, _ in per.most_common(2)]
            wknd = sum(1 for e in regular if set(e.get("wd") or []) & {5, 6})
            times = sorted(e["time"] for e in regular if e.get("time"))
            a = f"Больше всего занятий — по {top[0]}" + (f" и {top[1]}" if len(top) > 1 else "") + "."
            if times:
                a += f" Самое раннее начинается в {times[0]}, самое позднее — в {times[-1]}."
            a += (f" По выходным — {wknd} {plural(wknd, WHO)}." if wknd else " По выходным занятий нет.")
            qa.append(("В какие дни и во сколько проходят занятия?", a))
            prices = sorted(p for p in (price_from(e) for e in regular) if p)
            if len(prices) >= 3:
                qa.append(("Сколько стоит одно занятие?",
                           f"Разовое занятие стоит от {fmt_rsd(prices[0])} до {fmt_rsd(prices[-1])}, "
                           f"чаще всего около {fmt_rsd(prices[len(prices) // 2])}. Абонемент на месяц обычно выгоднее — "
                           "цены указаны на странице каждого занятия."))
        qa.append(("Как записаться?",
                   "Откройте занятие — на его странице есть кнопка записи, она ведёт на сайт, в Instagram или "
                   "Telegram площадки. Афиша Клубка обновляется ежедневно, но перед первым визитом лучше "
                   "уточнить расписание у площадки."))
        html_ = "".join(f"<dt>{q}</dt><dd>{a}</dd>" for q, a in qa)
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", a)}}
            for q, a in qa]}
        return f'<h2>Частые вопросы</h2><dl class="faq">{html_}</dl>', ld

    def venue_cards(evs):
        by = {}
        for e in evs:
            by.setdefault(e["place"], []).append(e)
        return "".join(
            f'<li><a class="ecard" href="/{slugs[n]}/">{logo(n)}<div><div class="t">{esc(n)}</div>'
            f'<div class="s">{esc(next((e["address"] for e in es if e.get("address")), ""))} · {len(es)} '
            f'{plural(len(es), WHO)}</div></div></a></li>'
            for n, es in sorted(by.items()) if n not in VENUE_HIDDEN)

    def days_label(ds):
        """(1,2,3,4) -> «вт–пт», (0,3) -> «пн, чт»."""
        ds = list(ds)
        if len(ds) >= 3 and ds == list(range(ds[0], ds[-1] + 1)):
            return f"{WEEKDAYS_SHORT[ds[0]]}–{WEEKDAYS_SHORT[ds[-1]]}"
        return ", ".join(WEEKDAYS_SHORT[i] for i in ds)

    def slots_of(es):
        """{(дни,): [время…]} — одинаковые наборы дней вместе: «вт–пт 08:30, 09:30»."""
        slots = {}
        for e in es:
            for d in (e.get("wd") or []):
                slots.setdefault(e.get("time") or "", set()).add(d)
        by_days = {}
        for t, ds in slots.items():
            by_days.setdefault(tuple(sorted(ds)), []).append(t)
        return by_days

    def when_str(by_days, with_days=True):
        return " · ".join((days_label(ds) if with_days else "")
                          + (" " + ", ".join(sorted(x for x in ts if x)) if any(ts) else "")
                          for ds, ts in sorted(by_days.items())).strip()

    def compact(evs, show=5):
        """Плотный список. Одно занятие одной площадки — одна строка: разные дни
        склеиваются («пн, ср 17:00»), разные возрастные группы — мини-списком внутри
        строки. Первые show строк видны, остальные — под «Ещё N»."""
        rows = {}
        for e in evs:
            rows.setdefault((e["title"], e["place"]), {}).setdefault(e.get("ageLabel") or "", []).append(e)
        lines = []
        for (title, place), ages in rows.items():
            first = next(iter(ages.values()))[0]
            head = f'<li><a href="/{epath(first)}/">{logo(place, "xs")}<div><div class="t">{esc(title)}</div>'
            if len(ages) == 1:
                age, es = next(iter(ages.items()))
                sub = " · ".join(x for x in (age, place) if x)
                lines.append(f'{head}<div class="p">{esc(sub)}</div></div><span class="w">{esc(when_str(slots_of(es)))}</span></a></li>')
                continue
            groups = sorted(ages.items(), key=lambda kv: ((kv[1][0].get("age") or [99])[0] or 0, kv[0]))
            per = [(age, slots_of(es)) for age, es in groups]
            day_sets = {tuple(sorted(per_[1])) for per_ in per}
            same_days = len(day_sets) == 1   # у всех групп одни и те же дни — пишем их один раз
            all_days = sorted({d for ds in next(iter(day_sets)) for d in ds}) if same_days else []
            days_txt = (f"по {WEEKDAYS_DAT[all_days[0]]}" if len(all_days) == 1 else days_label(all_days)) if all_days else ""
            chips = "".join(f'<span><b>{esc(age or "все возрасты")}</b> {esc(when_str(bd, not same_days))}</span>'
                            for age, bd in per)
            sub = " · ".join(x for x in (place, days_txt, f"{len(per)} {plural(len(per), ('группа', 'группы', 'групп'))}") if x)
            lines.append(f'{head}<div class="p">{esc(sub)}</div><div class="ag">{chips}</div></div></a></li>')
        head_, rest = lines[:show], lines[show:]
        out = f'<ul class="clist">{"".join(head_)}</ul>'
        if rest:
            out += (f'<details class="more"><summary>Ещё {len(rest)} {plural(len(rest), WHO)}</summary>'
                    f'<ul class="clist" style="border-top:0">{"".join(rest)}</ul></details>')
        return out

    def by_category(evs, where):
        """Занятия, сгруппированные по направлениям: <h2>Танцы на Врачаре</h2> + список."""
        groups = {}
        for e in evs:
            groups.setdefault(e.get("categoryLabel") or "Другие занятия", []).append(e)
        order = sorted(groups.items(), key=lambda kv: (kv[0] == "Другие занятия", -len(kv[1])))
        return "".join(f'<h2>{esc(label)} {esc(where)}</h2>{compact(es)}' for label, es in order)

    def dated_compact(evs, show=6):
        lines = [f'<li><a href="/{epath(e)}/">{logo(e["place"], "xs")}<div><div class="t">{esc(e["title"])}</div>'
                 f'<div class="p">{esc(" · ".join(x for x in (e.get("ageLabel"), e["place"]) if x))}</div></div>'
                 f'<span class="w">{esc(when(e))}</span></a></li>' for e in evs]
        out = f'<ul class="clist">{"".join(lines[:show])}</ul>'
        if lines[show:]:
            out += (f'<details class="more"><summary>Ещё {len(lines) - show}</summary>'
                    f'<ul class="clist" style="border-top:0">{"".join(lines[show:])}</ul></details>')
        return out

    def stats(evs, noun=WHO, age_label=None):
        n_v = len({e["place"] for e in evs})
        bits = [f"{n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))}",
                f"{len(evs)} {plural(len(evs), noun)}"]
        ages = age_range(evs)
        if age_label or ages:
            bits.append(age_label or f"возраст {ages[0]}–{ages[1]} лет")
        return '<div class="stats">' + "".join(f"<span>{esc(b)}</span>" for b in bits) + "</div>"

    def intro(paras):
        return '<div class="intro">' + "".join(f"<p>{esc(p)}</p>" for p in paras) + "</div>"

    blog = []   # (раздел, url, заголовок, анонс, meta, картинка)

    def excerpt(text, limit=170):
        return first_sentence(text, limit)

    def cover(evs, prefer=None, used=()):
        """Картинка карточки: заглушка категории или фото одного из занятий."""
        for c_ in ([prefer] if prefer else []) + [e.get("category") for e in evs]:
            ph = f"data/images/placeholder-{c_}.jpg"
            if c_ and ph not in used and (ROOT / ph).exists():
                return ph
        return next((e["image"] for e in evs if e.get("image") and e["image"] not in used), "og-cover.png")
    for c, info in sorted(cats.items(), key=lambda kv: -len(kv[1]["events"])):
        evs = info["events"]
        label = info["label"]
        h1, what, kw = CAT_SEO.get(c, (f"{label} для детей в Белграде", label.lower(), label.lower()))
        cat_venues = {}
        for e in evs:
            cat_venues.setdefault(e["place"], []).append(e)
        n_ev, n_v = len(evs), len(cat_venues)
        names = sorted(cat_venues)
        vcards = "".join(
            f'<li><a class="ecard" href="/{slugs[n]}/">{logo(n)}<div><div class="t">{esc(n)}</div>'
            f'<div class="s">{esc(next((e["address"] for e in es if e.get("address")), ""))} · {len(es)} '
            f'{plural(len(es), ("занятие", "занятия", "занятий"))}</div></div></a></li>'
            for n, es in sorted(cat_venues.items()))
        others = "".join(
            f'<a class="chip" href="/category/{esc(oc)}/">{esc(oi["label"])}</a>'
            for oc, oi in sorted(cats.items()) if oc != c)
        more = intro(CAT_INTRO.get(c, []))
        if c == "early_dev":
            more += '<p class="lead">Смотрите также: <a href="/kruzhki/malyshi/">все занятия для малышей в Белграде</a>.</p>'
        reg_c = [e for e in evs if not e.get("date")]
        dated_c = [e for e in evs if e.get("date")]
        if c == "theatre":
            listing = (f'<h2>Театры и площадки</h2><ul class="vgrid sm">{vcards}</ul>'
                       f'<h2>Афиша детских спектаклей</h2>{dated_compact(dated_c[:60], 12)}'
                       + (f'<h2>Театральные студии</h2>{compact(reg_c)}' if reg_c else ""))
        else:
            listing = (f'<h2>Где заниматься</h2><ul class="vgrid sm">{vcards}</ul>'
                       + (f'<h2>Все занятия</h2>{compact(reg_c, 10)}' if reg_c else "")
                       + (f'<h2>Ближайшие события</h2>{dated_compact(dated_c)}' if dated_c else ""))
        faq_html, faq_ld = faq(evs, "в Белграде")
        body = (f'{crumbs_back("/blog/", "Блог")}{hero_block(c)}'
                f'<h1>{esc(h1)}</h1>{stats(evs, SHOWS if c == "theatre" else WHO)}{more}'
                f'{listing}{faq_html}'
                f'<h2>Другие категории</h2><div class="chips">{others}</div>')
        ld = {"@context": "https://schema.org", "@type": "ItemList", "name": h1,
              "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{slugs[n]}/", "name": n}
                                  for i, n in enumerate(names)]}
        if faq_ld:
            ld = {"@context": "https://schema.org",
                  "@graph": [{k: v for k, v in x.items() if k != "@context"} for x in (ld, faq_ld)]}
        page(f"category/{c}", f"{h1} — расписание и цены | Клубок",
             f"{h1}: {n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))}, {n_ev} {plural(n_ev, SHOWS if c == 'theatre' else WHO)}. "
             f"{kw.capitalize()}. Расписание, возраст и цены.",
             body, f"/category/{c}/", None, ld)
        urls.append((f"/category/{c}/", "0.8"))
        blog.append(("Направления", f"/category/{c}/", h1,
                     excerpt(CAT_INTRO[c][0] if c in CAT_INTRO else f"{h1}: {what}."),
                     f"{n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))} · {n_ev} {plural(n_ev, SHOWS if c == 'theatre' else WHO)}",
                     cover(evs, c)))

    # /category/ — больше не отдельная страница: всё собрано в «Блоге»
    redirect("category", "/blog/")

    # --- посадочные: кружки по районам и занятия для малышей ---
    def landing(path, h1, title, desc, paras, evs, where, cta, related, upper=True):
        regular_l = [e for e in evs if not e.get("date")]
        dated_l = [e for e in evs if e.get("date")]
        faq_html, faq_ld = faq(evs, where, upper)
        body = (f'{crumbs_back("/blog/", "Блог")}{hero_block(path.split("/")[-1])}<h1>{esc(h1)}</h1>{stats(evs, WHO, None if upper else "для детей до 4 лет")}{intro(paras)}'
                f'<a class="btn" href="{esc(cta[0])}" style="display:inline-block;margin:4px 0 0">{esc(cta[1])}</a>'
                f'<h2>Площадки {esc(where)}</h2><ul class="vgrid sm">{venue_cards(evs)}</ul>'
                f'{by_category(regular_l, where)}'
                + (f'<h2>Ближайшие события {esc(where)}</h2>{dated_compact(dated_l[:20])}' if dated_l else "")
                + f'{faq_html}<h2>Смотрите также</h2><div class="chips">'
                + "".join(f'<a class="chip" href="{h}">{esc(t)}</a>' for h, t in related) + "</div>")
        names = sorted({e["place"] for e in evs})
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "ItemList", "name": h1, "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": f"{SITE}/{slugs[n]}/", "name": n} for i, n in enumerate(names)]},
            {k: v for k, v in faq_ld.items() if k != "@context"},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Клубок", "item": SITE + "/"},
                {"@type": "ListItem", "position": 2, "name": "Блог", "item": SITE + "/blog/"},
                {"@type": "ListItem", "position": 3, "name": h1, "item": f"{SITE}/{path}/"}]}]}
        page(path, title, desc, body, f"/{path}/", None, ld)
        urls.append((f"/{path}/", "0.8"))

    related_all = [(f"/kruzhki/{s_}/", f"Кружки {w}") for s_, (_, w, _, _) in DISTRICT_PAGES.items()]
    related_all += [("/kruzhki/malyshi/", "Занятия для малышей"), ("/category/dance/", "Танцы для детей"),
                    ("/category/theatre/", "Детские театры"), ("/schedule/", "Всё расписание")]
    for ds, (dname, where, members, paras) in DISTRICT_PAGES.items():
        evs = [e for e in events if district_of(e) in members]
        if len(evs) < 3:   # меньше трёх занятий — страница была бы пустой
            continue
        cats_here = Counter(e["categoryLabel"] for e in evs if e.get("categoryLabel") and not e.get("date"))
        top = ", ".join(l.lower() for l, _ in cats_here.most_common(4))
        n_v = len({e["place"] for e in evs})
        dist_q = ",".join(DISTRICT_SLUGS[m] for m in members if m in DISTRICT_SLUGS)
        landing(f"kruzhki/{ds}", f"Кружки для детей {where}",
                f"Кружки и секции для детей {where}, Белград: расписание и цены | Клубок",
                f"Детские кружки {where} (Белград): {n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))}, "
                f"{len(evs)} {plural(len(evs), WHO)} — {top}. Возраст, расписание, цены и запись.",
                paras, evs, where, (f"/schedule/?district={dist_q}", f"Открыть расписание {where}"),
                [r for r in related_all if r[0] != f"/kruzhki/{ds}/"])
        blog.append(("Районы", f"/kruzhki/{ds}/", f"Кружки для детей {where}", excerpt(paras[0]),
                     f"{n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))} · {len(evs)} {plural(len(evs), WHO)}",
                     DISTRICT_COVER[ds] if (ROOT / DISTRICT_COVER.get(ds, "-")).exists()
                     else cover([e for e in evs if not e.get("date")] or evs, None, {b[5] for b in blog})))

    toddlers = [e for e in events if isinstance(e.get("age"), list) and len(e["age"]) == 2
                and e["age"][0] is not None and e["age"][0] <= 3]
    if toddlers:
        n_v = len({e["place"] for e in toddlers})
        landing("kruzhki/malyshi", "Занятия для малышей в Белграде",
                "Занятия для малышей в Белграде: развитие, музыка, танцы, плавание от 1 года | Клубок",
                f"Занятия для детей до 4 лет в Белграде: {n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))} — "
                "раннее развитие, занятия с мамой, музыка, хореография, плавание, творчество. Расписание и цены.",
                MALYSHI_INTRO, toddlers, "для малышей", ("/schedule/?age=2", "Открыть расписание для 2 лет"),
                [r for r in related_all if r[0] != "/kruzhki/malyshi/"] + [("/category/early_dev/", "Раннее развитие")], upper=False)
        blog.append(("Направления", "/kruzhki/malyshi/", "Занятия для малышей в Белграде", excerpt(MALYSHI_INTRO[0]),
                     f"{n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))} · {len(toddlers)} {plural(len(toddlers), WHO)}",
                     "data/images/placeholder-early_dev.jpg"))

    redirect("kruzhki", "/blog/")

    # авторские статьи блога
    for a in ARTICLES:
        src = (ROOT / "articles" / f'{a["slug"]}.html').read_text(encoding="utf-8")
        upd = date.fromisoformat(a["updated"])
        others = [b for b in blog if b[0] == "Районы"] + [b for b in blog if b[1] == "/kruzhki/malyshi/"]
        more_ = "".join(f'<a class="chip" href="{b[1]}">{esc(b[2])}</a>' for b in others)
        body = (f'{crumbs_back("/blog/", "Блог")}<article class="article">{hero_block(a["slug"])}'
                f'<h1>{esc(a["title"])}</h1><div class="meta">Клубок · обновлено {upd.day} {MONTHS[upd.month - 1]} {upd.year}</div>'
                f'{src}<h2>Читайте также</h2><div class="chips">{more_}</div></article>')
        ld = {"@context": "https://schema.org", "@type": "Article", "headline": a["title"], "description": a["description"],
              "image": hero_url(a["slug"], 1200, 675), "datePublished": a["published"], "dateModified": a["updated"],
              "inLanguage": "ru", "author": {"@type": "Organization", "name": "Клубок", "url": SITE + "/"},
              "publisher": {"@type": "Organization", "name": "Клубок", "url": SITE + "/"},
              "mainEntityOfPage": f'{SITE}/blog/{a["slug"]}/'}
        page(f'blog/{a["slug"]}', f'{a["seo_title"]} | Клубок', a["description"], body, f'/blog/{a["slug"]}/', None, ld)
        urls.append((f'/blog/{a["slug"]}/', "0.8"))
        blog.insert(0, ("Гайды", f'/blog/{a["slug"]}/', a["title"], a["excerpt"],
                        f'гайд · {upd.day} {MONTHS[upd.month - 1]}', None))

    # «Блог»: все посадочные страницы карточками
    def post(b, big=False):
        _, href, title, text, meta, img = b
        key = href.strip("/").split("/")[-1]
        if key in HERO:
            img = hero_url(key, 1200 if big else 640, 675 if big else 360)
        elif img:
            img = "/" + img
        lazy = "" if big else ' loading="lazy"'
        pic = f'<img src="{esc(img)}" alt=""{lazy}>' if img else '<img alt="">'
        li = '<li style="grid-column:1/-1">' if big else "<li>"
        cls = "post big" if big else "post"
        return (f'{li}<a class="{cls}" href="{href}">{pic}'
                f'<div class="pb"><span class="tag">{esc(b[0])}</span><h3>{esc(title)}</h3><p>{esc(text)}</p>'
                f'<div class="meta">{esc(meta if b[0] == "Гайды" else f"{meta} · обновлено {today.day} {MONTHS[today.month - 1]}")}</div></div></a></li>')
    sections_order = ["Гайды", "Районы", "Направления"]
    # сверху — свежий гайд (или самый насыщенный район), дальше по разделам
    order = {s_: i for i, s_ in enumerate(sections_order)}
    ranked = sorted(blog, key=lambda b: (order[b[0]], -int((re.search(r"· (\d+)", b[4]) or re.search(r"(\d+)", "0")).group(1))))
    featured = ranked[0]
    posts = f'<ul class="bgrid">{post(featured, True)}</ul>'
    for sec in sections_order:
        items_ = [b for b in ranked if b[0] == sec and b is not featured]
        if items_:
            posts += f'<h2 class="bsec">{esc(sec)}</h2><ul class="bgrid">{"".join(post(b) for b in items_)}</ul>'
    page("blog", "Блог Клубка: гайды по детским кружкам и занятиям в Белграде | Клубок",
         "Гайды Клубка: кружки для детей по районам Белграда (Врачар, Старый Град, Новый Белград), занятия для малышей, "
         "танцы, театры, робототехника, языки и другие направления — с расписанием и ценами.",
         '<h1>Блог Клубка</h1><p class="lead">Гайды по детским занятиям в Белграде: где заниматься в вашем районе, '
         'что выбрать для малыша и какие есть студии по каждому направлению. Расписание в статьях обновляется каждый день.</p>'
         + posts, "/blog/", None,
         {"@context": "https://schema.org", "@type": "Blog", "name": "Блог Клубка", "url": SITE + "/blog/",
          "blogPost": [{"@type": "BlogPosting", "headline": b[2], "url": SITE + b[1], "description": b[3],
                        "dateModified": today.isoformat()} for b in ranked]},
         wide=True)
    urls.append(("/blog/", "0.8"))

    # «Расписание»: регулярные занятия по дням недели
    regular = [e for e in events if not e.get("date")]
    by_wd = ""
    for i, wd_name in enumerate(WEEKDAYS):
        day = sorted((e for e in regular if i in (e.get("wd") or [])), key=lambda e: e.get("time") or "")
        if day:
            by_wd += f'<h2>{wd_name}</h2><ul class="cards">{"".join(event_line(e) for e in day)}</ul>'
    page("schedule", "Расписание детских кружков и секций в Белграде по дням недели | Клубок",
         f"Постоянные детские занятия в Белграде: {len(regular)} {plural(len(regular), ('занятие', 'занятия', 'занятий'))} "
         "по дням недели — танцы, языки, плавание, творчество, спорт. Возраст, время, цены и запись.",
         f'<h1>Расписание детских занятий в Белграде</h1><p class="lead">Постоянные кружки и секции по дням недели.</p>{by_wd}',
         "/schedule/", route={"route": "schedule"}, wide=True)
    urls.append(("/schedule/", "0.9"))
    # Расписание с фильтрами: простые сочетания, у которых приложение ставит свой canonical
    # (порядок параметров cat → age → evlang как в приложении). Мелкие (<3 занятий) не добавляем.
    for lang in ("ru", "sr"):
        urls.append((f"/schedule/?evlang={lang}", "0.6"))
    for a in range(0, 13):
        if sum(1 for e in regular if (e.get("age") or [0, 99])[0] <= a <= (e.get("age") or [0, 99])[1]) >= 3:
            urls.append((f"/schedule/?age={a}", "0.6"))
    for c in sorted({e.get("category") for e in regular if e.get("category")}):
        if sum(1 for e in regular if e.get("category") == c) >= 3:
            urls.append((f"/schedule/?cat={quote(c)}&evlang=ru", "0.5"))

    # все ближайшие события
    dated = [e for e in events if e.get("date")]
    page("events/all", "Детские события в Белграде: спектакли, мастер-классы, праздники | Клубок",
         "Ближайшие разовые детские события в Белграде: спектакли, концерты, мастер-классы и праздники. Даты, возраст, цены и запись.",
         f'<h1>Ближайшие детские события в Белграде</h1><p class="lead">Спектакли, мастер-классы, концерты и праздники.</p>'
         f'<ul class="cards">{"".join(event_line(e) for e in dated)}</ul>',
         "/events/all/", route={"route": "eventsAll"})
    urls.append(("/events/all/", "0.9"))

    page("favs", "Моё избранное | Клубок", "Сохранённые занятия и события.",
         '<h1>Моё избранное</h1><p class="lead">Сохранённые занятия и события.</p>',
         "/favs/", route={"route": "favs"}, noindex=True)

    # Любой другой адрес: GitHub Pages отдаёт 404.html, приложение разбирает путь само.
    page("", "Клубок — афиша детских занятий и мероприятий в Белграде",
         "Детские кружки, секции и мероприятия в Белграде.",
         '<h1>Страница не найдена</h1><p class="lead"><a href="/"><u>Открыть афишу</u></a></p>',
         "/", route={}, noindex=True, out=ROOT / "404.html")

    (ROOT / "data" / "routes.json").write_text(json.dumps(
        {"v": slugs, "e": EPATHS}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    # sitemap
    lastmod = today.isoformat()
    rows = "".join(
        f"  <url>\n    <loc>{SITE}{u.replace('&', '&amp;')}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <priority>{p}</priority>\n  </url>\n"
        for u, p in urls)
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n",
        encoding="utf-8")
    print(f"events={len(events)} venues={len(venues)} categories={len(cats)} sitemap_urls={len(urls)}")


if __name__ == "__main__":
    main()
