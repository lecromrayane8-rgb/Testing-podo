"""La page du site du bot : une seule page, sans dépendance externe, qui parle au serveur de webapp.py.

Mêmes couleurs que le tableau de bord (palette validée, sombre par défaut, bouton clair/sombre). Tout texte venu
des données est inséré avec textContent : jamais interprété comme du HTML.
"""
from __future__ import annotations

from .dashboard import CSS as DASHBOARD_CSS

SITE_CSS = """
:root { --accent: #2563c9; --accent-hover: #1d4fa3; }
.site-top { position: sticky; top: 0; z-index: 10; background: var(--page); border-bottom: 1px solid var(--border); }
.site-top-inner { max-width: 1120px; margin: 0 auto; padding: 12px 16px 0; }
.brand-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.brand-row .brand { margin: 0; }
.tabs { display: flex; gap: 2px; overflow-x: auto; margin-top: 6px; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tabs a { padding: 8px 12px; color: var(--text-secondary); text-decoration: none; white-space: nowrap;
  border-bottom: 2px solid transparent; font-weight: 600; font-size: 14px; }
.tabs a:hover { color: var(--text-primary); }
.tabs a[aria-current="page"] { color: var(--text-primary); border-bottom-color: var(--accent); }
main.site { padding-top: 20px; }
.view > section:first-child, .view > .hero:first-child { margin-top: 0; }
.hero { background: var(--surface-1); border: 1px solid var(--border); border-left: 4px solid var(--accent);
  border-radius: 12px; padding: 18px 20px; }
.eyebrow { margin: 0; color: var(--text-secondary); font-size: 12px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; }
.hero h1 { font-size: 24px; margin: 4px 0 6px; }
.hero p { margin: 0; color: var(--text-secondary); max-width: 760px; }
.row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 14px; }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 16px;
  border-radius: 999px; border: 1px solid var(--border); background: var(--surface-1); color: var(--text-primary);
  font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; text-decoration: none; }
.btn:hover { border-color: var(--accent); }
.btn:focus-visible, .seg button:focus-visible, .tabs a:focus-visible { outline: 2px solid var(--accent);
  outline-offset: 2px; }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
.btn-stop { border-color: var(--critical); }
.btn[disabled] { opacity: 0.5; cursor: not-allowed; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
  display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.card h3 { margin: 0; font-size: 15px; }
.card p { margin: 0; }
.card .row { margin-top: auto; padding-top: 8px; }
.card-head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.muted { color: var(--text-secondary); font-size: 13px; }
.why-not { color: var(--text-secondary); font-size: 12px; }
.mono { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 12px; }
.lastline { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-title { font-size: 14px; margin: 20px 0 8px; color: var(--text-secondary); text-transform: uppercase;
  letter-spacing: 0.05em; }
.empty-box { background: var(--surface-1); border: 1px dashed var(--border); border-radius: 12px; padding: 14px 16px;
  color: var(--text-secondary); }
.warn { margin-top: 16px; padding: 12px 16px; border-radius: 8px; border: 2px solid var(--warning); }
.journal { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 12px; }
@media (max-width: 760px) { .journal { grid-template-columns: minmax(0, 1fr); } }
.task-list { display: flex; flex-direction: column; gap: 6px; }
.task-list button { text-align: left; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
  padding: 8px 12px; color: var(--text-primary); font: inherit; font-size: 14px; cursor: pointer; }
.task-list button[aria-pressed="true"] { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
.log { margin: 0; background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
  height: 64vh; overflow: auto; white-space: pre-wrap; word-break: break-word; line-height: 1.5; font-size: 12.5px; }
.controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 12px; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 999px; overflow: hidden; }
.seg button { background: transparent; border: 0; padding: 6px 14px; color: var(--text-secondary); font: inherit;
  font-size: 13px; font-weight: 600; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--accent); color: #fff; }
.check { display: inline-flex; gap: 6px; align-items: center; font-size: 14px; color: var(--text-secondary); }
.status-line { margin: 0 0 12px; color: var(--text-secondary); font-size: 13px; }
td.focus { font-weight: 700; }
tr.strong td:first-child { box-shadow: inset 3px 0 0 var(--warning); }
@media (max-width: 600px) {
  .tabs { flex-wrap: wrap; }
  .tabs .long, .win:not(.focus), .vol { display: none; }
  #view-radar th, #view-radar td { padding: 8px 8px; }
}
.frame { display: block; width: 100%; height: 78vh; border: 1px solid var(--border); border-radius: 12px;
  background: var(--page); }
.form { display: grid; gap: 16px; max-width: 720px; }
.field { display: grid; gap: 4px; }
.field label { font-weight: 600; }
.field input { font: inherit; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--page); color: var(--text-primary); width: 100%; }
.field input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.toast { position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%); z-index: 20; max-width: min(560px, 92vw);
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 10px 16px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25); font-size: 14px; }
.toast.bad { border-color: var(--critical); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); margin-right: 6px;
  vertical-align: 0.05em; }
.dot-live { animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.35; } }
@media (prefers-reduced-motion: reduce) { .dot-live { animation: none; } }
"""

BODY = """
<header class="site-top"><div class="site-top-inner">
  <div class="brand-row">
    <p class="brand">Trading bot <span class="badge" id="mode-badge">…</span></p>
    <button id="theme-toggle" class="theme" type="button">Clair / sombre</button>
  </div>
  <nav class="tabs" aria-label="Pages du site">
    <a href="#accueil" data-view="accueil">Accueil</a>
    <a href="#radar" data-view="radar">Radar<span class="long"> des mouvements</span></a>
    <a href="#prix" data-view="prix">Prix</a>
    <a href="#tableau" data-view="tableau">Tableau<span class="long"> de bord</span></a>
    <a href="#journal" data-view="journal">Journal</a>
    <a href="#reglages" data-view="reglages">Réglages</a>
  </nav>
</div></header>
<main class="site">
  <div id="view-accueil" class="view">
    <div class="hero" aria-live="polite">
      <p class="eyebrow">Prochaine étape</p>
      <h1 id="next-title">Chargement…</h1>
      <p id="next-text"></p>
      <div class="row" id="next-actions"></div>
    </div>
    <div id="settings-warning" class="warn" hidden></div>
    <section><h2>En cours et récent</h2><div id="tasks" class="cards"></div></section>
    <section><h2>Résultats</h2><div id="results" class="cards"></div></section>
    <section><h2>Toutes les actions</h2><div id="actions"></div></section>
  </div>
  <div id="view-radar" class="view" hidden>
    <h1>Radar des mouvements</h1>
    <p class="meta" id="radar-intro"></p>
    <section>
      <div class="controls">
        <div class="seg" role="group" aria-label="Fenêtre" id="radar-windows"></div>
        <label class="check"><input type="checkbox" id="radar-rising"> Hausses seulement</label>
      </div>
      <p class="status-line" id="radar-status" aria-live="polite">Démarrage du radar…</p>
      <div class="table-wrap"><table><thead id="radar-head"></thead><tbody id="radar-rows"></tbody></table></div>
      <p class="note">Barre jaune : gros mouvement (au moins 1 % en 1 min, 2 % en 5 min ou 4 % en 15 min). Un mouvement
        affiché ici a déjà eu lieu : le labo court terme teste s'il est rentable de sauter dessus (stratégies
        « Impulsion »), frais compris. Le radar ne passe aucun ordre.</p>
    </section>
  </div>
  <div id="view-prix" class="view" hidden>
    <h1>Prix en direct</h1>
    <p class="meta">Les vrais prix publics de plusieurs plateformes, côte à côte, toutes les 10 secondes. Aucun compte
      nécessaire.</p>
    <section>
      <p class="status-line" id="prices-status" aria-live="polite">Connexion aux plateformes…</p>
      <div class="table-wrap" id="prices-table" hidden><table><thead id="prices-head"></thead>
        <tbody id="prices-rows"></tbody></table></div>
      <p class="note">Écart : différence entre la plateforme la plus chère et la moins chère. « $ » : coté en dollars.
        Un écart de 0,1 % ne couvre même pas les frais d'un aller-retour (environ 0,3 %).</p>
      <ul class="note" id="prices-errors"></ul>
    </section>
  </div>
  <div id="view-tableau" class="view" hidden>
    <div class="controls">
      <div class="seg" role="group" aria-label="Tableau de bord" id="board-choice">
        <button type="button" data-board="bots">Mes bots et les labos</button>
        <button type="button" data-board="tournoi-court-terme">Tournoi court terme</button>
        <button type="button" data-board="tournoi">Tournoi long terme</button>
      </div>
      <a class="btn" id="board-open" href="/tableau/bots" target="_blank" rel="noopener">Ouvrir en grand</a>
    </div>
    <iframe class="frame" id="board-frame" title="Tableau de bord" src="about:blank"></iframe>
  </div>
  <div id="view-journal" class="view" hidden>
    <h1>Journal</h1>
    <p class="meta">Ce que disent les commandes lancées depuis le site, en direct.</p>
    <section class="journal">
      <div class="task-list" id="journal-tasks"></div>
      <pre class="log mono" id="log" tabindex="0" aria-label="Journal de la tâche choisie">Choisis une tâche.</pre>
    </section>
  </div>
  <div id="view-reglages" class="view" hidden>
    <h1>Réglages</h1>
    <p class="meta" id="mode-line"></p>
    <section>
      <form class="form" id="settings-form" novalidate></form>
      <div class="row">
        <button class="btn btn-primary" type="submit" form="settings-form">Enregistrer</button>
        <button class="btn" type="button" id="open-env">Ouvrir le fichier .env (réglages avancés)</button>
      </div>
      <p class="note">Les commandes lancées après l'enregistrement utilisent les nouveaux réglages ; celles qui tournent
        déjà gardent les anciens jusqu'à leur prochain lancement.</p>
    </section>
  </div>
  <footer><p class="note">Les performances passées ne garantissent rien. Le site ne passe jamais d'ordre en argent
    réel. Garde la fenêtre noire du bot ouverte : la fermer arrête tout ce que le site a lancé.</p></footer>
</main>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
"""

JS = r"""
(() => {
  const $ = (sel) => document.querySelector(sel);
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children) if (child !== null && child !== undefined) node.append(child);
    return node;
  }
  const HEADERS = {'Content-Type': 'application/json', 'X-Demande': 'site-du-bot'};
  async function getJSON(path) {
    const r = await fetch(path, {cache: 'no-store'});
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ('Erreur ' + r.status));
    return data;
  }
  async function post(path, body) {
    const r = await fetch(path, {method: 'POST', headers: HEADERS, body: JSON.stringify(body || {})});
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data.ok === false) throw new Error(data.error || ('Erreur ' + r.status));
    return data;
  }
  let toastTimer = null;
  function toast(text, bad) {
    const t = $('#toast');
    t.textContent = text; t.className = 'toast' + (bad ? ' bad' : ''); t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, bad ? 9000 : 4500);
  }

  // --- formats à la française ---
  const MINUS = '−';
  function pct(v, digits) {
    if (v === null || v === undefined || !isFinite(v)) return '—';
    const d = digits === undefined ? 2 : digits;
    const s = Math.abs(v * 100).toFixed(d);
    if (Number(s) === 0) return s.replace('.', ',') + ' %';  // jamais « −0,00 % »
    return (v > 0 ? '+' : MINUS) + s.replace('.', ',') + ' %';
  }
  function pctPoints(v) {  // déjà en pourcentage (espérance par trade du labo)
    if (v === null || v === undefined || !isFinite(v)) return '—';
    return (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(v).toFixed(3).replace('.', ',') + ' %';
  }
  function price(v) {
    if (!v) return '—';
    if (v >= 1000) return v.toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    return Number(v.toPrecision(5)).toLocaleString('fr-FR', {maximumFractionDigits: 12});
  }
  function money(v) { return v ? Math.round(v / 1e6).toLocaleString('fr-FR') + ' M$' : '—'; }
  function duration(s) {
    if (s < 60) return s + ' s';
    const m = Math.floor(s / 60);
    if (m < 60) return m + ' min';
    const h = Math.floor(m / 60);
    if (h < 48) return h + ' h ' + String(m % 60).padStart(2, '0');
    return Math.floor(h / 24) + ' j ' + (h % 24) + ' h';
  }
  function when(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', {day: '2-digit', month: '2-digit'}) + ' à ' +
      d.toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'});
  }
  function cls(v) { return v > 0 ? 'up' : v < 0 ? 'down' : ''; }

  // --- navigation ---
  const VIEWS = ['accueil', 'radar', 'prix', 'tableau', 'journal', 'reglages'];
  let view = 'accueil';
  function show(name) {
    view = VIEWS.includes(name) ? name : 'accueil';
    for (const v of VIEWS) $('#view-' + v).hidden = v !== view;
    document.querySelectorAll('.tabs a').forEach(a => {
      if (a.dataset.view === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (view === 'tableau') showBoard(currentBoard);
    if (view === 'reglages') loadSettings();
    last.radar = last.prices = last.journal = 0;
  }
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));

  // --- état général (accueil) ---
  let state = null;
  const RUNNING = 'en cours';
  const LONG = {pilote: 1, recherche: 1, 'labo-court': 1, 'labo-limites': 1, 'labo-long': 1};
  async function launch(action) {
    if (LONG[action.key] && !confirm(action.title + ' : ' + action.duration +
        '. Garde l\'ordinateur allumé et la fenêtre noire ouverte. Lancer ?')) return;
    try {
      const data = await post('/api/lancer', {action: action.key});
      toast('Lancé : ' + action.title);
      journalTask = data.task.id; journalNext = 0; logLines = [];
      location.hash = '#journal';
      refreshState();
    } catch (e) { toast(e.message, true); }
  }
  async function stopTask(task) {
    if (!confirm('Arrêter « ' + task.title + ' » ?')) return;
    try { await post('/api/arreter', {tache: task.id}); toast('Arrêt demandé : ' + task.title); refreshState(); }
    catch (e) { toast(e.message, true); }
  }
  function actionButton(action, primary, label) {
    return el('button', {class: 'btn' + (primary ? ' btn-primary' : ''), type: 'button', disabled: !!action.blocked,
      title: action.blocked || null, onclick: () => launch(action), text: label || 'Lancer'});
  }
  function chip(kind, text) {
    const style = {ok: 'chip-good', bad: 'chip-critical', warn: 'chip-warning', idle: 'chip-muted'}[kind] || '';
    return el('span', {class: 'chip ' + style}, el('span', {text: kind === 'live' ? '●' : kind === 'ok' ? '✓' :
      kind === 'bad' ? '✕' : '•'}), text);
  }
  function taskChip(task) {
    if (task.status === RUNNING) return chip('live', 'en cours');
    if (task.status === 'terminé') return chip('ok', 'terminé');
    if (task.status === 'échec') return chip('bad', 'échec');
    return chip('idle', task.status);
  }
  function renderNext(s) {
    $('#next-title').textContent = s.next.title;
    $('#next-text').textContent = s.next.text;
    const box = $('#next-actions'); box.replaceChildren();
    const action = s.next.action && s.actions.find(a => a.key === s.next.action);
    if (action) box.append(actionButton(action, true, action.title));
    if (s.next.view) box.append(el('a', {class: 'btn', href: '#' + s.next.view,
      text: s.next.view === 'journal' ? 'Voir le journal' : 'Voir le tableau de bord'}));
    const warning = $('#settings-warning');
    warning.hidden = !s.settings_error;
    warning.textContent = s.settings_error ? 'Réglages invalides : ' + s.settings_error : '';
  }
  function renderTasks(tasks) {
    const box = $('#tasks'); box.replaceChildren();
    const shown = tasks.filter(t => t.status === RUNNING).concat(tasks.filter(t => t.status !== RUNNING).slice(0, 3));
    if (!shown.length) {
      box.append(el('p', {class: 'empty-box', text: 'Rien ne tourne pour l\'instant. Le plus simple : le pilote automatique, en haut.'}));
      return;
    }
    for (const t of shown) {
      const running = t.status === RUNNING;
      const timing = running ? 'depuis ' + duration(t.seconds) : 'durée ' + duration(t.seconds) + ' · fini le ' + when(t.finished);
      box.append(el('article', {class: 'card'},
        el('div', {class: 'card-head'}, el('h3', {text: t.title}), taskChip(t)),
        el('p', {class: 'muted', text: timing + (t.steps > 1 ? ' · étape ' + t.step + '/' + t.steps : '')}),
        el('p', {class: 'lastline mono', text: t.last || '…'}),
        el('div', {class: 'row'},
          el('button', {class: 'btn', type: 'button', text: 'Journal', onclick: () => {
            journalTask = t.id; journalNext = 0; logLines = []; location.hash = '#journal'; }}),
          running ? el('button', {class: 'btn btn-stop', type: 'button', text: 'Arrêter', onclick: () => stopTask(t)}) : null)));
    }
  }
  function renderResults(s) {
    const box = $('#results'); box.replaceChildren();
    for (const lab of s.labs) {
      const card = el('article', {class: 'card'}, el('h3', {text: lab.title}));
      if (!lab.done) {
        card.append(el('p', {class: 'muted', text: 'Pas encore lancé.'}));
      } else {
        card.append(el('p', {class: 'muted', text: when(lab.date) + ' · ' + lab.tested + ' essais'}));
        card.append(el('p', {}, el('strong', {text: lab.retained === 0 ? 'Aucune stratégie retenue' :
          lab.retained === 1 ? '1 stratégie retenue' : lab.retained + ' stratégies retenues'}),
          lab.retained ? ' : ' + lab.names.join(', ') + (lab.retained > lab.names.length ? '…' : '') :
            ' : aucune ne gagne après frais'));
        if (lab.best) card.append(el('p', {class: 'muted', text: 'Meilleure avant frais : ' + pctPoints(lab.best.gross) +
          ' par trade, après frais ' + pctPoints(lab.best.net) + ' (' + lab.best.variant + ', ' + lab.best.timeframe + ')'}));
      }
      box.append(card);
    }
    for (const t of s.tournaments) {
      const card = el('article', {class: 'card'},
        el('div', {class: 'card-head'}, el('h3', {text: t.title}), t.running ? chip('live', 'en cours') : null));
      card.append(el('p', {class: 'muted', text: t.started ? (t.running ? '' : 'À l\'arrêt · ') + 'départ le ' +
        when(t.started) + ' · ' + t.strategies + (t.strategies > 1 ? ' stratégies' : ' stratégie') + ' × ' +
        t.markets + (t.markets > 1 ? ' cryptos' : ' crypto') : 'Jamais lancé.'}));
      if (t.dashboard) card.append(el('div', {class: 'row'}, el('button', {class: 'btn', type: 'button',
        text: 'Voir son tableau de bord', onclick: () => { currentBoard = t.folder; location.hash = '#tableau'; showBoard(t.folder); }})));
      box.append(card);
    }
  }
  function renderActions(s) {
    const box = $('#actions'); box.replaceChildren();
    for (const group of s.groups) {
      const cards = el('div', {class: 'cards'});
      for (const a of s.actions.filter(x => x.group === group)) {
        cards.append(el('article', {class: 'card'},
          el('h3', {text: a.title}), el('p', {text: a.description}), el('p', {class: 'muted', text: a.duration}),
          a.blocked ? el('p', {class: 'why-not', text: a.blocked}) : null,
          el('div', {class: 'row'}, actionButton(a, a.key === 'pilote'))));
      }
      box.append(el('h3', {class: 'group-title', text: group}), cards);
    }
  }
  async function refreshState() {
    try {
      state = await getJSON('/api/etat');
      $('#mode-badge').textContent = state.mode_label;
      renderNext(state); renderTasks(state.tasks); renderResults(state); renderActions(state);
      renderJournalList(state.tasks);
    } catch (e) {
      $('#next-title').textContent = 'Le site ne répond plus';
      $('#next-text').textContent = 'La fenêtre noire du bot a peut-être été fermée. Relance « Ouvrir le bot ».';
    }
  }

  // --- journal ---
  let journalTask = null, journalNext = 0, logLines = [];
  function renderJournalList(tasks) {
    const box = $('#journal-tasks'); box.replaceChildren();
    if (!tasks.length) { box.append(el('p', {class: 'muted', text: 'Aucune tâche lancée depuis le site.'})); return; }
    if (journalTask === null) journalTask = tasks[0].id;
    for (const t of tasks) {
      box.append(el('button', {type: 'button', 'aria-pressed': String(t.id === journalTask), onclick: () => {
        journalTask = t.id; journalNext = 0; logLines = []; $('#log').textContent = ''; renderJournalList(state.tasks);
        last.journal = 0; }}, el('strong', {text: t.title}), el('br'),
        el('span', {class: 'muted', text: t.status + ' · ' + when(t.started)})));
    }
  }
  async function refreshJournal() {
    if (journalTask === null) return;
    const data = await getJSON('/api/journal?tache=' + journalTask + '&depuis=' + journalNext);
    if (!data.lines.length && journalNext) return;
    const log = $('#log');
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
    logLines = logLines.concat(data.lines);
    if (logLines.length > 3000) logLines = logLines.slice(-3000);
    journalNext = data.next;
    log.textContent = logLines.length ? logLines.join('\n') : 'Démarrage…';
    if (atBottom || logLines.length === data.lines.length) log.scrollTop = log.scrollHeight;
  }

  // --- radar ---
  let radarWindow = 300, radarReady = false, pricesReady = false;
  const WINDOW_LABELS = {60: '1 min', 300: '5 min', 900: '15 min'};
  function radarControls() {
    const box = $('#radar-windows'); box.replaceChildren();
    for (const w of [60, 300, 900]) {
      box.append(el('button', {type: 'button', 'aria-pressed': String(w === radarWindow), text: WINDOW_LABELS[w],
        onclick: () => { radarWindow = w; radarControls(); last.radar = 0; }}));
    }
  }
  $('#radar-rising').addEventListener('change', () => { last.radar = 0; });
  async function refreshRadar() {
    const rising = $('#radar-rising').checked ? 1 : 0;
    const data = await getJSON('/api/radar?fenetre=' + radarWindow + '&hausses=' + rising);
    $('#radar-intro').textContent = 'Toutes les cryptos de ' + data.exchange + ' cotées en USDT et échangées à plus de ' +
      '5 M$ par jour, relevées toutes les 10 secondes. Classées par variation sur ' + WINDOW_LABELS[data.window] + '.';
    const filled = Math.min(100, Math.round(data.span / 900 * 100));
    let status = data.tracked ? data.tracked + ' cryptos suivies' + (data.updated ? ' · mis à jour à ' +
      new Date(data.updated).toLocaleTimeString('fr-FR') : '') : 'Démarrage du radar…';
    radarReady = data.tracked > 0;
    if (data.tracked && filled < 100) status += ' · radar rempli à ' + filled + ' % (il lui faut 15 min de relevés ; ' +
      'en attendant, classement sur 24 h)';
    if (data.error) status += ' · problème : ' + data.error;
    $('#radar-status').textContent = status;
    $('#radar-head').replaceChildren(el('tr', {}, el('th', {text: 'Crypto'}), el('th', {class: 'n', text: 'Prix'}),
      ...[60, 300, 900].map(w => el('th', {class: 'n win' + (w === data.window ? ' focus' : ''), text: WINDOW_LABELS[w]})),
      el('th', {class: 'n', text: '24 h'}), el('th', {class: 'n vol', text: 'Volume 24 h'})));
    const body = $('#radar-rows'); body.replaceChildren();
    for (const m of data.moves) {
      const cells = [el('td', {class: 'pair', text: m.symbol.split('/')[0]}), el('td', {class: 'n', text: price(m.last)})];
      for (const w of ['60', '300', '900']) {
        const v = m.changes[w];
        cells.push(el('td', {class: 'n win ' + cls(v) + (Number(w) === data.window ? ' focus' : ''), text: pct(v)}));
      }
      cells.push(el('td', {class: 'n ' + cls(m.change_24h), text: pct(m.change_24h, 1)}));
      cells.push(el('td', {class: 'n vol', text: money(m.volume_24h)}));
      body.append(el('tr', {class: m.strong ? 'strong' : null}, ...cells));
    }
    if (!data.moves.length) body.append(el('tr', {}, el('td', {colspan: '7', class: 'muted',
      text: data.error ? 'Radar indisponible : ' + data.error : 'Premiers relevés en cours…'})));
  }

  // --- prix ---
  async function refreshPrices() {
    const data = await getJSON('/api/prix');
    const b = data.board;
    pricesReady = !!b;
    $('#prices-table').hidden = !b;
    $('#prices-status').textContent = b ? 'Mis à jour à ' + new Date(data.updated).toLocaleTimeString('fr-FR') +
      (data.error ? ' · problème : ' + data.error : '') : (data.error ? 'Problème : ' + data.error : 'Connexion aux plateformes… (10 à 20 s la première fois)');
    if (!b) return;
    $('#prices-head').replaceChildren(el('tr', {}, el('th', {text: 'Crypto'}),
      ...b.platforms.map(p => el('th', {class: 'n', text: p.name})), el('th', {class: 'n', text: 'Écart'}),
      el('th', {class: 'n', text: '24 h'})));
    const body = $('#prices-rows'); body.replaceChildren();
    for (const row of b.rows) {
      body.append(el('tr', {}, el('td', {class: 'pair', text: row.base}),
        ...b.platforms.map(p => { const q = row.prices[p.id]; return el('td', {class: 'n', text: q ? price(q.price) + (q.usd ? ' $' : '') : '—'}); }),
        el('td', {class: 'n', text: row.spread === null ? '—' : pct(row.spread)}),
        el('td', {class: 'n ' + cls(row.change), text: pct(row.change, 1)})));
    }
    $('#prices-errors').replaceChildren(...Object.entries(b.errors).map(([name, problem]) =>
      el('li', {text: name + ' indisponible : ' + problem})));
  }

  // --- tableau de bord ---
  let currentBoard = 'bots';
  try { currentBoard = localStorage.getItem('board') || 'bots'; } catch (e) {}
  function showBoard(which) {
    currentBoard = which;
    try { localStorage.setItem('board', which); } catch (e) {}
    document.querySelectorAll('#board-choice button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.board === which)));
    const src = '/tableau/' + which;
    const frame = $('#board-frame');
    if (frame.getAttribute('src') !== src) frame.setAttribute('src', src);
    $('#board-open').setAttribute('href', src);
  }
  document.querySelectorAll('#board-choice button').forEach(b => b.addEventListener('click', () => showBoard(b.dataset.board)));

  // --- réglages ---
  async function loadSettings() {
    let data;
    try { data = await getJSON('/api/reglages'); } catch (e) { toast(e.message, true); return; }
    $('#mode-line').textContent = 'Mode : ' + data.mode_label + '. Pour changer de mode (testnet, démo, réel) ou mettre ' +
      'des clés API, ouvre le fichier .env : le site ne passe jamais en argent réel.';
    $('#open-env').hidden = !data.local;
    const form = $('#settings-form'); form.replaceChildren();
    for (const f of data.fields) {
      const id = 'f-' + f.key;
      const input = el('input', {id: id, name: f.key, type: f.kind === 'secret' ? 'password' : 'text',
        autocomplete: 'off', spellcheck: 'false', value: f.kind === 'secret' ? '' : f.value,
        placeholder: f.kind === 'secret' ? (f.set ? 'déjà réglé : laisse vide pour le garder' : 'pas encore réglé') :
          (f.default ? f.default + ' (par défaut)' : null)});
      form.append(el('div', {class: 'field'}, el('label', {for: id, text: f.title}), input,
        el('span', {class: 'muted', text: f.help})));
    }
  }
  $('#settings-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const values = {};
    for (const input of event.target.querySelectorAll('input')) values[input.name] = input.value;
    try { const r = await post('/api/reglages', {values: values}); toast('Réglages enregistrés (' + (r.saved.length || 0) + ').'); loadSettings(); refreshState(); }
    catch (e) { toast(e.message, true); }
  });
  $('#open-env').addEventListener('click', async () => {
    try { await post('/api/ouvrir-reglages'); toast('Le fichier .env s\'ouvre dans le Bloc-notes.'); }
    catch (e) { toast(e.message, true); }
  });

  // --- thème ---
  $('#theme-toggle').addEventListener('click', () => {
    const root = document.documentElement;
    const next = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch (e) {}
  });

  // --- rythme : chaque source seulement quand sa page est affichée ---
  const last = {state: 0, journal: 0, radar: 0, prices: 0};
  const busy = {};
  async function every(name, ms, fn) {
    const now = Date.now();
    if (busy[name] || now - last[name] < ms) return;
    busy[name] = true; last[name] = now;
    try { await fn(); } catch (e) { if (name === 'radar') $('#radar-status').textContent = e.message;
      if (name === 'prices') $('#prices-status').textContent = e.message; }
    finally { busy[name] = false; }
  }
  function tick() {
    if (document.hidden) return;
    every('state', 4000, refreshState);
    if (view === 'journal') every('journal', 1500, refreshJournal);
    if (view === 'radar') every('radar', radarReady ? 10000 : 2000, refreshRadar);
    if (view === 'prix') every('prices', pricesReady ? 10000 : 2000, refreshPrices);
  }
  radarControls();
  show(location.hash.slice(1));
  tick();
  setInterval(tick, 500);
})();
"""

HEAD = (
    '<!doctype html><html lang="fr" data-theme="dark"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    "<title>Bot de trading</title>"
    "<script>try { const t = localStorage.getItem('theme'); if (t) document.documentElement.dataset.theme = t; }"
    " catch (e) {}</script>"
)


def render_page() -> str:
    return HEAD + "<style>" + DASHBOARD_CSS + SITE_CSS + "</style></head><body>" + BODY + "<script>" + JS + \
        "</script></body></html>"


def simple_page(title: str, body: str) -> str:
    return (HEAD.replace("<title>Bot de trading</title>", f"<title>{title}</title>") + "<style>" + DASHBOARD_CSS
            + SITE_CSS + "</style></head><body><main>" + body + "</main></body></html>")


def empty_dashboard() -> str:
    return simple_page("Tableau de bord", (
        '<div class="hero"><p class="eyebrow">Tableau de bord</p><h1>Rien à montrer ici pour l\'instant</h1>'
        "<p>Ce tableau apparaît dès le premier tour du tournoi (ou des bots). Lance-le depuis l'accueil du site.</p>"
        "</div>"))


def code_page() -> str:
    return simple_page("Code du bot", (
        '<div class="hero"><p class="eyebrow">Accès depuis un autre appareil</p><h1>Entre le code du bot</h1>'
        "<p>Il est affiché dans la fenêtre noire du bot, sur l'ordinateur. L'appareil s'en souviendra.</p>"
        '<form class="row" method="get" action="/"><div class="field"><input name="code" inputmode="numeric" '
        'autocomplete="one-time-code" aria-label="Code à 6 chiffres" maxlength="6" required></div>'
        '<button class="btn btn-primary" type="submit">Entrer</button></form></div>'))
