/* Queensland Eye Institute — site behaviour (no dependencies)
   1. Navigation (mobile panel, submenus)
   2. Accessibility preferences (text size, contrast, theme) persisted in localStorage
   3. Site search (client-side index)
*/
(function () {
  'use strict';
  var doc = document, root = doc.documentElement;
  var PREF_KEY = 'qei-prefs';

  function readPrefs() {
    try { return JSON.parse(localStorage.getItem(PREF_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function writePrefs(p) {
    try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (e) { /* storage unavailable */ }
  }
  function applyPrefs(p) {
    if (p.textsize && p.textsize > 1) root.setAttribute('data-textsize', String(p.textsize)); else root.removeAttribute('data-textsize');
    if (p.contrast === 'high') root.setAttribute('data-contrast', 'high'); else root.removeAttribute('data-contrast');
    if (p.theme === 'light' || p.theme === 'dark') root.setAttribute('data-theme', p.theme); else root.removeAttribute('data-theme');
  }

  /* ---------- Navigation ---------- */
  function initNav() {
    var header = doc.querySelector('.header');
    var toggle = doc.querySelector('.nav-toggle');
    if (header && toggle) {
      toggle.addEventListener('click', function () {
        var open = header.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        doc.body.classList.toggle('nav-open', open);
        toggle.querySelector('.nav-toggle__label').textContent = open ? 'Close' : 'Menu';
      });
    }
    var items = doc.querySelectorAll('.nav__item--has-sub');
    Array.prototype.forEach.call(items, function (item) {
      var btn = item.querySelector(':scope > button');
      if (!btn) return;
      btn.addEventListener('click', function () {
        var open = item.classList.toggle('is-open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        Array.prototype.forEach.call(items, function (other) {
          if (other !== item) { other.classList.remove('is-open'); var b = other.querySelector(':scope > button'); if (b) b.setAttribute('aria-expanded', 'false'); }
        });
      });
    });
    doc.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        Array.prototype.forEach.call(items, function (item) { item.classList.remove('is-open'); var b = item.querySelector(':scope > button'); if (b) b.setAttribute('aria-expanded', 'false'); });
        var a11y = doc.querySelector('.a11y.is-open'); if (a11y) { a11y.classList.remove('is-open'); a11y.querySelector('.a11y__toggle').setAttribute('aria-expanded', 'false'); }
      }
    });
    doc.addEventListener('click', function (e) {
      if (!e.target.closest('.nav__item--has-sub')) {
        Array.prototype.forEach.call(items, function (item) { item.classList.remove('is-open'); var b = item.querySelector(':scope > button'); if (b) b.setAttribute('aria-expanded', 'false'); });
      }
      var a11y = doc.querySelector('.a11y.is-open');
      if (a11y && !e.target.closest('.a11y')) { a11y.classList.remove('is-open'); a11y.querySelector('.a11y__toggle').setAttribute('aria-expanded', 'false'); }
    });
  }

  /* ---------- Accessibility panel ---------- */
  function initA11y() {
    var wrap = doc.querySelector('.a11y');
    if (!wrap) return;
    var toggle = wrap.querySelector('.a11y__toggle');
    var prefs = readPrefs();
    function refresh() {
      Array.prototype.forEach.call(wrap.querySelectorAll('[data-textsize]'), function (b) {
        b.setAttribute('aria-pressed', String(prefs.textsize || 1) === b.getAttribute('data-textsize') ? 'true' : 'false');
      });
      var c = wrap.querySelector('[data-contrast-toggle]'); if (c) c.setAttribute('aria-pressed', prefs.contrast === 'high' ? 'true' : 'false');
      var t = wrap.querySelector('[data-theme-select]'); if (t) t.value = prefs.theme || 'system';
    }
    toggle.addEventListener('click', function () {
      var open = wrap.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) { var first = wrap.querySelector('.a11y__panel button, .a11y__panel select'); if (first) first.focus(); }
    });
    wrap.addEventListener('click', function (e) {
      var b = e.target.closest('[data-textsize]');
      if (b) { prefs.textsize = parseInt(b.getAttribute('data-textsize'), 10); writePrefs(prefs); applyPrefs(prefs); refresh(); }
      var c = e.target.closest('[data-contrast-toggle]');
      if (c) { prefs.contrast = prefs.contrast === 'high' ? 'normal' : 'high'; writePrefs(prefs); applyPrefs(prefs); refresh(); }
      var r = e.target.closest('[data-reset-prefs]');
      if (r) { prefs = {}; writePrefs(prefs); applyPrefs(prefs); refresh(); }
    });
    var sel = wrap.querySelector('[data-theme-select]');
    if (sel) sel.addEventListener('change', function () { prefs.theme = sel.value; writePrefs(prefs); applyPrefs(prefs); refresh(); });
    refresh();
  }

  /* ---------- Search ---------- */
  function tokenise(s) {
    return String(s || '').toLowerCase().replace(/[^a-z0-9\s-]/g, ' ').split(/\s+/).filter(function (t) { return t.length > 1; });
  }
  function initSearch() {
    var page = doc.querySelector('[data-search-page]');
    if (!page) return;
    var input = page.querySelector('input[type="search"]');
    var results = page.querySelector('[data-search-results]');
    var status = page.querySelector('[data-search-status]');
    var indexUrl = page.getAttribute('data-search-index');
    var index = null, loading = null;
    function load() {
      if (index) return Promise.resolve(index);
      if (loading) return loading;
      status.textContent = 'Loading search…';
      loading = fetch(indexUrl, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (data) {
        index = data.map(function (d) { d._t = tokenise(d.t); d._b = tokenise((d.d || '') + ' ' + (d.b || '') + ' ' + (d.k || '')); return d; });
        return index;
      });
      return loading;
    }
    function escapeHtml(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function run(q) {
      var terms = tokenise(q);
      if (!terms.length) { results.innerHTML = ''; status.textContent = 'Type a word or phrase, for example "cataract surgery", "IPL" or a doctor’s name.'; return; }
      load().then(function (idx) {
        var scored = [];
        idx.forEach(function (d) {
          var score = 0;
          terms.forEach(function (term) {
            d._t.forEach(function (w) { if (w === term) score += 12; else if (w.indexOf(term) === 0) score += 6; });
            var bodyHits = 0; d._b.forEach(function (w) { if (w === term) bodyHits += 1; else if (w.indexOf(term) === 0) bodyHits += 0.5; });
            score += Math.min(bodyHits, 8);
            if (d.s && d.s.toLowerCase().indexOf(term) !== -1) score += 3;
          });
          var allTerms = terms.every(function (term) { return d._t.concat(d._b).some(function (w) { return w.indexOf(term) === 0; }); });
          if (allTerms) score *= 1.5;
          if (score > 0) scored.push({ d: d, s: score });
        });
        scored.sort(function (a, b) { return b.s - a.s; });
        var top = scored.slice(0, 40);
        status.textContent = top.length ? (top.length === 1 ? '1 result' : top.length + ' results') + ' for “' + q + '”' : 'No results for “' + q + '”. Try a different word, or call 07 3239 5000 and our team will help.';
        results.innerHTML = top.map(function (r) {
          return '<li><span class="badge badge--outline">' + escapeHtml(r.d.s || 'Page') + '</span><h3><a href="' + escapeHtml(r.d.u) + '">' + escapeHtml(r.d.t) + '</a></h3><p>' + escapeHtml(r.d.d || '') + '</p></li>';
        }).join('');
      }).catch(function () { status.textContent = 'Search is unavailable right now. Please use the site menu or call 07 3239 5000.'; });
    }
    var params = new URLSearchParams(location.search);
    var q = params.get('q') || '';
    if (q) { input.value = q; run(q); } else { run(''); }
    var timer;
    input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { run(input.value); history.replaceState(null, '', '?q=' + encodeURIComponent(input.value)); }, 180); });
    page.querySelector('form').addEventListener('submit', function (e) { e.preventDefault(); run(input.value); });
    load();
  }

  applyPrefs(readPrefs());
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', function () { initNav(); initA11y(); initSearch(); });
  else { initNav(); initA11y(); initSearch(); }
})();
