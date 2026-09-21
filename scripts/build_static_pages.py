#!/usr/bin/env python3
"""Генерирует статичные индексируемые страницы из data/events.json.

Приложение (index.html) — одностраничное, все разделы живут за «#», и для
Google это один адрес. Чтобы поиск видел площадки и занятия, для каждой
площадки, категории и события собирается обычная HTML-страница с текстом:

  venues/               — список площадок
  <venue>/              — площадка: адрес, расписание, ближайшие события
  <venue>/<event>/      — одно занятие или событие (без даты в адресе)
  category/<cat>/       — занятия одной категории

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
OWNED_DIRS = ("venues", "category", "events")
MANIFEST = ROOT / "static-pages.txt"
# Каталоги в корне сайта, которые нельзя занимать под slug площадки.
RESERVED = {"en", "sr", "data", "docs", "db", "collector", "scripts", "supabase", "scratch",
            "venues", "category", "events", "assets", "kids", "api", "static"}

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
footer{border-top:1px solid #eee6d6;margin-top:24px;padding:24px 28px;font-size:14px;color:var(--muted);text-align:center}
@media(max-width:900px){.detail{grid-template-columns:1fr;gap:28px}.detail h1{font-size:34px}}
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
VENUE_CONTACTS = {}
for _m in re.finditer(r'^\s*"([^"\n]+)":\s*\{([^}\n]*)\}', _js_block(APP, "VENUE_CONTACTS"), re.M):
    VENUE_CONTACTS[_m.group(1)] = dict(re.findall(r'(\w+):\s*"([^"]*)"', _m.group(2)))

PIN = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#c05f45" stroke-width="2" '
       'stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/>'
       '<circle cx="12" cy="10" r="3"/></svg>')


def logo(name, small=False):
    cls = "logo sm" if small else "logo"
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



def page(path, title, description, body, canonical_path, image=None, jsonld=None, noindex=False, wide=False):
    out = ROOT / path / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    url = SITE + canonical_path
    img = SITE + "/" + image if image else SITE + "/og-cover.png"
    ld = f'\n<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    robots = "noindex, follow" if noindex else "index, follow, max-image-preview:large"
    venues_on = ' class="on"' if path == "venues" else ""
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
<style>{CSS}</style>{ld}
</head>
<body>
<header class="site">
<a class="brand" href="/"><img src="/logo.png" alt="Клубок"><span>Куда сходить с ребёнком в Белграде</span></a>
<nav class="nav"><a href="/">Расписание</a><a href="/venues/"{venues_on}>Площадки</a><a class="add" href="/">Открыть афишу</a></nav>
</header>
{body}
<footer>Клубок — афиша детских занятий и мероприятий в Белграде · <a href="/">Открыть афишу</a></footer>
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
<aside>{hero}<div class="pricecard">{price}{cta}<a class="btn alt" href="/#event/{quote(e["id"])}">Открыть в афише</a>{note}</div></aside>
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
        page(epath(e), title, desc, body, f"/{epath(e)}/", image, ld, wide=True)
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
        sub = f'<div class="lead">{esc(", ".join(cat_labels[:3]))}</div>' if cat_labels else ""
        sections = ""
        if regular:
            sections += '<h2>Регулярные занятия</h2><ul class="cards">' + "".join(event_line(e, False) for e in regular) + "</ul>"
        if dated:
            sections += '<h2>Ближайшие события</h2><ul class="cards">' + "".join(event_line(e, False) for e in dated) + "</ul>"
        body = f"""{crumbs_back("/venues/", "Назад к площадкам")}
<div class="vcard">
<div class="vhead">{logo(name)}<div><h1>{esc(name)}</h1>{sub}</div></div>
{addr_html}
<div class="pills">{pills}<a class="pill" href="/#venue/{quote(name)}">Открыть в афише</a></div>
</div>
{sections}"""
        ld = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": name,
              "address": {"@type": "PostalAddress", "streetAddress": address, "addressLocality": "Belgrade",
                          "addressCountry": "RS"}}
        if phone:
            ld["telephone"] = phone
        page(s, title, desc, body, f"/{s}/", None, ld)
        urls.append((f"/{s}/", "0.7"))

    # список площадок
    items = "".join(
        f'<li><a class="ecard" href="/{slugs[n]}/">{logo(n)}<div><div class="t">{esc(n)}</div>'
        f'<div class="s">{esc(next((e["address"] for e in venues[n] if e.get("address")), ""))} · занятий: {len(venues[n])}</div></div></a></li>'
        for n in sorted(venues))
    page("venues", "Площадки: детские студии, кружки и клубы в Белграде | Клубок",
         "Русскоязычные детские студии, кружки, секции и театры в Белграде: адреса, расписание занятий, возраст и цены.",
         f'<h1>Площадки в Белграде</h1><p class="lead">Детские студии, кружки, секции и театры</p><ul class="vgrid">{items}</ul>',
         "/venues/")

    # категории
    for c, info in sorted(cats.items()):
        evs = info["events"]
        label = info["label"]
        body = (f'{crumbs_back("/", "Вся афиша")}'
                f'<h1>{esc(label)} для детей в Белграде</h1>'
                f'<p class="lead">Занятия и события в категории «{esc(label)}»: расписание, возраст, цены.</p>'
                f'<ul class="cards">{"".join(event_line(e) for e in evs)}</ul>')
        page(f"category/{c}", f"{label} для детей в Белграде — занятия и расписание | Клубок",
             f"{label} для детей в Белграде: {len(evs)} занятий и событий, расписание, возраст и цены.",
             body, f"/category/{c}/")
        urls.append((f"/category/{c}/", "0.7"))

    # sitemap
    lastmod = today.isoformat()
    rows = "".join(
        f"  <url>\n    <loc>{SITE}{u}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <priority>{p}</priority>\n  </url>\n"
        for u, p in urls)
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n",
        encoding="utf-8")
    print(f"events={len(events)} venues={len(venues)} categories={len(cats)} sitemap_urls={len(urls)}")


if __name__ == "__main__":
    main()
