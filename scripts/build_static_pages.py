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
*{box-sizing:border-box}body{margin:0;background:#edf1f3;color:#35312c;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
a{color:#2f6f8f}.wrap{max-width:760px;margin:0 auto;padding:20px 16px 48px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:20px;font-size:15px}
.top .logo{font-weight:800;font-size:20px;color:#35312c;text-decoration:none}
.crumbs{font-size:14px;color:#6b665f;margin-bottom:12px}
h1{font-size:30px;line-height:1.2;margin:0 0 12px;font-weight:800}h2{font-size:20px;margin:28px 0 10px}
.card{background:#fff;border-radius:14px;padding:16px 18px;margin:0 0 12px}
.meta{margin:0;padding:0;list-style:none}.meta li{margin:4px 0}.meta b{font-weight:600}
.cta{display:inline-block;background:#35312c;color:#fff;text-decoration:none;padding:11px 18px;border-radius:10px;font-weight:600;margin:6px 8px 6px 0}
.cta.alt{background:#fff;color:#35312c;border:1px solid #cfd6da}
.list{list-style:none;margin:0;padding:0}.list li{background:#fff;border-radius:12px;padding:12px 16px;margin:0 0 8px}
.list .sub{color:#6b665f;font-size:14px}.hero{width:100%;max-height:340px;object-fit:cover;border-radius:14px;margin-bottom:16px}
p{margin:0 0 12px}footer{margin-top:32px;font-size:14px;color:#6b665f}
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


def page(path, title, description, body, canonical_path, image=None, jsonld=None, noindex=False):
    out = ROOT / path / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    url = SITE + canonical_path
    img = SITE + "/" + image if image else SITE + "/og-cover.png"
    ld = f'\n<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    robots = "noindex, follow" if noindex else "index, follow, max-image-preview:large"
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
<style>{CSS}</style>{ld}
</head>
<body>
<div class="wrap">
<div class="top"><a class="logo" href="/">Клубок</a><a href="/venues/">Площадки</a></div>
{body}
<footer>Клубок — афиша детских занятий и мероприятий в Белграде. <a href="/">Открыть афишу</a></footer>
</div>
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
    return (f'<li><a href="/{epath(e)}/">{esc(e["title"])}</a>'
            f'<div class="sub">{esc(sub)}</div></li>')


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
        facts = []
        if when(e):
            facts.append(("Когда", when(e)))
        if e.get("dur"):
            facts.append(("Длительность", e["dur"]))
        if e.get("ageLabel"):
            facts.append(("Возраст", e["ageLabel"]))
        if e.get("price"):
            facts.append(("Цена", e["price"]))
        facts.append(("Где", f'<a href="/{v_slug}/">{esc(e["place"])}</a>'
                      + (f', {esc(e["address"])}' if e.get("address") else "")))
        if e.get("placePhone"):
            facts.append(("Телефон", esc(e["placePhone"])))
        facts_html = "".join(f"<li><b>{k}:</b> {v if k == 'Где' else esc(v)}</li>" for k, v in facts)
        src = e.get("source") or {}
        cta = ""
        if src.get("url"):
            cta = f'<a class="cta" href="{esc(src["url"])}" rel="noopener">{esc(src.get("cta") or "Записаться")}</a>'
        cat = ""
        if e.get("category"):
            cat = f' · <a href="/category/{esc(e["category"])}/">{esc(e["categoryLabel"])}</a>'
        image = e.get("image")
        hero = f'<img class="hero" src="/{esc(image)}" alt="{esc(e["title"])}">' if image else ""
        body = f"""<div class="crumbs"><a href="/">Клубок</a> › <a href="/{v_slug}/">{esc(e["place"])}</a>{cat}</div>
<h1>{esc(e["title"])}</h1>
{hero}<div class="card"><ul class="meta">{facts_html}</ul></div>
{paragraphs(e.get("desc") or e.get("short"))}
<p>{cta}<a class="cta alt" href="/#event/{quote(e["id"])}">Открыть в афише</a></p>"""
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
        page(epath(e), title, desc, body, f"/{epath(e)}/", image, ld)
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
        meta = []
        if address:
            meta.append(f"<li><b>Адрес:</b> {esc(address)}</li>")
        if phone:
            meta.append(f"<li><b>Телефон:</b> {esc(phone)}</li>")
        meta_html = f'<div class="card"><ul class="meta">{"".join(meta)}</ul></div>' if meta else ""
        ctas = "".join(f'<a class="cta" href="{esc(u)}" rel="noopener">{esc(c)}</a>' for u, c in sources.items())
        sections = ""
        if regular:
            sections += "<h2>Регулярные занятия</h2><ul class=\"list\">" + "".join(event_line(e, False) for e in regular) + "</ul>"
        if dated:
            sections += "<h2>Ближайшие события</h2><ul class=\"list\">" + "".join(event_line(e, False) for e in dated) + "</ul>"
        body = f"""<div class="crumbs"><a href="/">Клубок</a> › <a href="/venues/">Площадки</a></div>
<h1>{esc(name)}</h1>
{meta_html}
<p>{ctas}<a class="cta alt" href="/#venue/{quote(name)}">Открыть в афише</a></p>
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
        f'<li><a href="/{slugs[n]}/">{esc(n)}</a><div class="sub">'
        f'{esc(next((e["address"] for e in venues[n] if e.get("address")), ""))} · занятий: {len(venues[n])}</div></li>'
        for n in sorted(venues))
    page("venues", "Площадки: детские студии, кружки и клубы в Белграде | Клубок",
         "Русскоязычные детские студии, кружки, секции и театры в Белграде: адреса, расписание занятий, возраст и цены.",
         f'<div class="crumbs"><a href="/">Клубок</a></div><h1>Площадки в Белграде</h1><ul class="list">{items}</ul>',
         "/venues/")

    # категории
    for c, info in sorted(cats.items()):
        evs = info["events"]
        label = info["label"]
        body = (f'<div class="crumbs"><a href="/">Клубок</a> › <a href="/venues/">Площадки</a></div>'
                f'<h1>{esc(label)} для детей в Белграде</h1>'
                f'<p>Занятия и события в категории «{esc(label)}»: расписание, возраст, цены.</p>'
                f'<ul class="list">{"".join(event_line(e) for e in evs)}</ul>'
                f'<p><a class="cta alt" href="/">Вся афиша</a></p>')
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
