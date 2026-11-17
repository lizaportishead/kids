/* Клубок: согласие на аналитику (Google Analytics + Яндекс.Метрика).
   До согласия счётчики НЕ загружаются и cookie не ставятся.
   Выбор хранится в localStorage["klubok_consent"] = "granted" | "denied".
   Подключается на каждой странице одним тегом <script src="/consent.js"></script>.
   Переспросить: window.klubokConsentReset() (ссылка «Настройки cookie» в подвале). */
(function () {
  var KEY = "klubok_consent", GA = "G-7WVH2BQ1K6", YM = 112118644;
  var T = {
    ru: { t: "Мы используем cookie для статистики", p: "Чтобы понимать, чем пользуются родители, мы считаем посещения через Google Analytics и Яндекс.Метрику. Они ставят cookie только с вашего согласия. Для работы сайта (язык, избранное, фильтры) нужны только данные в вашем браузере — они не требуют согласия.", ok: "Принять", no: "Отказаться", more: "Подробнее" },
    en: { t: "We use cookies for statistics", p: "To understand how parents use the site we count visits with Google Analytics and Yandex Metrica. They set cookies only with your consent. The site itself (language, favourites, filters) only stores data in your browser and needs no consent.", ok: "Accept", no: "Decline", more: "Learn more" },
    sr: { t: "Koristimo kolačiće za statistiku", p: "Da bismo razumeli kako roditelji koriste sajt, brojimo posete preko Google Analytics i Yandex Metrica. Kolačiće postavljaju samo uz vaš pristanak. Za rad sajta (jezik, omiljeno, filteri) čuvaju se samo podaci u vašem pregledaču i pristanak nije potreban.", ok: "Prihvatam", no: "Odbijam", more: "Detaljnije" }
  };
  function get() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function set(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }
  function lang() {
    try {
      var q = new URLSearchParams(location.search).get("lang") || localStorage.getItem("klubok_lang");
      if (T[q]) return q;
    } catch (e) {}
    return "ru";
  }

  function loadAnalytics() {
    if (window.__klubokAnalytics) return;
    window.__klubokAnalytics = true;
    // Google Analytics 4
    var s = document.createElement("script");
    s.async = true; s.src = "https://www.googletagmanager.com/gtag/js?id=" + GA;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", GA);
    // Яндекс.Метрика (без Вебвизора: записи сессий не ведём)
    (function (m, e, t, r, i, k, a) {
      m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments); };
      m[i].l = 1 * new Date();
      k = e.createElement(t); a = e.getElementsByTagName(t)[0]; k.async = 1; k.src = r;
      a.parentNode.insertBefore(k, a);
    })(window, document, "script", "https://mc.yandex.ru/metrika/tag.js?id=" + YM, "ym");
    window.ym(YM, "init", { ssr: true, clickmap: true, accurateTrackBounce: true, trackLinks: true,
      referrer: document.referrer, url: location.href });
  }

  function removeCookies() {
    // Снимаем то, что могли поставить счётчики раньше (на своём домене).
    var host = location.hostname.split("."), doms = [location.hostname];
    if (host.length > 2) doms.push(host.slice(-2).join("."));
    doms.push("." + host.slice(-2).join("."));
    document.cookie.split(";").forEach(function (c) {
      var n = c.split("=")[0].trim();
      if (/^(_ga|_gid|_gat|_ym|_ym_|yabs|ymex|_clck)/.test(n)) {
        doms.forEach(function (d) { document.cookie = n + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=" + d; });
        document.cookie = n + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
      }
    });
  }

  function banner() {
    if (document.getElementById("kc-banner") || !document.body) return;
    var L = T[lang()];
    var d = document.createElement("div");
    d.id = "kc-banner"; d.setAttribute("role", "dialog"); d.setAttribute("aria-label", L.t);
    d.style.cssText = "position:fixed;left:16px;right:16px;bottom:16px;max-width:520px;z-index:2147483000;box-sizing:border-box;" +
      "background:#fff;border:1px solid #ebe0ca;border-radius:14px;padding:16px 18px;box-shadow:0 8px 30px rgba(32,30,29,.18);" +
      "font:400 13px/19px Figtree,system-ui,sans-serif;color:#35312c";
    var btn = "font:600 13px Figtree,system-ui,sans-serif;border-radius:9px;padding:9px 16px;cursor:pointer;border:1px solid #201e1d;";
    d.innerHTML = '<div style="font-weight:700;font-size:14px;margin-bottom:4px">' + L.t + "</div>" +
      '<div style="color:#6d6357">' + L.p + ' <a href="/cookies/" style="color:#35312c;text-decoration:underline">' + L.more + "</a></div>" +
      '<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">' +
      '<button type="button" data-kc="granted" style="' + btn + 'background:#201e1d;color:#fff">' + L.ok + "</button>" +
      '<button type="button" data-kc="denied" style="' + btn + 'background:#fff;color:#201e1d">' + L.no + "</button></div>";
    d.addEventListener("click", function (ev) {
      var v = ev.target && ev.target.getAttribute && ev.target.getAttribute("data-kc");
      if (!v) return;
      set(v);
      if (d.parentNode) d.parentNode.removeChild(d);
      if (v === "granted") loadAnalytics(); else removeCookies();
    });
    document.body.appendChild(d);
  }

  function start() {
    var v = get();
    if (v === "granted") loadAnalytics();
    else if (v !== "denied") banner();
  }

  window.klubokConsentReset = function () {
    try { localStorage.removeItem(KEY); } catch (e) {}
    removeCookies();
    banner();
  };

  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
  // Страница могла быть переписана приложением (document.write) — повторный запуск скрипта сам перерисует баннер.
})();
