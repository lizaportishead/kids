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
OWNED_DIRS = ("venues", "category", "kruzhki", "events", "schedule", "favs")
MANIFEST = ROOT / "static-pages.txt"
# Каталоги в корне сайта, которые нельзя занимать под slug площадки.
RESERVED = {"en", "sr", "data", "docs", "db", "collector", "scripts", "supabase", "scratch",
            "venues", "category", "events", "assets", "kids", "api", "static",
            "schedule", "favs", "afisha", "event", "venue", "kruzhki"}

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
.clist .w{flex:none;text-align:right;font-size:14px;font-weight:600;white-space:nowrap}
details.more summary{cursor:pointer;list-style:none;display:inline-block;margin-top:10px;font-weight:600;font-size:15px;color:var(--orange)}
details.more summary::-webkit-details-marker{display:none}details.more[open] summary{display:none}
.vgrid.sm{grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px}.vgrid.sm .ecard{padding:10px 12px}.vgrid.sm .t{font-size:15px}.vgrid.sm .s{font-size:13px}
@media(max-width:640px){.clist a{flex-wrap:wrap;align-items:flex-start}.clist a>div{flex-basis:calc(100% - 52px)}.clist .w{flex-basis:100%;padding-left:52px;text-align:left;color:var(--orange);white-space:normal}}
footer .links{display:flex;flex-wrap:wrap;justify-content:center;gap:6px 14px;margin-top:8px}
footer{border-top:1px solid #eee6d6;margin-top:24px;padding:24px 28px;font-size:14px;color:var(--muted);text-align:center}
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
}
DISTRICT_KEYWORDS = ["Врачар", "Дорчол", "Стари Град", "Старый Град", "Нови Београд", "Новый Белград", "Земун",
                     "Звездара", "Вождовац", "Чукарица", "Раковица", "Палилула", "Савски венац"]
DISTRICT_ALIASES = {"Стари Град": "Старый Град", "Нови Београд": "Новый Белград"}
# Слаги районов в фильтре приложения (?district=…)
DISTRICT_SLUGS = {"Врачар": "vracar", "Дорчол": "dorcol", "Старый Град": "stari-grad", "Новый Белград": "novi-beograd"}


def district_of(e):
    """Район по адресу — так же, как в приложении (districtOf), но без учёта регистра."""
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
<footer>Клубок — афиша детских занятий и мероприятий в Белграде · <a href="/category/">Занятия по категориям</a>
<div class="links"><a href="/kruzhki/vracar/">Кружки на Врачаре</a><a href="/kruzhki/stari-grad/">Кружки в Старом Граде</a><a href="/kruzhki/novi-beograd/">Кружки в Новом Белграде</a><a href="/kruzhki/malyshi/">Занятия для малышей</a><a href="/category/dance/">Танцы для детей</a><a href="/category/theatre/">Детские театры</a></div></footer>
</body>
</html>
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
         f'<h1>Площадки в Белграде</h1><p class="lead">Детские студии, кружки, секции и театры. <a href="/category/"><u>Смотреть по категориям</u></a></p><ul class="vgrid">{items}</ul>',
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

    def compact(evs, show=5):
        """Плотный список: одно и то же занятие в разные дни — одна строка
        («пн, ср 17:00»), первые show строк видны, остальные — под «Ещё N»."""
        rows = {}
        for e in evs:
            rows.setdefault((e["title"], e["place"], e.get("ageLabel")), []).append(e)
        lines = []
        for (title, place, age), es in rows.items():
            slots = {}
            for e in es:
                for i in (e.get("wd") or []):
                    slots.setdefault(e.get("time") or "", set()).add(i)
            # одинаковые наборы дней — один раз: «вт–пт 08:30, 09:30»
            by_days = {}
            for t, ds in slots.items():
                by_days.setdefault(tuple(sorted(ds)), []).append(t)
            w = " · ".join(days_label(ds) + (" " + ", ".join(sorted(x for x in ts if x)) if any(ts) else "")
                           for ds, ts in sorted(by_days.items()))
            sub = " · ".join(x for x in (age, place) if x)
            lines.append(f'<li><a href="/{epath(es[0])}/">{logo(place, "xs")}<div><div class="t">{esc(title)}</div>'
                         f'<div class="p">{esc(sub)}</div></div><span class="w">{esc(w)}</span></a></li>')
        head, rest = lines[:show], lines[show:]
        out = f'<ul class="clist">{"".join(head)}</ul>'
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

    cat_links = []
    for c, info in sorted(cats.items(), key=lambda kv: -len(kv[1]["events"])):
        evs = info["events"]
        label = info["label"]
        h1, what, kw = CAT_SEO.get(c, (f"{label} для детей в Белграде", label.lower(), label.lower()))
        cat_venues = {}
        for e in evs:
            cat_venues.setdefault(e["place"], []).append(e)
        n_ev, n_v = len(evs), len(cat_venues)
        names = sorted(cat_venues)
        shown = ", ".join(names[:6]) + (f" и ещё {len(names) - 6}" if len(names) > 6 else "")
        ages = age_range(evs)
        age_txt = f" Возраст детей — от {ages[0]} до {ages[1]} лет." if ages else ""
        intro_txt = (f"В афише Клубка — {n_ev} {plural(n_ev, ('занятие', 'занятия', 'занятий'))} и событий: {what}. "
                 f"Площадки: {shown}.{age_txt} Расписание, цены и запись — на страницах занятий.")
        vcards = "".join(
            f'<li><a class="ecard" href="/{slugs[n]}/">{logo(n)}<div><div class="t">{esc(n)}</div>'
            f'<div class="s">{esc(next((e["address"] for e in es if e.get("address")), ""))} · {len(es)} '
            f'{plural(len(es), ("занятие", "занятия", "занятий"))}</div></div></a></li>'
            for n, es in sorted(cat_venues.items()))
        others = "".join(
            f'<a class="chip" href="/category/{esc(oc)}/">{esc(oi["label"])}</a>'
            for oc, oi in sorted(cats.items()) if oc != c)
        more = f'{intro(CAT_INTRO[c])}<p class="lead">{esc(intro_txt)}</p>' if c in CAT_INTRO else f'<p class="lead">{esc(intro_txt)}</p>'
        if c == "early_dev":
            more += '<p class="lead">Смотрите также: <a href="/kruzhki/malyshi/">все занятия для малышей в Белграде</a>.</p>'
        reg_c = [e for e in evs if not e.get("date")]
        dated_c = [e for e in evs if e.get("date")]
        if c == "theatre":
            listing = (f'<h2>Театры и площадки</h2><ul class="vgrid sm">{vcards}</ul>'
                       f'<h2>Афиша детских спектаклей</h2>{dated_compact(dated_c[:60], 12)}'
                       + (f'<h2>Театральные студии</h2>{compact(reg_c)}' if reg_c else ""))
        elif c in CAT_INTRO:
            listing = (f'<h2>Где заниматься</h2><ul class="vgrid sm">{vcards}</ul>'
                       f'<h2>Все занятия</h2>{compact(reg_c, 10)}'
                       + (f'<h2>Ближайшие события</h2>{dated_compact(dated_c)}' if dated_c else ""))
        else:
            listing = (f'<h2>Где заниматься</h2><ul class="cards">{vcards}</ul>'
                       f'<h2>Все занятия</h2><ul class="cards">{"".join(event_line(e) for e in evs)}</ul>')
        faq_html, faq_ld = faq(evs, "в Белграде") if c in CAT_INTRO else ("", None)
        body = (f'{crumbs_back("/category/", "Все категории")}'
                f'<h1>{esc(h1)}</h1>{(stats(evs, SHOWS if c == "theatre" else WHO)) if c in CAT_INTRO else ""}{more}'
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
        cat_links.append((c, label, h1, n_ev))

    # оглавление категорий
    hub = "".join(
        f'<li><a class="ecard" href="/category/{c}/"><div><div class="t">{esc(h1)}</div>'
        f'<div class="s">{n} {plural(n, ("занятие", "занятия", "занятий"))}</div></div></a></li>'
        for c, label, h1, n in cat_links)
    page("category", "Занятия для детей в Белграде по категориям: танцы, языки, плавание, творчество | Клубок",
         "Все виды детских занятий в Белграде: танцы, языки, плавание, творчество, музыка, спорт, шахматы, робототехника и подготовка к школе.",
         f'<h1>Занятия для детей в Белграде по категориям</h1><p class="lead">Выберите направление — покажем площадки, расписание и цены.</p>'
         f'<ul class="cards">{hub}</ul>', "/category/")
    urls.append(("/category/", "0.8"))

    # --- посадочные: кружки по районам и занятия для малышей ---
    def landing(path, h1, title, desc, paras, evs, where, cta, related, upper=True):
        regular_l = [e for e in evs if not e.get("date")]
        dated_l = [e for e in evs if e.get("date")]
        faq_html, faq_ld = faq(evs, where, upper)
        body = (f'{crumbs_back("/kruzhki/", "Кружки по районам")}<h1>{esc(h1)}</h1>{stats(evs, WHO, None if upper else "для детей до 4 лет")}{intro(paras)}'
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
                {"@type": "ListItem", "position": 2, "name": "Кружки по районам", "item": SITE + "/kruzhki/"},
                {"@type": "ListItem", "position": 3, "name": h1, "item": f"{SITE}/{path}/"}]}]}
        page(path, title, desc, body, f"/{path}/", None, ld)
        urls.append((f"/{path}/", "0.8"))

    related_all = [(f"/kruzhki/{s_}/", f"Кружки {w}") for s_, (_, w, _, _) in DISTRICT_PAGES.items()]
    related_all += [("/kruzhki/malyshi/", "Занятия для малышей"), ("/category/dance/", "Танцы для детей"),
                    ("/category/theatre/", "Детские театры"), ("/schedule/", "Всё расписание")]
    hub_items = []
    for ds, (dname, where, members, paras) in DISTRICT_PAGES.items():
        evs = [e for e in events if district_of(e) in members]
        if not evs:
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
        hub_items.append((f"/kruzhki/{ds}/", f"Кружки для детей {where}", f"{n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))} · {top}"))

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
        hub_items.append(("/kruzhki/malyshi/", "Занятия для малышей в Белграде", f"{n_v} {plural(n_v, ('площадка', 'площадки', 'площадок'))} · для детей до 4 лет"))

    page("kruzhki", "Кружки для детей в Белграде по районам: Врачар, Старый Град, Новый Белград | Клубок",
         "Детские кружки и секции в районах Белграда: Врачар, Старый Град и Дорчол, Новый Белград. Площадки, расписание, возраст и цены.",
         '<h1>Кружки для детей в Белграде по районам</h1><p class="lead">Выберите район — покажем площадки, расписание и цены. '
         'Или смотрите <a href="/category/">занятия по направлениям</a>.</p><ul class="cards">'
         + "".join(f'<li><a class="ecard" href="{h}"><div><div class="t">{esc(t)}</div><div class="s">{esc(sub)}</div></div></a></li>'
                   for h, t, sub in hub_items) + "</ul>", "/kruzhki/")
    urls.append(("/kruzhki/", "0.8"))

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
