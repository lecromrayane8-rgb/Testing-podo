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
.link { background: none; border: 0; padding: 0; font: inherit; font-weight: 600; color: var(--text-primary);
  text-decoration: underline; text-decoration-color: var(--accent); text-underline-offset: 3px; cursor: pointer; }
.link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
dialog.sheet { width: min(920px, calc(100vw - 24px)); max-height: calc(100vh - 24px); padding: 18px 20px;
  border: 1px solid var(--border); border-radius: 14px; background: var(--page); color: var(--text-primary); }
dialog.sheet::backdrop { background: rgba(0, 0, 0, 0.6); }
@media (max-width: 600px) { dialog.sheet { padding: 14px 12px; } }
.sheet-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 12px; }
.sheet-head h2 { margin: 2px 0 0; font-size: 20px; }
.verdict-box { margin: 12px 0; padding: 12px 14px; border-radius: 10px; background: var(--surface-1);
  border: 1px solid var(--border); border-left: 4px solid var(--warning); }
.verdict-box p { margin: 0; }
.verdict-box .verdict-label { font-weight: 700; margin-bottom: 4px; }
.verdict-box.v-bad { border-left-color: var(--critical); }
.verdict-box.v-good { border-left-color: var(--good); }
.mini-chart { position: relative; background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
  padding: 8px; margin: 8px 0 4px; }
.mini-chart svg { display: block; width: 100%; height: auto; font-size: 12px; outline-offset: 4px; }
.band { fill: var(--series-1); opacity: 0.14; }
.trial-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 760px) { .trial-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.small-print { color: var(--text-secondary); font-size: 12px; }
#journal-intro { margin-bottom: 10px; }
#study-windows button { white-space: nowrap; }
table.options td:first-child { white-space: normal; min-width: 200px; }
.option-cards { display: none; gap: 10px; margin-bottom: 8px; }
@media (max-width: 600px) { .options-wrap, #study-windows .long { display: none; } .option-cards { display: grid; } }
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
    <a href="#essais" data-view="essais"><span class="long">Mes </span>essais</a>
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
      <p class="note">Barre jaune : gros mouvement (au moins 1 % en 1 min, 2 % en 5 min ou 4 % en 15 min). Touche le nom
        d'une crypto pour étudier son mouvement sur 30 jours d'historique et l'essayer en argent fictif. Un mouvement
        affiché ici a déjà eu lieu ; le radar ne passe aucun ordre.</p>
    </section>
    <section>
      <h2>Ce que les mouvements jaunes ont donné ensuite</h2>
      <p class="meta" id="journal-intro"></p>
      <div class="table-wrap"><table><thead><tr><th>Mouvement</th><th class="n">Vus</th><th class="n">5 min après</th>
        <th class="n">15 min après</th><th class="n">1 h après</th></tr></thead><tbody id="journal-rows"></tbody></table></div>
      <p class="note">Chaque case : ce qu'aurait rapporté, en moyenne, un achat juste après chaque gros mouvement à la
        hausse, frais et glissement compris, puis la part des cas gagnants. Relevé en direct, sans jamais regarder le
        futur : un vrai test, qui grandit chaque jour où le site reste ouvert.</p>
    </section>
  </div>
  <div id="view-essais" class="view" hidden>
    <h1>Mes essais en argent fictif</h1>
    <p class="meta">Essaie les opportunités du radar avec un compte fictif : achat au prix réel du moment, frais et
      glissement compris, puis sortie automatique selon l'option choisie (stop, essoufflement, temps maximum). Rien ne
      part jamais sur une vraie plateforme.</p>
    <section><div class="trial-kpis" id="trial-kpis"></div></section>
    <section><h2>En cours</h2><div id="trial-open"></div></section>
    <section><h2>Le compte fictif après chaque essai</h2><div id="trial-curve"></div></section>
    <section><h2>Essais terminés</h2><div id="trial-done"></div></section>
    <div class="row"><button class="btn btn-stop" id="trial-reset" type="button">Remettre le compte fictif à zéro</button></div>
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
<dialog id="study" class="sheet" aria-labelledby="study-title">
  <div class="sheet-head">
    <div><p class="eyebrow">Étude d'une opportunité</p><h2 id="study-title">…</h2></div>
    <button class="btn" type="button" id="study-close">Fermer</button>
  </div>
  <div class="controls"><div class="seg" role="group" aria-label="Mouvement étudié" id="study-windows"></div></div>
  <div id="study-body" aria-live="polite"></div>
</dialog>
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
    const r = await fetch(path, {cache: 'no-store', headers: {'X-Demande': 'site-du-bot'}});
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
  const VIEWS = ['accueil', 'radar', 'prix', 'essais', 'tableau', 'journal', 'reglages'];
  let view = 'accueil';
  function show(name) {
    view = VIEWS.includes(name) ? name : 'accueil';
    for (const v of VIEWS) $('#view-' + v).hidden = v !== view;
    document.querySelectorAll('.tabs a').forEach(a => {
      if (a.dataset.view === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (view === 'tableau') showBoard(currentBoard);
    if (view === 'reglages') loadSettings();
    last.radar = last.prices = last.journal = last.trials = 0;
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
      const name = el('button', {class: 'link', type: 'button', text: m.symbol.split('/')[0],
        'aria-label': 'Étudier ' + m.symbol, onclick: () => openStudy(m.symbol, m.rise || data.window, m)});
      const cells = [el('td', {class: 'pair'}, name), el('td', {class: 'n', text: price(m.last)})];
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
    renderJournal(data.journal, data.pending);
  }
  function renderJournal(j, pending) {
    if (!j) return;
    $('#journal-intro').textContent = j.count ? j.count + ' gros mouvements jugés depuis le ' + when(j.since) +
      (pending ? ' · ' + pending + ' en cours d\'observation' : '') + '.' :
      'Le journal se remplit : chaque gros mouvement à la hausse est jugé 5 min, 15 min et 1 h après. ' +
      (pending ? pending + ' en cours d\'observation. ' : '') + 'Reviens dans une heure.';
    const body = $('#journal-rows'); body.replaceChildren();
    for (const row of j.rows) {
      const cells = [el('td', {text: 'Hausse de ' + pct(row.threshold, 0).replace('+', '') + ' en ' + WINDOW_LABELS[row.window]}),
        el('td', {class: 'n', text: String(row.count)})];
      for (const h of ['300', '900', '3600']) {
        const c = row.after[h];
        cells.push(el('td', {class: 'n'}, c ? el('strong', {class: cls(c.mean), text: pct(c.mean)}) : '—',
          c ? el('span', {class: 'small-print', text: ' · ' + Math.round(100 * c.winners) + ' % gagnants'}) : null));
      }
      body.append(el('tr', {}, ...cells));
    }
  }

  // --- graphiques : une série en ligne de 2 px, sa bande pâle, une ligne de référence nommée, une info-bulle ---
  const SVG = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs, ...children) {
    const node = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) node.setAttribute(k, v);
    for (const c of children) if (c !== null && c !== undefined) node.append(c);
    return node;
  }
  function niceTicks(lo, hi, count) {
    const raw = (hi - lo || Math.abs(hi) || 1) / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(st => st >= raw);
    const ticks = [];
    for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) ticks.push(Math.round(t / step) * step);
    return ticks;
  }
  function lineChart(o) {
    const W = Math.max(280, Math.round(o.width || 640)), small = W < 520;
    const H = small ? 220 : 260, ML = small ? 46 : 58, MR = small ? 76 : 170, MT = 14, MB = 28;
    const ys = o.ys.concat(o.band ? o.band[0].concat(o.band[1]) : [], o.refs.map(r => r.y));
    let lo = Math.min(...ys), hi = Math.max(...ys);
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.1 || 0.001;
    lo -= pad; hi += pad;
    const n = o.xs.length - 1, x0 = o.xs[0], x1 = o.xs[n];
    const X = x => ML + (x1 === x0 ? 0.5 : (x - x0) / (x1 - x0)) * (W - ML - MR);
    const Y = y => MT + (hi - y) / (hi - lo) * (H - MT - MB);
    const root = svg('svg', {viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': o.label, tabindex: '0'});
    const ticks = niceTicks(lo, hi, 6), step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
    for (const t of ticks) {
      root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(t), y2: Y(t), class: Math.abs(t) < 1e-12 ? 'zero' : 'grid'}));
      root.append(svg('text', {x: ML - 8, y: Y(t) + 4, 'text-anchor': 'end', class: 'tick'}, o.yTick(t, step)));
    }
    for (const t of (small && o.xTicksSmall) || o.xTicks) {
      root.append(svg('text', {x: X(t), y: H - 8, 'text-anchor': 'middle', class: 'tick'}, o.xTick(t)));
    }
    if (o.band) {
      const top = o.xs.map((x, i) => X(x) + ',' + Y(o.band[1][i]));
      const bottom = o.xs.map((x, i) => X(x) + ',' + Y(o.band[0][i])).reverse();
      root.append(svg('polygon', {points: top.concat(bottom).join(' '), class: 'band'}));
    }
    const endY = Y(o.ys[n]);
    for (const r of o.refs) {
      const y = Y(r.y);
      root.append(svg('line', {x1: ML, x2: W - MR, y1: y, y2: y, class: 'cost'}));
      const nudge = Math.abs(y - endY) < 16 ? (y < endY ? -8 : 8) : 0;  // l'étiquette ne recouvre pas celle de la ligne
      root.append(svg('text', {x: W - MR + 8, y: y + 4 + nudge, class: 'cost-label'}, small ? r.short : r.label));
    }
    root.append(svg('polyline', {points: o.xs.map((x, i) => X(x) + ',' + Y(o.ys[i])).join(' '), class: 'line',
      stroke: 'var(--series-1)'}));
    root.append(svg('circle', {cx: X(o.xs[n]), cy: endY, r: 4, fill: 'var(--series-1)', class: 'end'}));
    const clash = o.refs.some(r => Math.abs(Y(r.y) - endY) < 16 && Y(r.y) >= endY);
    root.append(svg('text', {x: W - MR + 8, y: endY + 4 + (o.refs.length && Math.abs(Y(o.refs[0].y) - endY) < 16 ?
      (clash ? -8 : 8) : 0), class: 'end-label'}, small && o.endShort ? o.endShort : o.endLabel));
    const cross = svg('line', {y1: MT, y2: H - MB, class: 'crosshair'});
    root.append(cross);
    const box = el('div', {class: 'mini-chart'}), tip = el('div', {class: 'tip', hidden: true});
    box.append(root, tip);
    let index = n;
    function show(i) {
      index = Math.max(0, Math.min(n, i));
      const x = X(o.xs[index]);
      cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.style.visibility = 'visible';
      tip.replaceChildren(...o.tip(index).map((line, k) => el('div', {class: k ? 'tip-row' : 'tip-date', text: line})));
      tip.hidden = false;
      const r = root.getBoundingClientRect(), host = box.getBoundingClientRect();
      const left = r.left - host.left + x / W * r.width;
      tip.style.left = (left + tip.offsetWidth + 16 > host.width ? Math.max(4, left - tip.offsetWidth - 12) : left + 12) + 'px';
      tip.style.top = '8px';
    }
    function hide() { cross.style.visibility = 'hidden'; tip.hidden = true; }
    root.addEventListener('pointermove', e => {
      const r = root.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W;
      let best = 0;
      for (let i = 1; i <= n; i++) if (Math.abs(X(o.xs[i]) - px) < Math.abs(X(o.xs[best]) - px)) best = i;
      show(best);
    });
    root.addEventListener('pointerleave', hide);
    root.addEventListener('focus', () => show(index));
    root.addEventListener('blur', hide);
    root.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft') { show(index - 1); e.preventDefault(); }
      if (e.key === 'ArrowRight') { show(index + 1); e.preventDefault(); }
    });
    return box;
  }

  // --- étude d'une opportunité (fiche ouverte depuis le radar) ---
  const study = $('#study');
  let studySymbol = null, studyWindow = 300, studyTimer = null, studyTicket = 0, studyMove = null;
  const VERDICTS = {bad: ['✕', 'Mauvais signe'], good: ['✓', 'Une piste, pas une preuve'], neutral: ['•', 'Rien de net'],
    few: ['…', 'Trop peu de cas']};
  function studyControls() {
    const box = $('#study-windows'); box.replaceChildren();
    for (const w of [60, 300, 900]) {
      box.append(el('button', {type: 'button', 'aria-pressed': String(w === studyWindow),
        onclick: () => { studyWindow = w; studyControls(); loadStudy(); }},
        el('span', {class: 'long', text: pct(STRONG[w], 0) + ' en '}), WINDOW_LABELS[w]));
    }
  }
  const STRONG = {60: 0.01, 300: 0.02, 900: 0.04};
  function openStudy(symbol, window, move) {
    studySymbol = symbol; studyWindow = window; studyMove = move || null;
    const now = move && move.changes[String(window)];
    $('#study-title').textContent = symbol.split('/')[0] + (now !== null && now !== undefined ?
      ' · ' + pct(now) + ' en ' + WINDOW_LABELS[window] : '');
    studyControls();
    if (!study.open) study.showModal();
    loadStudy();
  }
  $('#study-close').addEventListener('click', () => study.close());
  study.addEventListener('close', () => { clearTimeout(studyTimer); studyTicket++; });
  function loadStudy() {
    clearTimeout(studyTimer);
    $('#study-body').replaceChildren(el('p', {class: 'muted', text: 'Étude en cours : 30 jours de bougies de 1 minute ' +
      'de ' + studySymbol + ', les mêmes hausses dans le passé, et trois façons d\'en sortir testées… (10 à 30 s la ' +
      'première fois)'}));
    pollStudy(++studyTicket);
  }
  async function pollStudy(ticket) {
    if (!study.open || ticket !== studyTicket) return;
    let data;
    try {
      data = await getJSON('/api/etude?symbole=' + encodeURIComponent(studySymbol) + '&fenetre=' + studyWindow);
    } catch (e) { if (ticket === studyTicket) renderStudyError(e.message); return; }
    if (ticket !== studyTicket) return;  // une autre fiche ou une autre fenêtre a été demandée entre-temps
    if (data.status === 'prêt') renderStudy(data.result);
    else if (data.status === 'erreur') renderStudyError(data.error);
    else {
      if (data.message) $('#study-body').firstChild.textContent = data.message;
      studyTimer = setTimeout(() => pollStudy(ticket), 1500);
    }
  }
  function renderStudyError(message) {
    $('#study-body').replaceChildren(el('div', {class: 'verdict-box v-bad'},
      el('p', {class: 'verdict-label', text: 'Étude impossible'}), el('p', {text: message})));
  }
  function renderStudy(r) {
    const body = $('#study-body'); body.replaceChildren();
    const now = studyMove && studyMove.changes[String(r.window)];
    if (now !== null && now !== undefined && now < 0) body.append(el('p', {class: 'warn', text: r.symbol.split('/')[0] +
      ' baisse en ce moment (' + pct(now) + ') : cette étude porte sur ses hausses passées. Le bot n\'achète qu\'à la ' +
      'hausse : il ne parie jamais sur une baisse.'}));
    const [icon, label] = VERDICTS[r.verdict.kind] || ['•', ''];
    body.append(el('div', {class: 'verdict-box v-' + r.verdict.kind},
      el('p', {class: 'verdict-label', text: icon + ' ' + label}), el('p', {text: r.verdict.text})));
    body.append(el('p', {class: 'muted', text: r.events + ' hausses pareilles sur les ' + r.days + ' derniers jours (' +
      r.bars.toLocaleString('fr-FR') + ' bougies de 1 min). Un aller-retour coûte environ ' + pct(r.cost).replace('+', '') +
      ' en frais et glissement.'}));
    if (r.path) {
      const m = r.path.minutes;
      body.append(el('h3', {class: 'chart-title', text: 'Ce que le prix a fait dans l\'heure qui a suivi l\'achat'}));
      body.append(lineChart({
        width: body.clientWidth - 18, xs: m, ys: r.path.median, band: [r.path.q25, r.path.q75],
        refs: [{y: r.cost, label: 'frais d\'un aller-retour', short: 'frais'}],
        xTicks: [1, 15, 30, 45, 60], xTicksSmall: [1, 30, 60], xTick: t => t + ' min',
        yTick: (t, step) => pct(t, step >= 0.0095 ? 0 : step >= 0.00095 ? 1 : 2),
        endLabel: 'médiane ' + pct(r.path.median[m.length - 1]), endShort: pct(r.path.median[m.length - 1]),
        label: 'Variation médiane du prix après ' + r.events + ' hausses pareilles, minute par minute',
        tip: i => ['après ' + m[i] + ' min', 'médiane ' + pct(r.path.median[i]),
          'la moitié des cas entre ' + pct(r.path.q25[i]) + ' et ' + pct(r.path.q75[i])],
      }));
      body.append(el('p', {class: 'small-print', text: 'Ligne : la médiane des cas, sans aucune sortie. Bande : la moitié ' +
        'des cas, ceux du milieu. Pour gagner, le prix doit passer au-dessus de la ligne des frais. Les options ci-dessous ' +
        'sortent plus tôt (stop, essoufflement) : leurs résultats diffèrent de cette courbe.'}));
    }
    body.append(el('h3', {class: 'chart-title', text: 'Trois façons de sortir, testées sur le même historique'}));
    const rows = r.options.map(o => {
      const risk = riskText(o.plan);
      const button = el('button', {class: 'btn' + (o.key === 'normale' ? ' btn-primary' : ''), type: 'button',
        disabled: !o.plan, text: 'Essayer', onclick: () => tryOption(r, o)});
      return el('tr', {}, el('td', {}, el('strong', {text: o.title}), el('br'), el('span', {class: 'small-print', text: o.description})),
        el('td', {class: 'n'}, String(o.trades), el('br'), el('span', {class: 'small-print',
          text: o.winners === null ? '' : Math.round(100 * o.winners) + ' % gagnants'})),
        el('td', {class: 'n'}, el('strong', {class: cls(o.mean), text: pct(o.mean)}), el('br'),
          el('span', {class: 'small-print', text: 'avant frais ' + pct(o.gross_mean)})),
        el('td', {class: 'n ' + cls(o.worst), text: pct(o.worst)}),
        el('td', {class: 'n', text: risk}), el('td', {}, button));
    });
    body.append(el('div', {class: 'option-cards'}, ...r.options.map(o => el('div', {class: 'card'},
      el('div', {class: 'card-head'}, el('h3', {text: o.title}), el('strong', {class: cls(o.mean), text: pct(o.mean)})),
      el('p', {class: 'small-print', text: o.description}),
      el('p', {class: 'muted', text: o.trades + ' trades' + (o.winners === null ? '' : ' · ' + Math.round(100 * o.winners) +
        ' % gagnants') + ' · avant frais ' + pct(o.gross_mean) + ' · pire ' + pct(o.worst)}),
      el('p', {class: 'muted', text: 'Si le stop est touché : ' + riskText(o.plan)}),
      el('div', {class: 'row'}, el('button', {class: 'btn' + (o.key === 'normale' ? ' btn-primary' : ''), type: 'button',
        disabled: !o.plan, text: 'Essayer en argent fictif', onclick: () => tryOption(r, o)}))))));
    body.append(el('div', {class: 'table-wrap options-wrap'}, el('table', {class: 'options'},
      el('thead', {}, el('tr', {}, el('th', {text: 'Option'}), el('th', {class: 'n', text: 'Trades'}),
        el('th', {class: 'n', text: 'Moyenne par trade'}), el('th', {class: 'n', text: 'Pire trade'}),
        el('th', {class: 'n', text: 'Si le stop est touché'}), el('th', {text: ''}))),
      el('tbody', {}, ...rows))));
    body.append(el('p', {class: 'small-print', text: 'Moyennes par trade sur l\'historique, mêmes règles que le bot en ' +
      'direct. « Si le stop est touché » : la perte d\'un essai maintenant, sur ton compte fictif. Le passé ne garantit ' +
      'rien ; un essai se fait en argent fictif, rien ne part sur une vraie plateforme.'}));
  }
  function riskText(plan) {
    return plan ? MINUS + usdt(plan.loss_if_stop) + ' (' + pct(-plan.loss_pct) + ')' : '—';
  }
  async function tryOption(r, o) {
    const p = o.plan;
    const text = 'Essai en ARGENT FICTIF sur ' + r.symbol + ', ' + o.title.toLowerCase() + '.\n\n' +
      'Achat d\'environ ' + usdt(p.notional) + ' au prix du moment.\n' +
      'Stop à ' + price(p.stop) + ' (' + pct(p.stop_pct) + ') : s\'il est touché, tu perds environ ' + usdt(p.loss_if_stop) +
      ' fictifs (' + pct(p.loss_pct).replace('+', '') + ' du compte).\n' +
      'Sortie automatique : ' + o.description + '.\n\n' +
      (o.trades >= 20 ? 'Dans le passé, cette option a donné ' + pct(o.mean) + ' par trade en moyenne après frais (' +
        o.trades + ' trades).' : 'L\'historique ne dit presque rien de ce mouvement (' + o.trades + ' trades) : c\'est un ' +
        'essai à l\'aveugle.') + ' Rien ne part sur une vraie plateforme. Lancer l\'essai ?';
    if (!confirm(text)) return;
    try {
      await post('/api/essais/ouvrir', {symbole: r.symbol, fenetre: r.window, option: o.key});
      study.close();
      toast('Essai lancé en argent fictif : ' + r.symbol);
      location.hash = '#essais';
    } catch (e) { toast(e.message, true); }
  }

  // --- mes essais ---
  function usdt(v, signed) {
    if (v === null || v === undefined || !isFinite(v)) return '—';
    const s = Math.abs(v).toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' USDT';
    return signed ? (v > 0 ? '+' : v < 0 ? MINUS : '') + s : (v < 0 ? MINUS : '') + s;
  }
  function tile(label, value, sub, hero) {
    return el('div', {class: 'tile' + (hero ? ' tile-hero' : '')}, el('p', {class: 'tile-label', text: label}),
      el('p', {class: 'tile-value', text: value}), el('p', {class: 'tile-sub', text: sub}));
  }
  async function refreshTrials() {
    const d = await getJSON('/api/essais');
    const st = d.stats;
    $('#trial-kpis').replaceChildren(
      tile('Compte fictif', usdt(d.equity), 'départ ' + usdt(d.start) + ' le ' + when(d.since)),
      tile('Résultat', usdt(d.result, true), pct(d.result_pct)),
      tile('Essais terminés', String(st.n), d.positions.length + ' en cours (' + d.max_open + ' au plus)'),
      tile('Gagnants', st.n ? st.winners + ' sur ' + st.n : '—', st.n ? 'en moyenne ' + pct(st.mean) + ' par essai' : 'aucun essai terminé'));
    const open = $('#trial-open'); open.replaceChildren();
    if (!d.positions.length) open.append(el('p', {class: 'empty-box', text: 'Aucun essai en cours. Dans le radar, touche le ' +
      'nom d\'une crypto qui bouge, regarde son étude, puis « Essayer ».'}));
    else open.append(el('div', {class: 'table-wrap'}, el('table', {},
      el('thead', {}, el('tr', {}, ...['Crypto', 'Option', 'Achat', 'Prix', 'Résultat', 'Stop', 'Depuis', ''].map((h, i) =>
        el('th', {class: i >= 2 && i <= 6 ? 'n' : null, text: h})))),
      el('tbody', {}, ...d.positions.map(p => el('tr', {},
        el('td', {class: 'pair', text: p.symbol}), el('td', {text: p.option_title}),
        el('td', {class: 'n', text: price(p.entry)}), el('td', {class: 'n', text: price(p.price)}),
        el('td', {class: 'n'}, el('strong', {class: cls(p.pnl), text: usdt(p.pnl, true)}),
          el('span', {class: 'small-print', text: ' ' + pct(p.return)})),
        el('td', {class: 'n', text: price(p.stop)}),
        el('td', {class: 'n', text: duration(Math.max(0, Math.round(Date.now() / 1000 - p.opened_ts)))}),
        el('td', {}, el('button', {class: 'btn', type: 'button', text: 'Vendre', onclick: () => sellTrial(p)}))))))));
    const curve = $('#trial-curve'); curve.replaceChildren();
    if (!d.curve.length) curve.append(el('p', {class: 'empty-box', text: 'La courbe apparaît après le premier essai terminé.'}));
    else {
      const xs = [0].concat(d.curve.map((_, i) => i + 1)), ys = [d.start].concat(d.curve.map(c => c.equity));
      const trades = d.trades.slice().reverse();
      curve.append(lineChart({
        width: curve.clientWidth - 18, xs: xs, ys: ys, band: null,
        refs: [{y: d.start, label: 'départ : ' + usdt(d.start), short: 'départ'}],
        xTicks: [0].concat(niceTicks(1, xs.length - 1, 4).filter(t => t >= 1 && t <= xs.length - 1 && Number.isInteger(t))),
        xTick: t => t ? 'n° ' + t : 'départ', yTick: t => Math.round(t).toLocaleString('fr-FR'),
        endLabel: usdt(ys[ys.length - 1]), endShort: Math.round(ys[ys.length - 1]).toLocaleString('fr-FR'),
        label: 'Compte fictif après chaque essai terminé',
        tip: i => i ? ['après l\'essai n° ' + i, usdt(ys[i]), trades[i - 1].symbol + ' : ' + usdt(trades[i - 1].pnl, true)] :
          ['au départ', usdt(ys[0])],
      }));
    }
    const done = $('#trial-done'); done.replaceChildren();
    if (!d.trades.length) done.append(el('p', {class: 'empty-box', text: 'Aucun essai terminé pour l\'instant.'}));
    else done.append(el('div', {class: 'table-wrap'}, el('table', {},
      el('thead', {}, el('tr', {}, ...['Fin', 'Crypto', 'Option', 'Résultat', 'Durée', 'Sortie'].map((h, i) =>
        el('th', {class: i === 3 || i === 4 ? 'n' : null, text: h})))),
      el('tbody', {}, ...d.trades.slice(0, 50).map(t => el('tr', {},
        el('td', {text: when(t.closed)}), el('td', {class: 'pair', text: t.symbol}), el('td', {text: t.option_title}),
        el('td', {class: 'n'}, el('strong', {class: cls(t.pnl), text: usdt(t.pnl, true)}),
          el('span', {class: 'small-print', text: ' ' + pct(t.return)})),
        el('td', {class: 'n', text: duration(Math.round(t.minutes * 60))}), el('td', {text: t.reason_text})))))));
  }
  async function sellTrial(p) {
    if (!confirm('Revendre l\'essai sur ' + p.symbol + ' au prix du moment (argent fictif) ?')) return;
    try { const r = await post('/api/essais/vendre', {id: p.id}); toast('Vendu : ' + usdt(r.trade.pnl, true)); last.trials = 0; }
    catch (e) { toast(e.message, true); }
  }
  $('#trial-reset').addEventListener('click', async () => {
    if (!confirm('Remettre le compte fictif à zéro ? Les essais en cours et l\'historique des essais sont effacés.')) return;
    try { await post('/api/essais/zero'); toast('Compte fictif remis à zéro.'); last.trials = 0; }
    catch (e) { toast(e.message, true); }
  });

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
  const last = {state: 0, journal: 0, radar: 0, prices: 0, trials: 0};
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
    if (view === 'essais') every('trials', 5000, refreshTrials);
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
