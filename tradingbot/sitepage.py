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
.tabs .short { display: none; }
@media (max-width: 600px) {
  .tabs { flex-wrap: wrap; }
  .tabs .long, .win:not(.focus), .vol { display: none; }
  .tabs .short { display: inline; }
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
.cards.wide { grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); }
.card.know p { font-size: 14px; }
.card.know.full { grid-column: 1 / -1; }
.card.know.full p { max-width: 900px; }
.card.know .sources { font-size: 12px; color: var(--text-secondary); }
.card.know .sources a { color: var(--text-secondary); text-underline-offset: 2px; }
.card.know .lab-says { margin-top: 4px; padding-top: 8px; border-top: 1px solid var(--grid); }
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
.tabs .more { background: none; border: 0; padding: 8px 12px; color: var(--text-secondary); font: inherit;
  font-size: 14px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; }
.tabs .more[aria-expanded="true"] { color: var(--text-primary); }
.tabs .more::after { content: " ▾"; }
.tabs-more { margin-top: 0; padding-bottom: 2px; flex-wrap: wrap; }
.tabs[hidden] { display: none; }
.tabs-more a { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-bottom: 8px; }
.section-head h2 { margin: 0; }
.trade { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px;
  margin-bottom: 10px; }
.trade p { margin: 4px 0 0; }
.trade .head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.trade .head h3 { margin: 0; font-size: 15px; }
.trade .result { font-weight: 700; font-variant-numeric: tabular-nums; }
.trade details { margin-top: 6px; }
.trade summary { cursor: pointer; color: var(--text-secondary); font-size: 13px; }
.trade ul { margin: 6px 0 0; padding-left: 18px; color: var(--text-secondary); font-size: 14px; }
.lesson-line { margin: 0 0 6px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
.swatch.line { height: 3px; border-radius: 2px; }
ul.reading { margin: 0; padding-left: 18px; }
ul.reading li { margin-bottom: 6px; max-width: 860px; }
select { font: inherit; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--page);
  color: var(--text-primary); max-width: 220px; }
.lesson { max-width: 820px; }
.lesson h1 { margin-bottom: 4px; }
.lesson p { font-size: 16px; line-height: 1.6; }
.lesson .example { background: var(--surface-1); border: 1px solid var(--border); border-left: 4px solid var(--series-1);
  border-radius: 10px; padding: 10px 14px; }
.lesson .example strong { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--text-secondary); margin-bottom: 2px; }
.lesson .remember { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px 10px 32px; }
.quiz { margin-top: 12px; }
.quiz .q { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
  margin-bottom: 10px; }
.quiz .q p { margin: 0 0 8px; font-weight: 600; }
.quiz .choices { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.quiz .choices button { text-align: left; }
.quiz .choices button[aria-pressed="true"].right { border-color: var(--good); }
.quiz .choices button[aria-pressed="true"].wrong { border-color: var(--critical); }
.quiz .why { margin-top: 8px; color: var(--text-secondary); font-size: 14px; }
.sim { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; margin: 12px 0; }
.sim label { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 12px; margin-bottom: 10px; font-size: 14px; }
.sim input[type=range] { grid-column: 1 / -1; width: 100%; accent-color: var(--accent); }
.sim .out { font-size: 16px; margin: 6px 0 0; }
.sim .question { color: var(--text-secondary); font-size: 14px; margin: 0 0 10px; }
.done-mark { color: var(--good); font-weight: 700; }
.news-item { padding: 10px 0; border-bottom: 1px solid var(--grid); }
.news-item a { color: var(--text-primary); font-weight: 600; text-decoration: none; }
.news-item a:hover { text-decoration: underline; }
.news-item .meta-line { color: var(--text-secondary); font-size: 13px; margin-top: 2px; }
.coin { display: inline-flex; gap: 4px; align-items: baseline; margin-right: 10px; font-size: 13px; }
.meter { position: relative; height: 10px; border-radius: 999px; background: var(--grid); margin: 14px 0 6px; }
.meter .mark { position: absolute; top: -5px; width: 4px; height: 20px; border-radius: 2px; background: var(--text-primary);
  transform: translateX(-2px); }
.meter-scale { display: flex; justify-content: space-between; color: var(--text-secondary); font-size: 12px; }
.fng-value { font-size: 40px; font-weight: 600; margin: 0; line-height: 1.1; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); margin-right: 6px;
  vertical-align: 0.05em; }
.dot-live { animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.35; } }
.fleet-kpis { display: grid; grid-template-columns: minmax(0, 2fr) repeat(3, minmax(0, 1fr)); gap: 12px; }
.fleet-kpis .tile-hero { grid-column: auto; }
@media (max-width: 760px) { .fleet-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .fleet-kpis .tile-hero { grid-column: span 2; } }
.pill { display: inline-flex; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--border); font-size: 13px;
  color: var(--text-primary); white-space: nowrap; }
.botcard .big .delta { font-size: 14px; margin-left: 6px; }
@media (max-width: 600px) { .tabs a, .tabs .more { padding: 8px 9px; } }
.warn-top { margin: 0 0 16px; }
.squad { margin-top: 28px; }
.squad-head { display: flex; justify-content: space-between; align-items: baseline; gap: 4px 12px; flex-wrap: wrap; }
.squad-head h2 { margin: 0; }
.squad-head h2 a { color: var(--text-primary); text-decoration: none; }
.squad-head h2 a:hover { text-decoration: underline; text-decoration-color: var(--accent); }
.bot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 12px;
  margin-top: 10px; }
.botcard { gap: 4px; }
.botcard h3 a { color: var(--text-primary); text-decoration: none; }
.botcard .big { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; margin: 2px 0 0; }
.spark svg { display: block; width: 100%; height: 56px; }
.spark.muted { height: 56px; display: flex; align-items: center; }
.pos-line { font-size: 14px; font-variant-numeric: tabular-nums; }
.events { list-style: none; margin: 0; padding: 0; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 12px; }
.events li { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: 10px; padding: 8px 14px;
  border-bottom: 1px solid var(--grid); font-size: 14px; }
.events li:last-child { border-bottom: 0; }
.events time { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.events .ev-sortie span, .events .ev-remplacement span { color: var(--text-primary); }
@media (max-width: 600px) { .events li { grid-template-columns: minmax(0, 1fr); gap: 0; } }
.panel { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px;
  margin-top: 16px; }
.panel > p { margin: 6px 0 0; max-width: 900px; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px 16px; flex-wrap: wrap; }
.panel-head h2 { margin: 2px 0 0; font-size: 20px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.bot-chart { margin-top: 12px; }
.bot-chart .mini-chart { margin: 0; }
.position-box { margin-top: 12px; padding: 12px 14px; border-radius: 10px; border: 1px solid var(--border);
  background: var(--page); }
.position-box p { margin: 0; }
.facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 170px), 1fr)); gap: 8px 16px;
  margin-top: 8px; }
.fact .k { margin: 0; color: var(--text-secondary); font-size: 12px; }
.fact .v { margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; }
.compare { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
.compare .tile { background: var(--page); }
@media (max-width: 600px) { .compare { grid-template-columns: minmax(0, 1fr); } }
.panel .trade { background: var(--page); }
.crumb { margin: 0 0 8px; }
.choice-team { margin-top: 18px; }
.choice-team h3 { margin: 0 0 6px; font-size: 16px; }
@media (prefers-reduced-motion: reduce) { .dot-live { animation: none; } }
"""

BODY = """
<header class="site-top"><div class="site-top-inner">
  <div class="brand-row">
    <p class="brand">Trading bot <span class="badge" id="mode-badge">…</span></p>
    <button id="theme-toggle" class="theme" type="button">Clair / sombre</button>
  </div>
  <nav class="tabs" aria-label="Pages du site">
    <a href="#direct" data-view="direct">Direct</a>
    <a href="#long" data-view="long"><span class="long">Long terme</span><span class="short">Long</span></a>
    <a href="#court" data-view="court"><span class="long">Court terme</span><span class="short">Court</span></a>
    <a href="#scalping" data-view="scalping">Scalping</a>
    <a href="#labos" data-view="labos">Labos</a>
    <button type="button" class="more" id="more-toggle" aria-expanded="false" aria-controls="more-tabs">Plus</button>
  </nav>
  <nav class="tabs tabs-more" id="more-tabs" aria-label="Autres pages" hidden>
    <a href="#accueil" data-view="accueil">Mon trader</a>
    <a href="#graphiques" data-view="graphiques">Graphiques</a>
    <a href="#ecole" data-view="ecole">École</a>
    <a href="#actualite" data-view="actualite">Actualité</a>
    <a href="#radar" data-view="radar">Radar</a>
    <a href="#prix" data-view="prix">Prix</a>
    <a href="#essais" data-view="essais"><span class="long">Mes essais</span><span class="short">Essais</span></a>
    <a href="#savoir" data-view="savoir">Comprendre</a>
    <a href="#tableau" data-view="tableau">Tableau<span class="long"> de bord</span></a>
    <a href="#journal" data-view="journal">Journal</a>
    <a href="#reglages" data-view="reglages">Réglages</a>
  </nav>
</div></header>
<main class="site">
  <div id="settings-warning" class="warn warn-top" hidden></div>
  <div id="view-direct" class="view">
    <div class="hero" aria-live="polite">
      <p class="eyebrow">En direct · argent fictif</p>
      <h1 id="fleet-title">Chargement…</h1>
      <p id="fleet-text"></p>
      <div class="row" id="fleet-actions"></div>
    </div>
    <section><div class="fleet-kpis" id="fleet-kpis"></div></section>
    <div id="fleet-teams"></div>
    <section><h2>Ce qui vient de se passer</h2><ol class="events" id="fleet-events"></ol></section>
    <p class="note">Chaque bot a 1000 USDT fictifs (réglable) et met tout son capital à chaque trade, avec le levier de son
      équipe : un stop touché peut coûter plusieurs pourcents de son capital, et un bot peut être liquidé. Il est alors
      remplacé par le suivant du classement. Le meilleur de milliers de backtests est souvent chanceux : c'est le direct
      qui tranche.</p>
  </div>
  <div id="view-equipe" class="view" hidden>
    <h1 id="team-title">…</h1>
    <p class="meta" id="team-intro"></p>
    <div id="team-bots"></div>
  </div>
  <div id="view-bot" class="view" hidden>
    <p class="crumb"><a class="link" href="#direct" id="bot-back">← Tous les bots</a></p>
    <div id="bot-page"><p class="muted">Chargement…</p></div>
  </div>
  <div id="view-accueil" class="view" hidden>
    <div class="hero" aria-live="polite">
      <p class="eyebrow">Prochaine étape</p>
      <h1 id="next-title">Chargement…</h1>
      <p id="next-text"></p>
      <div class="row" id="next-actions"></div>
    </div>
    <section id="trader-section">
      <div class="section-head"><h2>Ton trader fictif</h2>
        <div class="seg" role="group" aria-label="Compte affiché" id="trader-mode">
          <button type="button" data-mode="live" aria-pressed="true">En direct</button>
          <button type="button" data-mode="replay" aria-pressed="false">Rejeu sur l'historique</button>
        </div></div>
      <p class="meta" id="trader-intro">Chargement…</p>
      <div class="trial-kpis" id="trader-kpis"></div>
      <div id="trader-curve"></div>
      <h3 class="group-title">Positions ouvertes</h3><div id="trader-positions"></div>
      <h3 class="group-title">Derniers trades, expliqués</h3><div id="trader-trades"></div>
      <h3 class="group-title">Ce que le trader a appris</h3><div id="trader-lessons"></div>
      <h3 class="group-title">Ses stratégies</h3><div id="trader-plays" class="cards"></div>
    </section>
    <section><h2>En cours et récent</h2><div id="tasks" class="cards"></div></section>
  </div>
  <div id="view-labos" class="view" hidden>
    <h1>Labos et tests</h1>
    <p class="meta">Comment tes 15 bots ont été choisis, ce que les autres labos ont trouvé sur l'historique réel, et
      toutes les actions du bot.</p>
    <section><h2>Le choix des 15 bots</h2><div id="fleet-choice"><p class="muted">Chargement…</p></div></section>
    <section><h2>Les autres labos</h2><div id="results" class="cards"></div></section>
    <section><h2>Toutes les actions</h2><div id="actions"></div></section>
  </div>
  <div id="view-graphiques" class="view" hidden>
    <h1>Graphiques</h1>
    <p class="meta">Chaque crypto comme un trader la lit : les bougies, les supports (en dessous) et les résistances
      (au-dessus), les moyennes sur 50 et 200 bougies, et ce qu'en disent les règles de ton trader. Une lecture pour
      comprendre : le trader n'achète que sur ses règles testées.</p>
    <div class="controls">
      <label class="check" for="chart-symbol">Crypto <select id="chart-symbol"></select></label>
      <div class="seg" role="group" aria-label="Unité de temps" id="chart-tf"></div>
    </div>
    <p class="status-line" id="chart-status" aria-live="polite">Choisis une crypto.</p>
    <div id="chart-box"></div>
    <div class="legend" id="chart-legend"></div>
    <section><h2>Ce que voit un trader</h2><ul class="reading" id="chart-reading"></ul></section>
    <section><h2>Ce que disent les règles de ton trader</h2><div id="chart-plays" class="cards"></div></section>
  </div>
  <div id="view-ecole" class="view" hidden>
    <div id="school-home">
      <h1>L'école du trading</h1>
      <p class="meta">Des leçons courtes, dans l'ordre : ce qu'est le trading, une crypto, un graphique, les supports,
        le stop, le levier, les frais… Chacune finit par un mini-quiz. Rien ici n'est un conseil d'investissement.</p>
      <div id="school-list" class="cards"></div>
    </div>
    <article id="lesson" class="lesson" hidden></article>
  </div>
  <div id="view-actualite" class="view" hidden>
    <h1>Actualité</h1>
    <p class="meta">Les derniers titres de CoinDesk, Cointelegraph et Decrypt, les cryptos qu'ils citent et ce que leur
      prix a fait depuis la publication, et l'humeur du marché. Pour comprendre ce qui se passe : ton trader ne trade pas
      sur les titres (quand on les lit, le mouvement a souvent déjà eu lieu).</p>
    <section><h2>L'humeur du marché</h2><div id="fng-box"><p class="muted">Chargement…</p></div></section>
    <section><h2>Derniers titres</h2><p class="status-line" id="news-status" aria-live="polite"></p>
      <div id="news-list" class="news"></div></section>
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
  <div id="view-savoir" class="view" hidden>
    <h1>Comprendre les courbes</h1>
    <p class="meta">D'abord la base des bots : les idées tirées d'études publiées (relues par des pairs, avec leurs liens),
      devenues des règles que ton labo teste. Puis, technique par technique : ce qu'elle mesure, comment la lire, ce que
      dit la recherche et ce qu'en dit ton labo, sur tes données. Rien ici n'est un conseil d'achat : la recherche donne
      des pistes, seul le test tranche.</p>
    <div id="savoir-cards"><p class="muted">Chargement…</p></div>
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
  function typo(value) {  // à la française : jamais de « % » ou de « : » seul en début de ligne
    return String(value).replace(/ ([%$»:;?!])/g, '\u00a0$1').replace(/« /g, '«\u00a0');
  }
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = typo(value);
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children) if (child !== null && child !== undefined) node.append(typeof child === 'string' ? typo(child) : child);
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
  const VIEWS = ['direct', 'equipe', 'bot', 'accueil', 'graphiques', 'ecole', 'actualite', 'labos', 'radar', 'prix',
    'essais', 'savoir', 'tableau', 'journal', 'reglages'];
  const TEAMS = {long: 'Long terme', court: 'Court terme', scalping: 'Scalping'};
  let view = 'direct', team = 'long', botSlot = null;
  function markTab() {
    const key = view === 'equipe' ? team : view === 'bot' ? (botSection() || 'direct') : view;
    document.querySelectorAll('.tabs a').forEach(a => {
      if (a.dataset.view === key) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
  }
  function show(name) {
    const parts = String(name || '').split('/'), sub = parts[1];
    if (TEAMS[parts[0]]) { view = 'equipe'; team = parts[0]; }
    else if (parts[0] === 'bot' && /^\d+$/.test(sub || '')) { view = 'bot'; botSlot = Number(sub); }
    else view = VIEWS.includes(parts[0]) && parts[0] !== 'equipe' && parts[0] !== 'bot' ? parts[0] : 'direct';
    for (const v of VIEWS) $('#view-' + v).hidden = v !== view;
    markTab();
    if (view === 'equipe' || view === 'bot' || view === 'direct') { renderFleet(); window.scrollTo(0, 0); }
    if (view === 'tableau') showBoard(currentBoard);
    if (view === 'reglages') loadSettings();
    if (view === 'savoir') loadKnowledge();
    if (MORE_VIEWS.includes(view)) setMore(true);
    if (view === 'ecole') loadSchool(sub).catch(e => toast(e.message, true));
    if (view === 'graphiques') {
      chartControls();
      loadMarkets().then(loadChart).catch(e => { $('#chart-status').textContent = e.message; });
    }
    last.radar = last.prices = last.journal = last.trials = last.trader = last.news = last.fleet = last.charts = 0;
    last.chart = Date.now();
  }
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));

  // --- état général (accueil) ---
  let state = null;
  const RUNNING = 'en cours';
  const LONG = {pilote: 1, recherche: 1, 'labo-court': 1, 'labo-limites': 1, 'labo-long': 1, 'flotte-choix': 1};
  async function launch(action) {
    if (LONG[action.key] && !confirm(action.title + ' : ' + action.duration +
        '. Garde l\'ordinateur allumé et la fenêtre noire ouverte. Lancer ?')) return;
    try {
      const data = await post('/api/lancer', {action: action.key});
      toast('Lancé : ' + action.title);
      journalTask = data.task.id; journalNext = 0; logLines = [];
      if (action.key === 'flotte') { location.hash = '#direct'; last.fleet = 0; }
      else location.hash = '#journal';
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
    if (s.portfolio) renderPortfolio(s.portfolio, box);
  }
  function pct2(v) {  // déjà en pourcentage, deux décimales
    if (v === null || v === undefined || !isFinite(v)) return '—';
    const s = Math.abs(v).toFixed(2);
    return (Number(s) === 0 ? '' : v > 0 ? '+' : MINUS) + s.replace('.', ',') + ' %';
  }
  function renderPortfolio(pf, box) {
    const lab = pf.lab;
    const card = el('article', {class: 'card'}, el('h3', {text: 'Labo portefeuille'}));
    if (!lab.done) {
      card.append(el('p', {class: 'muted', text: 'Pas encore lancé.'}));
    } else {
      card.append(el('p', {class: 'muted', text: when(lab.date) + ' · ' + lab.tested + ' variantes sur ' + lab.coins + ' cryptos'}));
      card.append(el('p', {}, el('strong', {text: lab.retained === 0 ? 'Aucune variante retenue' :
        lab.retained === 1 ? '1 variante retenue' : lab.retained + ' variantes retenues'}),
        lab.retained ? ' : ' + lab.names.join(', ') + (lab.retained > lab.names.length ? '…' : '') :
          ' : aucune ne bat le panier de toutes les cryptos, frais compris'));
      if (lab.best) card.append(el('p', {class: 'muted', text: 'Meilleure : ' + pct2(lab.best.mean) +
        ' par semaine après frais, contre ' + pct2(lab.best.basket) + ' pour le panier de toutes les cryptos (' +
        lab.best.variant + ', ' + lab.best.verdict + ')'}));
    }
    box.append(card);
    const run = el('article', {class: 'card'},
      el('div', {class: 'card-head'}, el('h3', {text: 'Portefeuille momentum'}), pf.running ? chip('live', 'en cours') : null));
    if (!pf.books.length) run.append(el('p', {class: 'muted', text: pf.running ? 'Démarrage…' : 'Jamais lancé.'}));
    for (const b of pf.books) {
      run.append(el('p', {}, el('strong', {text: b.variant}), el('br'),
        usdt(b.value) + ' fictifs, ', el('span', {class: cls(b.pnl_pct), text: pct2(b.pnl_pct)}),
        ' depuis le ' + when(b.since)));
      run.append(el('p', {class: 'muted', text: (b.holdings.length ? 'Garde ' + b.holdings.join(', ') : 'Rien en main') +
        ' · prochaine rotation le ' + when(b.next)}));
    }
    if (!pf.running && pf.books.some(b => b.retained)) run.append(el('p', {class: 'muted',
      text: 'À l\'arrêt : relance « Portefeuille momentum » pour qu\'il continue.'}));
    if (pf.books.some(b => !b.retained)) run.append(el('p', {class: 'muted',
      text: 'Le dernier labo portefeuille ne retient plus ' + (pf.books.filter(b => !b.retained).length > 1 ?
        'certaines de ces variantes : elles ne tournent plus.' : 'une de ces variantes : elle ne tourne plus.')}));
    box.append(run);
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

  // --- comprendre : la base de connaissances, reliée aux résultats des labos ---
  async function loadKnowledge() {
    let data;
    try { data = await getJSON('/api/savoir'); } catch (e) { toast(e.message, true); return; }
    const box = $('#savoir-cards'); box.replaceChildren();
    const links = sources => el('p', {class: 'sources'}, ...sources.flatMap((src, i) => [i ? ' · ' : null,
      el('a', {href: src.url, target: '_blank', rel: 'noopener', text: src.title})]));
    if (data.ideas && data.ideas.length) {
      const cards = el('div', {class: 'cards wide'});
      const STATUS = {retenue: ['ok', 'utilisée par les bots'], recalee: ['bad', 'recalée par ton labo'],
        defavorable: ['warn', 'recherche défavorable'], 'a-tester': ['idle', 'à tester'],
        info: ['idle', 'pour comprendre']};
      for (const idea of data.ideas) {
        const [kind, label] = STATUS[idea.status] || ['idle', idea.status];
        let best = '';
        if (idea.best_portfolio) best = ' Meilleure : ' + idea.best_portfolio.variant + ', ' + pct2(idea.best_portfolio.mean) +
          ' par semaine après frais (panier de toutes les cryptos : ' + pct2(idea.best_portfolio.basket) + ').';
        else if (idea.best_rule) best = ' Meilleure : ' + idea.best_rule.variant + ' en ' + idea.best_rule.timeframe + ', ' +
          pctPoints(idea.best_rule.net) + ' par trade après frais (' + idea.best_rule.verdict + ').';
        cards.append(el('article', {class: 'card know'},
          el('div', {class: 'card-head'}, el('h3', {text: idea.title}), chip(kind, label)),
          el('p', {}, el('strong', {text: 'Ce que les études ont trouvé. '}), idea.finding),
          idea.rules.length ? el('p', {}, el('strong', {text: 'Règles fixées d\'avance, testées par le bot. '}),
            idea.rules.join(' · ')) : null,
          el('p', {class: 'lab-says'}, el('strong', {text: 'Où elle en est : '}), idea.status_text + best),
          links(idea.sources)));
      }
      box.append(el('h3', {class: 'group-title', text: 'La base des bots : des études aux règles'}),
        el('p', {class: 'muted', text: 'Chaque idée vient d\'études publiées. Elle devient une règle chiffrée, fixée ' +
          'd\'après l\'étude et jamais ajustée sur tes données, que le labo teste. Les bots n\'utilisent que celles qui ' +
          'passent le labo.'}), cards);
    }
    for (const group of [...new Set(data.entries.map(e => e.group))]) {
      const cards = el('div', {class: 'cards wide'});
      for (const e of data.entries.filter(x => x.group === group)) {
        const lab = e.lab;
        let says = null;
        if (lab && lab.kind === 'portefeuille') {
          if (!lab.tested) says = 'pas encore testé : le labo portefeuille (ou le pilote automatique) s\'en charge.';
          else says = (lab.best ? 'meilleure variante ' + lab.best.variant + ' : ' + pct2(lab.best.mean) +
            ' par semaine après frais, contre ' + pct2(lab.best.basket) + ' pour le panier de toutes les cryptos (' +
            lab.best.verdict + '). ' : '') + (lab.retained ? lab.retained + ' variante(s) retenue(s) sur ' + lab.tested + '.' :
            'Aucune des ' + lab.tested + ' variantes n\'est retenue.');
        } else if (lab) {
          if (!lab.tested) says = 'pas encore testée dans tes labos.';
          else if (!lab.best) says = lab.tested + ' essais, trop peu de trades pour juger.';
          else says = 'meilleure version ' + lab.best.variant + ' en ' + lab.best.timeframe + ' : ' + pctPoints(lab.best.net) +
            ' par trade après frais (' + lab.best.verdict + ', ' + lab.best.lab.toLowerCase() + '). ' +
            (lab.retained ? lab.retained + ' version(s) retenue(s) sur ' + lab.tested + ' essais.' :
              'Aucune des ' + lab.tested + ' versions essayées n\'est retenue.');
        }
        cards.append(el('article', {class: 'card know' + (e.key === 'recherche' ? ' full' : '')},
          el('h3', {text: e.title}),
          el('p', {}, el('strong', {text: 'Ce que ça mesure. '}), e.measures),
          el('p', {}, el('strong', {text: 'Comment le lire. '}), e.reading),
          el('p', {}, el('strong', {text: 'Ce que dit la recherche. '}), e.research),
          links(e.sources),
          says ? el('p', {class: 'lab-says'}, el('strong', {text: 'Dans ton labo : '}), says) : null));
      }
      box.append(el('h3', {class: 'group-title', text: group}), cards);
    }
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

  // --- nouvelles pages : le trader, les graphiques, l'école, l'actualité ---
  const MORE_VIEWS = ['labos', 'radar', 'prix', 'essais', 'savoir', 'tableau', 'journal', 'reglages'];
  const moreToggle = $('#more-toggle'), moreTabs = $('#more-tabs');
  function setMore(open) { moreTabs.hidden = !open; moreToggle.setAttribute('aria-expanded', String(open)); }
  moreToggle.addEventListener('click', () => setMore(moreTabs.hidden));
  function signed(v, digits) {  // déjà en pourcentage
    if (v === null || v === undefined || !isFinite(v)) return '—';
    const s = Math.abs(v).toFixed(digits === undefined ? 2 : digits);
    if (Number(s) === 0) return s.replace('.', ',') + ' %';
    return (v > 0 ? '+' : MINUS) + s.replace('.', ',') + ' %';
  }
  function dec(v) { return v === null || v === undefined || !isFinite(v) ? '—' : (Math.round(v * 10) / 10).toLocaleString('fr-FR'); }
  function coin(symbol) { return String(symbol || '').split('/')[0]; }
  function spreadTicks(xs, k) {
    if (xs.length < 2) return xs.slice();
    const out = [];
    for (let i = 0; i < k; i++) out.push(xs[0] + (xs[xs.length - 1] - xs[0]) * (i + 0.5) / k);
    return out;
  }
  function dayLabel(ms) { return new Date(ms).toLocaleDateString('fr-FR', {day: '2-digit', month: '2-digit'}); }
  function monthLabel(ms) { return new Date(ms).toLocaleDateString('fr-FR', {month: 'short', year: '2-digit'}); }
  function tickPrice(v, step) {
    const d = Math.max(0, Math.min(8, -Math.floor(Math.log10(step || 1))));
    return v.toLocaleString('fr-FR', {minimumFractionDigits: d, maximumFractionDigits: d});
  }
  function keepOpen(root, render) {  // un rafraîchissement ne referme pas ce que l'utilisateur a déplié
    const open = new Set([...root.querySelectorAll('details[open]')].map(d => d.dataset.key));
    render();
    for (const d of root.querySelectorAll('details')) if (open.has(d.dataset.key)) d.open = true;
  }

  // --- le trader ---
  let traderMode = 'live', traderData = null, allTrades = false;
  $('#trader-mode').addEventListener('click', e => {
    const b = e.target.closest('button[data-mode]');
    if (!b) return;
    traderMode = b.dataset.mode;
    for (const x of $('#trader-mode').querySelectorAll('button')) x.setAttribute('aria-pressed', String(x === b));
    renderTrader();
  });
  async function refreshTrader() { traderData = await getJSON('/api/trader'); renderTrader(); }
  function renderTrader() { if (traderData) keepOpen($('#trader-section'), drawTrader); }
  function drawTrader() {
    const t = traderMode === 'live' ? traderData.live : traderData.replay, cfg = traderData.settings;
    const ids = ['#trader-kpis', '#trader-curve', '#trader-positions', '#trader-trades', '#trader-lessons', '#trader-plays'];
    for (const id of ids) $(id).replaceChildren();
    if (!t.exists) {
      $('#trader-intro').textContent = traderMode === 'live'
        ? 'Pas encore lancé. Dès qu\'un labo a retenu une stratégie, lance « Mon trader » : il la joue en argent fictif sur les '
          + cfg.coins + ' cryptos les plus échangées, et t\'explique ici chaque achat et chaque vente.'
        : 'Pas encore de rejeu. « Rejouer mon trader sur l\'historique » (page Labos et actions) montre en quelques minutes '
          + 'ce qu\'il aurait fait ces derniers mois, trade par trade, avec les explications.';
      return;
    }
    const s = t.settings || cfg;
    const lev = s.profile === 'futures' ? 'levier jusqu\'à ' + dec(s.max_leverage) + ' (futures)' : 'sans levier (au comptant)';
    $('#trader-intro').textContent = (traderMode === 'replay'
      ? 'Rejoué sur l\'historique récent avec les mêmes règles : forcément flatteur, ce n\'est pas une preuve. '
      : traderData.live.running ? 'Il tourne, en argent fictif. ' : 'À l\'arrêt : relance « Mon trader » pour qu\'il continue. ')
      + 'Risque de ' + dec(100 * s.risk_per_trade) + ' % par trade, ' + lev + ', ' + s.max_positions + ' positions au plus.'
      + (t.notice ? ' ' + t.notice : '');
    $('#trader-kpis').append(
      tile('Valeur du compte', usdt(t.value), 'au départ ' + usdt(t.start), true),
      tile('Depuis le départ', signed(t.pnl_pct), t.created ? 'depuis le ' + when(t.created) : ''),
      tile('Trades terminés', String(t.count), t.win_rate === null ? 'aucun encore' : Math.round(100 * t.win_rate) + ' % gagnants'),
      tile('Positions ouvertes', t.positions.length + ' / ' + s.max_positions,
        t.positions.length ? t.positions.map(p => coin(p.symbol)).join(', ') : 'aucune'));
    if (t.history && t.history.length >= 2) {
      const xs = t.history.map(h => Date.parse(h.t)), ys = t.history.map(h => h.value), box = $('#trader-curve');
      box.append(lineChart({width: box.clientWidth || 700, xs: xs, ys: ys,
        refs: [{y: t.start, label: 'Départ : ' + usdt(t.start), short: 'Départ'}], label: 'Valeur du compte fictif',
        xTicks: spreadTicks(xs, 4), xTicksSmall: spreadTicks(xs, 3), xTick: dayLabel,
        yTick: v => Math.round(v).toLocaleString('fr-FR'), endLabel: usdt(ys[ys.length - 1]),
        endShort: Math.round(ys[ys.length - 1]).toLocaleString('fr-FR'),
        tip: i => [when(new Date(xs[i]).toISOString()), usdt(ys[i])]}));
    }
    const positions = $('#trader-positions');
    if (!t.positions.length) positions.append(el('p', {class: 'muted', text: traderMode === 'live'
      ? 'Aucune position : le trader attend un signal de ses règles.' : 'Aucune position ouverte à la fin du rejeu.'}));
    for (const p of t.positions) positions.append(positionCard(p));
    const trades = $('#trader-trades'), shown = allTrades ? t.trades : t.trades.slice(0, 6);
    if (!t.trades.length) trades.append(el('p', {class: 'muted', text: 'Pas encore de trade terminé.'}));
    for (const x of shown) trades.append(tradeCard(x));
    if (t.trades.length > shown.length) trades.append(el('button', {class: 'btn', type: 'button',
      text: 'Voir les ' + (t.trades.length - shown.length) + ' autres trades', onclick: () => { allTrades = true; renderTrader(); }}));
    const lessons = $('#trader-lessons');
    if (!t.lessons.length) lessons.append(el('p', {class: 'muted', text: 'Pas encore de leçon : il faut des trades terminés.'}));
    for (const l of t.lessons) lessons.append(el('p', {class: 'lesson-line', text: l.text}));
    const plays = $('#trader-plays');
    if (!t.playbook.length) plays.append(el('p', {class: 'empty-box', text: 'Aucune stratégie retenue par les labos pour l\'instant : le trader attend.'}));
    for (const p of t.playbook) plays.append(el('article', {class: 'card'},
      el('div', {class: 'card-head'}, el('h3', {text: p.key}), chip(p.status === 'prometteur' ? 'ok' : 'warn', p.status)),
      el('p', {text: p.why}),
      el('p', {class: 'muted', text: (p.lab || '') + (p.expectancy === null || p.expectancy === undefined ? ''
        : ' · ' + signed(p.expectancy, 3) + ' par trade après frais dans le labo')})));
    const cut = Object.entries(t.eliminated || {});
    if (cut.length) plays.append(el('article', {class: 'card'}, el('h3', {text: 'Coupées par le gardien'}),
      ...cut.map(([key, why]) => el('p', {class: 'muted', text: key.replace('|', ' sur ') + ' : ' + why}))));
  }
  function readingList(lines) { return lines && lines.length ? el('ul', {}, ...lines.map(x => el('li', {text: x}))) : null; }
  function positionCard(p) {
    return el('article', {class: 'trade'},
      el('div', {class: 'head'}, el('h3', {text: coin(p.symbol) + ' · ' + p.play}),
        el('span', {class: 'result ' + cls(p.pnl_pct), text: signed(p.pnl_pct)})),
      el('p', {class: 'muted', text: 'Acheté le ' + when(p.entry_time) + ' à ' + price(p.entry_price) + ' · maintenant '
        + price(p.last_price) + ' · stop à ' + price(p.stop) + ' (' + signed(-100 * p.risk, 1) + ') · levier ×' + dec(p.leverage)}),
      el('p', {}, el('strong', {text: 'Pourquoi il est entré : '}), p.why || ''),
      p.reading && p.reading.length ? el('details', {'data-key': 'p' + p.id},
        el('summary', {text: 'Ce que montrait le graphique à l\'achat'}), readingList(p.reading)) : null,
      el('div', {class: 'row'}, el('button', {class: 'btn', type: 'button', text: 'Voir le graphique',
        onclick: () => openChart(p.symbol, p.timeframe)})));
  }
  function tradeCard(t) {
    const d = t.diagnosis || {};
    return el('article', {class: 'trade'},
      el('div', {class: 'head'}, el('h3', {text: coin(t.symbol) + ' · ' + t.play}),
        el('span', {class: 'result ' + cls(t.net), text: signed(100 * t.net) + ' · ' + (d.title || '')})),
      el('p', {text: d.text || ''}),
      d.lesson ? el('p', {class: 'muted'}, el('strong', {text: 'La leçon : '}), d.lesson) : null,
      el('p', {class: 'muted', text: 'Acheté le ' + when(t.entry_time) + ' à ' + price(t.entry_price) + ', vendu le '
        + when(t.exit_time) + ' à ' + price(t.exit_price) + ' (' + t.reason + ')'
        + (t.leverage > 1.05 ? ' · levier ×' + dec(t.leverage) : '')}),
      el('details', {'data-key': 't' + t.id + t.exit_time}, el('summary', {text: 'Pourquoi il est entré'}),
        el('p', {text: t.why || ''}), readingList(t.reading)),
      el('div', {class: 'row'}, el('button', {class: 'btn', type: 'button', text: 'Voir le graphique',
        onclick: () => openChart(t.symbol, t.timeframe)})));
  }

  // --- les graphiques ---
  const TFS = [['15m', '15 min'], ['1h', '1 h'], ['4h', '4 h'], ['1d', '1 jour']];
  let chartSymbol = null, chartTf = '4h', chartData = null;
  function chartControls() {
    const seg = $('#chart-tf');
    seg.replaceChildren(...TFS.map(([tf, label]) => el('button', {type: 'button', 'aria-pressed': String(tf === chartTf),
      text: label, onclick: () => { chartTf = tf; chartControls(); loadChart(); }})));
  }
  async function loadMarkets() {
    const data = await getJSON('/api/marches');
    const list = data.markets.length ? data.markets : [{symbol: 'BTC/USDT'}];
    chartSymbol = chartSymbol || (list.find(m => m.symbol === 'BTC/USDT') || list[0]).symbol;
    const select = $('#chart-symbol');
    select.replaceChildren(...list.map(m => el('option', {value: m.symbol, selected: m.symbol === chartSymbol,
      text: coin(m.symbol) + (m.change_24h === null || m.change_24h === undefined ? '' : ' (' + signed(100 * m.change_24h, 1) + ' sur 24 h)')})));
    if (!list.some(m => m.symbol === chartSymbol)) select.prepend(el('option', {value: chartSymbol, text: coin(chartSymbol), selected: true}));
  }
  $('#chart-symbol').addEventListener('change', e => { chartSymbol = e.target.value; loadChart(); });
  function openChart(symbol, tf) {
    chartSymbol = symbol;
    if (TFS.some(x => x[0] === tf)) chartTf = tf;
    location.hash = '#graphiques';
  }
  async function loadChart() {
    if (!chartSymbol) return;
    $('#chart-status').textContent = 'Chargement de ' + coin(chartSymbol) + '…';
    try {
      chartData = await getJSON('/api/graphique?symbole=' + encodeURIComponent(chartSymbol) + '&unite=' + chartTf);
    } catch (e) {
      $('#chart-status').textContent = e.message + ' Nouvel essai dans quelques secondes…';
      last.chart = Date.now() - 55000;  // le radar démarre peut-être : on réessaie dans 5 s plutôt que dans une minute
      return;
    }
    renderChart();
  }
  function chartLegend(d) {
    const item = (cls_, color, text) => el('span', {}, el('span', {class: 'swatch ' + cls_, style: 'background:' + color}), text);
    return [item('', 'var(--up)', 'bougie en hausse'), item('', 'var(--down)', 'bougie en baisse'),
      item('line', 'var(--series-1)', 'moyenne 50'), item('line', 'var(--series-7)', 'moyenne 200'),
      d.levels.some(z => z.kind === 'support') ? item('', 'var(--series-3)', 'support') : null,
      d.levels.some(z => z.kind === 'resistance') ? item('', 'var(--series-2)', 'résistance') : null,
      d.position ? item('line', 'var(--text-secondary)', 'ton achat et ton stop') : null,
      d.trades && d.trades.length ? el('span', {text: '▲ achat · ▼ vente du trader'}) : null];
  }
  function renderChart() {
    const d = chartData;
    if (!d) return;
    const tf = (TFS.find(x => x[0] === d.timeframe) || [0, d.timeframe])[1];
    $('#chart-status').textContent = coin(d.symbol) + ' en bougies de ' + tf + ' · dernier prix ' + price(d.last) + ' · '
      + d.levels.length + (d.levels.length > 1 ? ' zones touchées' : ' zone touchée') + ' au moins 2 fois';
    const box = $('#chart-box');
    box.replaceChildren(candleChart({...d, width: box.clientWidth || 900, label: 'Graphique de ' + coin(d.symbol) + ' en ' + tf}));
    $('#chart-legend').replaceChildren(...chartLegend(d).filter(Boolean));
    $('#chart-reading').replaceChildren(...d.reading.sentences.map(x => el('li', {text: x})));
    const plays = $('#chart-plays');
    plays.replaceChildren();
    if (!d.plays.length) plays.append(el('p', {class: 'empty-box', text: 'Aucune stratégie de ton trader dans cette unité de temps. '
      + 'Ses stratégies sont sur l\'accueil ; essaie leur unité de temps.'}));
    const SIGNALS = {achat: ['ok', 'signal d\'achat'], vente: ['bad', 'signal de vente'], rien: ['idle', 'rien pour l\'instant']};
    for (const p of d.plays) {
      const [kind, label] = SIGNALS[p.signal] || SIGNALS.rien;
      plays.append(el('article', {class: 'card'}, el('div', {class: 'card-head'}, el('h3', {text: p.key}), chip(kind, label)),
        el('p', {text: p.why || ''})));
    }
  }
  function tri(x, y, dir) { return 'M' + x + ',' + (y - 5 * dir) + 'L' + (x + 5) + ',' + (y + 4 * dir) + 'L' + (x - 5) + ',' + (y + 4 * dir) + 'Z'; }
  function candleChart(o) {
    const W = Math.max(300, Math.round(o.width)), small = W < 560;
    const H = small ? 300 : 400, MR = small ? 84 : 190, MT = 12, MB = 26;
    const c = o.candles, n = c.length;
    let lo = Math.min(...c.map(k => k[3])), hi = Math.max(...c.map(k => k[2]));
    const span0 = hi - lo || hi * 0.01 || 1;
    const zones = o.levels.filter(z => z.high >= lo - 0.25 * span0 && z.low <= hi + 0.25 * span0);
    for (const z of zones) { lo = Math.min(lo, z.low); hi = Math.max(hi, z.high); }
    if (o.position) { lo = Math.min(lo, o.position.stop); hi = Math.max(hi, o.position.entry_price); }
    const pad = (hi - lo) * 0.04 || Math.abs(hi) * 0.01 || 1;
    lo -= pad; hi += pad;
    const ticks = niceTicks(lo, hi, small ? 5 : 6), step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
    const tickText = ticks.map(t => tickPrice(t, step));
    const ML = Math.max(small ? 40 : 50, 14 + 6.8 * Math.max(...tickText.map(x => x.length)));
    const slot = (W - ML - MR) / n, body = Math.max(1, Math.min(8, slot * 0.66));
    const X = i => ML + slot * (i + 0.5), Y = v => MT + (hi - v) / (hi - lo) * (H - MT - MB);
    const root = svg('svg', {viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': o.label, tabindex: '0'});
    ticks.forEach((t, k) => {
      root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(t), y2: Y(t), class: 'grid'}));
      root.append(svg('text', {x: ML - 6, y: Y(t) + 4, 'text-anchor': 'end', class: 'tick'}, tickText[k]));
    });
    const labels = [];
    for (const z of zones) {
      const color = z.kind === 'support' ? 'var(--series-3)' : 'var(--series-2)', top = Y(z.high), bottom = Y(z.low);
      root.append(svg('rect', {x: ML, width: W - MR - ML, y: top, height: Math.max(2, bottom - top), fill: color, opacity: 0.16}));
      root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(z.price), y2: Y(z.price), stroke: color, 'stroke-width': 1}));
      labels.push({y: Y(z.price), color: color, text: small ? price(z.price) + ' ×' + z.touches
        : (z.kind === 'support' ? 'Support ' : 'Résistance ') + price(z.price) + ' · ' + z.touches + ' fois'});
    }
    for (const [series, color] of [[o.ma200, 'var(--series-7)'], [o.ma50, 'var(--series-1)']]) {
      let pts = [];
      const flush = () => { if (pts.length > 1) root.append(svg('polyline', {points: pts.join(' '), class: 'line', stroke: color})); pts = []; };
      (series || []).forEach((v, i) => { if (v === null || v === undefined) flush(); else pts.push(X(i) + ',' + Y(v)); });
      flush();
    }
    c.forEach((k, i) => {
      const color = k[4] >= k[1] ? 'var(--up)' : 'var(--down)';
      root.append(svg('line', {x1: X(i), x2: X(i), y1: Y(k[2]), y2: Y(k[3]), stroke: color, 'stroke-width': 1}));
      const top = Y(Math.max(k[1], k[4])), bottom = Y(Math.min(k[1], k[4]));
      root.append(svg('rect', {x: X(i) - body / 2, width: body, y: top, height: Math.max(1, bottom - top), fill: color}));
    });
    if (o.position) {
      for (const [v, color, text] of [[o.position.entry_price, 'var(--text-secondary)', (small ? 'Achat ' : 'Ton achat ') + price(o.position.entry_price)],
                                      [o.position.stop, 'var(--down)', 'Stop ' + price(o.position.stop)]]) {
        root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(v), y2: Y(v), stroke: color, 'stroke-width': 1}));
        labels.push({y: Y(v), color: color, text: text});
      }
    }
    const ts = c.map(k => k[0]);
    const at = t => { if (t === null || t === undefined || t < ts[0]) return -1; let i = 0; while (i + 1 < n && ts[i + 1] <= t) i++; return i; };
    for (const tr of o.trades || []) {
      const a = at(tr.entry), b = at(tr.exit);
      if (a >= 0) root.append(svg('path', {d: tri(X(a), Y(c[a][3]) + 11, 1), fill: 'var(--text-primary)', stroke: 'var(--surface-1)', 'stroke-width': 2}));
      if (b >= 0) root.append(svg('path', {d: tri(X(b), Y(c[b][2]) - 11, -1), fill: tr.net > 0 ? 'var(--up)' : 'var(--down)', stroke: 'var(--surface-1)', 'stroke-width': 2}));
    }
    labels.sort((a, b) => a.y - b.y);
    let lastY = -Infinity;
    for (const l of labels) {
      const y = Math.min(H - MB, Math.max(l.y, lastY + 15));
      lastY = y;
      root.append(svg('rect', {x: W - MR + 6, y: y - 5, width: 10, height: 10, rx: 2, fill: l.color}));
      root.append(svg('text', {x: W - MR + 20, y: y + 4, class: 'tick'}, l.text));
    }
    const intraday = ts.length > 1 && ts[1] - ts[0] < 86400000;
    const fmt = ms => { const d = new Date(ms); return intraday ? dayLabel(ms) + ' ' + String(d.getHours()).padStart(2, '0') + 'h' : dayLabel(ms); };
    for (let k = 0; k < (small ? 3 : 5); k++) {
      const i = Math.round((n - 1) * (k + 0.5) / (small ? 3 : 5));
      root.append(svg('text', {x: X(i), y: H - 8, 'text-anchor': 'middle', class: 'tick'}, fmt(ts[i])));
    }
    const cross = svg('line', {y1: MT, y2: H - MB, class: 'crosshair'});
    root.append(cross);
    const wrap = el('div', {class: 'mini-chart'}), tip = el('div', {class: 'tip', hidden: true});
    wrap.append(root, tip);
    let index = n - 1;
    function showAt(i) {
      index = Math.max(0, Math.min(n - 1, i));
      const k = c[index], x = X(index);
      cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.style.visibility = 'visible';
      tip.replaceChildren(el('div', {class: 'tip-date', text: new Date(k[0]).toLocaleString('fr-FR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'})}),
        el('div', {class: 'tip-row', text: 'Ouverture ' + price(k[1]) + ' · clôture ' + price(k[4])}),
        el('div', {class: 'tip-row', text: 'Plus haut ' + price(k[2]) + ' · plus bas ' + price(k[3])}),
        el('div', {class: 'tip-row', text: 'Sur la bougie : ' + signed(100 * (k[4] / k[1] - 1))}));
      tip.hidden = false;
      const r = root.getBoundingClientRect(), host = wrap.getBoundingClientRect();
      const left = r.left - host.left + x / W * r.width;
      tip.style.left = (left + tip.offsetWidth + 16 > host.width ? Math.max(4, left - tip.offsetWidth - 12) : left + 12) + 'px';
      tip.style.top = '8px';
    }
    function hide() { cross.style.visibility = 'hidden'; tip.hidden = true; }
    root.addEventListener('pointermove', e => {
      const r = root.getBoundingClientRect();
      showAt(Math.round(((e.clientX - r.left) / r.width * W - ML) / slot - 0.5));
    });
    root.addEventListener('pointerleave', hide);
    root.addEventListener('focus', () => showAt(index));
    root.addEventListener('blur', hide);
    root.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft') { showAt(index - 1); e.preventDefault(); }
      if (e.key === 'ArrowRight') { showAt(index + 1); e.preventDefault(); }
    });
    return wrap;
  }

  // --- les 15 bots ---
  let fleetData = null;
  const botCharts = {};  // bot -> {at, data, error}
  function botSection() {
    const b = fleetData && fleetData.bot;
    return b ? b.section : null;
  }
  async function refreshFleet() {
    fleetData = await getJSON('/api/bots' + (view === 'bot' && botSlot ? '?bot=' + botSlot : ''));
    renderFleet();
  }
  function renderFleet() {
    if (!fleetData) return;
    if (view === 'direct') renderDirect();
    if (view === 'equipe') keepOpen($('#team-bots'), renderTeam);
    if (view === 'bot') keepOpen($('#bot-page'), renderBotPage);
    if (view === 'labos') renderChoice();
    markTab();
  }
  function sideText(side) { return side === 'long' ? '▲ acheteur' : '▼ vendeur à découvert'; }
  function bigPct(v) {  // un résultat total, parfois énorme avec le levier : « +12 345 % »
    if (v === null || v === undefined || !isFinite(v)) return '—';
    const x = Math.round(100 * v);
    return (x > 0 ? '+' : x < 0 ? MINUS : '') + Math.abs(x).toLocaleString('fr-FR') + ' %';
  }
  function tradesText(n) { return !n ? 'aucun trade terminé' : n === 1 ? '1 trade' : n + ' trades'; }
  function tag(text) { return el('span', {class: 'pill', text: text}); }
  function days(a, b) {
    const d = Math.round((b - a) / 86400000);
    return d >= 1 ? ' en ' + d + (d > 1 ? ' jours' : ' jour') : '';
  }
  function teamBots() {
    const sec = fleetData && fleetData.ready ? fleetData.sections.find(x => x.key === team) : null;
    return sec ? sec.bots.filter(b => !b.empty) : [];
  }
  function renderDirect() {
    const d = fleetData, step = d.step;
    $('#fleet-title').textContent = step.title;
    $('#fleet-text').textContent = step.text;
    const row = $('#fleet-actions'); row.replaceChildren();
    const action = step.action && d.actions[step.action];
    if (action) row.append(actionButton(action, true, action.title));
    if (step.view === 'journal') row.append(el('a', {class: 'btn', href: '#journal', text: 'Voir le journal'}));
    const kpis = $('#fleet-kpis'), teams = $('#fleet-teams'), events = $('#fleet-events');
    kpis.replaceChildren(); teams.replaceChildren(); events.replaceChildren();
    if (!d.ready) {
      teams.append(el('p', {class: 'empty-box', text: 'Trois équipes de cinq bots : long terme (bougies de 4 h et d\'un jour), '
        + 'court terme (15 min et 1 h) et scalping (1 et 5 min). Chacun sur sa crypto, avec sa technique, choisie par '
        + 'backtest parmi des milliers de combinaisons. Ils apparaîtront ici, en direct, avec leurs positions et leurs trades.'}));
      events.append(el('li', {}, el('span', {class: 'muted', text: 'Rien encore.'})));
      return;
    }
    const t = d.totals;
    kpis.append(
      tile('Valeur de tous les bots', usdt(t.value), 'pour ' + usdt(t.start) + ' fictifs au départ', true),
      tile('Résultat', signed(100 * t.pnl_pct), usdt(t.pnl, true) + (t.retired ? ' · bots remplacés compris' : '')),
      tile('En position', t.positions + ' / ' + t.bots, t.positions ? 'bots dans un trade' : 'ils attendent leurs signaux'),
      tile('Trades terminés', String(t.count), t.win_rate === null ? 'aucun encore' : Math.round(100 * t.win_rate) + ' % gagnants'));
    for (const sec of d.sections) {
      teams.append(el('section', {class: 'squad'},
        el('div', {class: 'squad-head'}, el('h2', {}, el('a', {href: '#' + sec.key, text: sec.title})),
          el('span', {class: 'muted', text: sec.tf_labels.join(' et ') + ' · levier jusqu\'à ×' + dec(sec.leverage)})),
        el('div', {class: 'bot-grid'}, ...sec.bots.map(botCard))));
    }
    if (!d.events.length) events.append(el('li', {}, el('span', {class: 'muted', text: 'Rien encore : les bots démarrent.'})));
    for (const e of d.events.slice(0, 25)) {
      events.append(el('li', {class: 'ev-' + e.kind}, el('time', {datetime: e.t, text: ago(e.t)}), el('span', {text: e.text})));
    }
  }
  function statusChip(b) {
    if (b.position) return chip('live', 'en position');
    if (b.dead) return chip('bad', 'arrêté');
    if (b.pending && b.pending.kind === 'entry') return chip('warn', 'entre maintenant');
    return chip('idle', 'attend son signal');
  }
  function botCard(b) {
    if (b.empty) return el('article', {class: 'card botcard'}, el('h3', {text: b.name}),
      el('p', {class: 'muted', text: 'Plus de remplaçant : refais le choix des bots (page Labos).'}));
    const p = b.position;
    return el('article', {class: 'card botcard'},
      el('div', {class: 'card-head'}, el('h3', {}, el('a', {href: '#bot/' + b.slot, text: b.name + ' · ' + b.coin + ' · ' + b.tf_label})),
        statusChip(b)),
      el('p', {class: 'muted', text: b.technique + ' · ' + sideText(b.side) + ' · levier ×' + dec(b.leverage)
        + (b.target_r ? ' · objectif ' + dec(b.target_r) + 'R' : '')}),
      spark(b),
      el('p', {class: 'big'}, usdt(b.value), el('span', {class: 'delta ' + cls(b.pnl), text: signed(100 * b.pnl_pct)})),
      el('p', {class: 'muted', text: tradesText(b.count) + (b.win_rate === null ? '' : ' · '
        + Math.round(100 * b.win_rate) + ' % gagnants')}),
      p ? el('p', {class: 'pos-line'}, (p.side === 'long' ? 'Acheté ' : 'Vendu ') + price(p.price) + ' → ' + price(p.last) + ' · ',
        el('span', {class: cls(p.pnl), text: signed(100 * p.roi, 1) + ' du capital'})) : null,
      p ? el('p', {class: 'muted', text: 'Stop ' + price(p.stop) + (p.target ? ' · objectif ' + price(p.target) : '')
        + (p.leverage > 1 ? ' · liquidation ' + price(p.liquidation) : '')}) : null,
      el('div', {class: 'row'}, el('a', {class: 'btn', href: '#bot/' + b.slot, text: 'Voir le bot'})));
  }
  function spark(b) {
    const pts = b.closes || [];
    if (pts.length < 2) return el('div', {class: 'spark muted', text: 'Son graphique arrive à la prochaine bougie…'});
    const W = 300, H = 56, P = 4, ys = pts.map(x => x[1]), pos = b.position;
    const refs = pos ? [[pos.price, 'var(--text-secondary)'], [pos.stop, 'var(--critical)']]
      .concat(pos.target ? [[pos.target, 'var(--good)']] : []) : [];
    const all = ys.concat(refs.map(r => r[0]));
    let lo = Math.min(...all), hi = Math.max(...all);
    if (hi === lo) { hi += 1; lo -= 1; }
    const X = i => P + i / (pts.length - 1) * (W - 2 * P), Y = v => P + (hi - v) / (hi - lo) * (H - 2 * P);
    const root = svg('svg', {viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none', role: 'img',
      'aria-label': 'Prix de ' + b.coin + ' sur les ' + pts.length + ' dernières bougies de ' + b.tf_label});
    for (const [v, color] of refs) root.append(svg('line', {x1: P, x2: W - P, y1: Y(v), y2: Y(v), stroke: color,
      'stroke-width': 1, 'stroke-dasharray': '4 3', 'vector-effect': 'non-scaling-stroke'}));
    root.append(svg('polyline', {points: ys.map((v, i) => X(i) + ',' + Y(v)).join(' '), class: 'line',
      stroke: 'var(--series-1)', 'vector-effect': 'non-scaling-stroke'}));
    return el('div', {class: 'spark'}, root);
  }
  function fact(k, v, klass) { return el('div', {class: 'fact'}, el('p', {class: 'k', text: k}), el('p', {class: 'v ' + (klass || ''), text: v})); }
  function positionBox(b) {
    const p = b.position;
    if (!p) {
      const sig = b.pending && b.pending.kind === 'entry' ? ' Son signal vient de tomber : il entre au prochain tour.' : '';
      return el('div', {class: 'position-box'}, el('p', {class: 'muted', text: b.dead ? 'Arrêté : ' + b.dead + '. Il va être remplacé.'
        : 'Pas de position : il attend son signal.' + sig}));
    }
    const long = p.side === 'long';
    return el('div', {class: 'position-box'},
      el('p', {}, el('strong', {text: (long ? '▲ Acheté' : '▼ Vendu à découvert') + ' le ' + when(p.entry_at) + ' à ' + price(p.price)}),
        ' · maintenant ' + price(p.last)),
      el('div', {class: 'facts'},
        fact('Résultat latent', usdt(p.pnl, true) + ' (' + signed(100 * p.roi, 1) + ' du capital)', cls(p.pnl)),
        fact('Stop', price(p.stop) + ' (' + signed((long ? -100 : 100) * p.risk, 1) + ')'),
        fact('Objectif', p.target ? price(p.target) + ' (' + signed(100 * (p.target / p.price - 1), 1) + ')' : 'sortie par sa règle'),
        fact('Liquidation', p.leverage > 1 ? price(p.liquidation) + ' (' + signed(100 * (p.liquidation / p.price - 1), 0) + ')'
          : 'trop loin pour compter (sans levier)'),
        fact('Levier', '×' + dec(p.leverage) + ' · ' + usdt(p.notional) + ' en jeu'),
        fact('Depuis', p.bars + (p.bars > 1 ? ' bougies' : ' bougie'))));
  }
  function compareBox(b) {
    const bt = b.backtest || {};
    const test = bt.test_n ? signed(100 * bt.test_mean, 3) + ' par trade sur ' + bt.test_n + ' trades' : 'trop peu de trades';
    return el('div', {class: 'compare'},
      el('div', {class: 'tile'}, el('p', {class: 'tile-label', text: 'En direct, depuis le ' + when(b.started)}),
        el('p', {class: 'tile-value', text: usdt(b.value)}),
        el('p', {class: 'tile-sub'}, el('span', {class: cls(b.pnl), text: signed(100 * b.pnl_pct)}), ' · ' + tradesText(b.count)
          + (b.win_rate === null ? '' : ' · ' + Math.round(100 * b.win_rate) + ' % gagnants')
          + ' · pire baisse ' + signed(100 * b.drawdown, 0))),
      el('div', {class: 'tile'}, el('p', {class: 'tile-label', text: 'Dans le backtest (historique réel), avec levier'}),
        el('p', {class: 'tile-value', text: bigPct(bt.total_return) + days(bt.start_ts, bt.end_ts)}),
        el('p', {class: 'tile-sub', text: (bt.trades || 0) + ' trades · ' + signed(100 * bt.mean, 3) + ' par trade, frais compris · pire baisse '
          + signed(100 * bt.drawdown, 0)}),
        el('p', {class: 'tile-sub', text: 'Test final, jamais regardé pour choisir : ' + test}),
        el('p', {class: 'tile-sub', text: b.label_text || ''})));
  }
  function tradeItem(t) {
    const d = t.diagnosis || {};
    const long = t.side === 'long';
    return el('article', {class: 'trade'},
      el('div', {class: 'head'}, el('h3', {text: (long ? '▲ Achat ' : '▼ Vente à découvert ') + price(t.price) + ' → ' + price(t.exit_price)}),
        el('span', {class: 'result ' + cls(t.pnl), text: signed(100 * t.roi, 1) + ' du capital · ' + (d.title || t.reason)})),
      el('p', {class: 'muted', text: when(t.entry_at || new Date(t.entry_ts).toISOString()) + ' → '
        + when(t.exit_at || new Date(t.exit_ts).toISOString()) + ' · sortie : ' + t.reason + ' · levier ×' + dec(t.leverage)
        + ' · ' + signed(100 * t.net, 2) + ' sur la position, frais compris'}),
      d.text ? el('p', {text: d.text}) : null,
      d.lesson ? el('p', {class: 'muted'}, el('strong', {text: 'La leçon : '}), d.lesson) : null);
  }
  function botPanel(b, full) {
    if (b.empty) return el('article', {class: 'panel'}, el('h2', {text: b.name}),
      el('p', {class: 'muted', text: 'Plus de remplaçant : refais le choix des bots (page Labos).'}));
    const label = {'3': ['ok', 'gagnant sur 3 périodes'], '2': ['warn', 'gagnant sur 2 périodes'], essai: ['idle', 'à l\'essai']}[b.label] || ['idle', b.label || ''];
    const box = el('article', {class: 'panel'},
      el('div', {class: 'panel-head'},
        el('div', {}, el('p', {class: 'eyebrow', text: b.name + ' · ' + (TEAMS[b.section] || '')}),
          el('h2', {}, full ? b.coin + ' · ' + b.tf_label + ' · ' + b.technique
            : el('a', {class: 'link', href: '#bot/' + b.slot, text: b.coin + ' · ' + b.tf_label + ' · ' + b.technique}))),
        el('div', {class: 'chips'}, statusChip(b), tag(sideText(b.side)), tag('levier ×' + dec(b.leverage)),
          b.target_r ? tag('objectif ' + dec(b.target_r) + 'R') : null, chip(label[0], label[1]))),
      el('p', {text: b.rule + ' ' + b.side_hint.charAt(0).toUpperCase() + b.side_hint.slice(1) + '.'}),
      el('p', {class: 'muted', text: b.exit_rule}));
    const chartBox = el('div', {class: 'bot-chart', 'data-bot': String(b.slot)});
    box.append(chartBox);
    drawBotChart(chartBox, b.slot);
    box.append(positionBox(b), compareBox(b));
    const trades = full ? b.trades : b.trades.slice(0, 3);
    box.append(el('h3', {class: 'group-title', text: full ? 'Tous ses trades' : 'Ses derniers trades'}));
    if (!trades.length) box.append(el('p', {class: 'muted', text: 'Pas encore de trade terminé.'}));
    for (const t of trades) box.append(tradeItem(t));
    if (!full) box.append(el('div', {class: 'row'}, el('a', {class: 'btn', href: '#bot/' + b.slot, text: 'Tout voir sur ' + b.name})));
    return box;
  }
  function renderTeam() {
    const d = fleetData, box = $('#team-bots');
    $('#team-title').textContent = TEAMS[team];
    const sec = d.ready ? d.sections.find(x => x.key === team) : null;
    if (!sec) {
      $('#team-intro').textContent = 'Pas encore de bots : choisis-les sur l\'écran Direct.';
      box.replaceChildren();
      return;
    }
    $('#team-intro').textContent = sec.blurb + ' Levier jusqu\'à ×' + dec(sec.leverage) + '. Ces bots ont été choisis parmi '
      + sec.tested + ' combinaisons backtestées (' + sec.eligible + ' gagnantes, frais compris, sur l\'étude et la validation).';
    box.replaceChildren(...sec.bots.map(b => botPanel(b, false)));
    for (const b of sec.bots) if (!b.empty && !botCharts[b.slot]) loadBotChart(b.slot);
  }
  function renderBotPage() {
    const d = fleetData, box = $('#bot-page'), b = d.bot;
    box.replaceChildren();
    if (b && b.slot !== botSlot) { box.append(el('p', {class: 'muted', text: 'Chargement…'})); return; }  // l'ancien bot
    if (!b) { box.append(el('p', {class: 'empty-box', text: d.ready ? 'Ce bot n\'existe pas (ou plus).' : 'Pas encore de bots : choisis-les sur l\'écran Direct.'})); return; }
    $('#bot-back').setAttribute('href', '#' + b.section);
    $('#bot-back').textContent = '← ' + (TEAMS[b.section] || 'Tous les bots');
    box.append(botPanel(b, true));
    const r = b.reading;
    const coinBox = el('section', {}, el('h2', {text: 'La crypto ' + b.coin + ' en ' + b.tf_label + ', comme un trader la lit'}));
    if (r) {
      coinBox.append(el('div', {class: 'facts'},
        fact('Prix', price(r.price)), fact('Tendance de fond', r.trend || '—'),
        fact('RSI (14)', r.rsi === null || r.rsi === undefined ? '—' : String(Math.round(r.rsi))),
        fact('Bougie moyenne', r.candle_pct === null || r.candle_pct === undefined ? '—' : signed(100 * r.candle_pct, 2).replace('+', '')),
        fact('Sur 24 bougies', signed(100 * r.change, 1)),
        fact('Support', r.support ? price(r.support.price) + ' (' + signed(100 * r.support.distance, 1) + ')' : 'aucun proche'),
        fact('Résistance', r.resistance ? price(r.resistance.price) + ' (' + signed(100 * r.resistance.distance, 1) + ')' : 'aucune proche')),
        el('ul', {class: 'reading'}, ...(r.sentences || []).map(x => el('li', {text: x}))));
    } else coinBox.append(el('p', {class: 'muted', text: 'Sa lecture arrive à la prochaine bougie clôturée.'}));
    box.append(coinBox);
    const done = (b.trades || []).slice().reverse();  // du plus ancien au plus récent
    if (done.length >= 2) {
      const whole = b.count <= done.length;  // sinon, seulement les derniers trades gardés
      const xs = (whole ? [Date.parse(b.started)] : []).concat(done.map(t => t.exit_ts));
      const ys = (whole ? [b.start] : []).concat(done.map(t => t.equity));
      box.append(el('section', {}, el('h2', {text: 'Son capital en direct, trade après trade'}),
        lineChart({width: box.clientWidth || 700, xs: xs, ys: ys,
          refs: [{y: b.start, label: 'Départ : ' + usdt(b.start), short: 'Départ'}], label: 'Capital du bot en direct',
          xTicks: spreadTicks(xs, 4), xTicksSmall: spreadTicks(xs, 3), xTick: dayLabel,
          yTick: v => Math.round(v).toLocaleString('fr-FR'), endLabel: usdt(ys[ys.length - 1]),
          endShort: Math.round(ys[ys.length - 1]).toLocaleString('fr-FR'),
          tip: i => [when(new Date(xs[i]).toISOString()), usdt(ys[i])]})));
    }
    const bt = b.backtest || {};
    const back = el('section', {}, el('h2', {text: 'Son backtest'}),
      el('p', {class: 'meta', text: 'Sur ' + (bt.trades || 0) + ' trades de l\'historique réel : étude ' + signed(100 * bt.study_mean, 3) + ' par trade ('
        + (bt.study_n || 0) + ' trades), validation ' + signed(100 * bt.valid_mean, 3) + ' (' + (bt.valid_n || 0) + '), test final '
        + (bt.test_n ? signed(100 * bt.test_mean, 3) + ' (' + bt.test_n + ')' : '— (trop peu)') + '. Avec son levier et tout son capital : '
        + bigPct(bt.total_return) + days(bt.start_ts, bt.end_ts) + ', pire baisse ' + signed(100 * bt.drawdown, 0) + '.'}));
    if (bt.curve && bt.curve.length >= 2) {
      const xs = bt.curve.map(x => x[0]), ys = bt.curve.map(x => x[1]);
      back.append(lineChart({width: box.clientWidth || 700, xs: xs, ys: ys,
        refs: [{y: ys[0], label: 'Départ : ' + usdt(ys[0]), short: 'Départ'}], label: 'Capital du bot dans le backtest',
        xTicks: spreadTicks(xs, 4), xTicksSmall: spreadTicks(xs, 3), xTick: dayLabel,
        yTick: v => Math.round(v).toLocaleString('fr-FR'), endLabel: usdt(ys[ys.length - 1]),
        endShort: Math.round(ys[ys.length - 1]).toLocaleString('fr-FR'),
        tip: i => [when(new Date(xs[i]).toISOString()), usdt(ys[i])]}));
    }
    back.append(el('p', {class: 'note', text: 'Choisi parmi beaucoup d\'essais : le meilleur de milliers de backtests est souvent chanceux. '
      + 'Le test final, jamais regardé pour choisir, et surtout le direct disent s\'il tient.'}));
    box.append(back);
    if (b.retired && b.retired.length) {
      box.append(el('section', {}, el('h2', {text: 'Les bots qui ont eu cette place avant lui'}),
        ...b.retired.map(x => el('p', {class: 'muted', text: x.spec.symbol.split('/')[0] + ' · ' + x.spec.technique + ' : '
          + x.reason + ' (' + usdt(x.start) + ' → ' + usdt(x.end) + ', ' + x.count + ' trades), arrêté le ' + when(x.until)}))));
    }
    if (!botCharts[b.slot]) loadBotChart(b.slot);
  }
  async function loadBotChart(slot) {
    const cached = botCharts[slot];
    if (cached && cached.busy) return;
    botCharts[slot] = {...(cached || {}), busy: true};
    try {
      const data = await getJSON('/api/bot-graphique?bot=' + slot);
      botCharts[slot] = {at: Date.now(), data: data};
    } catch (e) {
      botCharts[slot] = {...(cached || {}), at: Date.now(), error: e.message};
    }
    document.querySelectorAll('.bot-chart[data-bot="' + slot + '"]').forEach(box => drawBotChart(box, slot));
  }
  async function refreshCharts() {
    const slots = view === 'bot' ? [botSlot] : view === 'equipe' ? teamBots().map(b => b.slot) : [];
    for (const slot of slots) if (slot) await loadBotChart(slot);
  }
  function drawBotChart(box, slot) {
    const c = botCharts[slot];
    if (!c || (!c.data && !c.error)) { box.replaceChildren(el('p', {class: 'muted', text: 'Chargement du graphique…'})); return; }
    if (!c.data) { box.replaceChildren(el('p', {class: 'muted', text: c.error + ' Nouvel essai dans quelques secondes…'})); return; }
    const d = c.data;
    box.replaceChildren(botChart({...d, width: box.clientWidth || 860, label: 'Graphique de ' + coin(d.symbol) + ' et de son bot'}),
      el('div', {class: 'legend'}, ...botLegend(d).filter(Boolean)));
  }
  function botLegend(d) {
    const item = (cls_, color, text, dashed) => el('span', {}, el('span', {class: 'swatch ' + cls_, style: 'background:' + color
      + (dashed ? ';opacity:0.7' : '')}), text);
    const out = [item('', 'var(--up)', 'bougie en hausse'), item('', 'var(--down)', 'bougie en baisse')];
    for (const ln of d.lines) if (!ln.key.startsWith('bb-') || ln.key === 'bb-mid') out.push(item('line', ln.color,
      ln.key === 'bb-mid' ? 'bandes de Bollinger' : ln.label, ln.dash));
    if (d.levels.some(z => z.kind === 'support')) out.push(item('', 'var(--series-3)', 'support'));
    if (d.levels.some(z => z.kind === 'resistance')) out.push(item('', 'var(--series-2)', 'résistance'));
    if (d.trades.length) out.push(el('span', {text: '▲▼ pleins : les vrais trades du bot'}));
    if (d.rule_trades.length) out.push(el('span', {text: '△▽ vides : ce que sa règle aurait fait sur ces bougies'}));
    if (d.position) out.push(item('line', 'var(--critical)', 'stop'), d.position.target ? item('line', 'var(--good)', 'objectif') : null);
    return out;
  }
  function botChart(o) {
    const W = Math.max(300, Math.round(o.width)), small = W < 560;
    const H = small ? 300 : 380, MR = small ? 92 : 178, MT = 12, MB = 26;
    const c = o.candles, n = c.length;
    let lo = Math.min(...c.map(k => k[3])), hi = Math.max(...c.map(k => k[2]));
    const span0 = hi - lo || hi * 0.01 || 1;
    const near = v => v !== null && v !== undefined && isFinite(v) && v >= lo - 0.6 * span0 && v <= hi + 0.6 * span0;
    const zones = o.levels.filter(z => z.high >= lo - 0.25 * span0 && z.low <= hi + 0.25 * span0);
    const pos = o.position, marks = [];
    if (pos) {
      marks.push([pos.price, 'var(--text-secondary)', (pos.side === 'long' ? 'Achat ' : 'Vente ') + price(pos.price), '']);
      marks.push([pos.stop, 'var(--critical)', 'Stop ' + price(pos.stop), '']);
      if (pos.target) marks.push([pos.target, 'var(--good)', 'Objectif ' + price(pos.target), '']);
      if (pos.leverage > 1 && near(pos.liquidation)) marks.push([pos.liquidation, 'var(--critical)', 'Liquidation ' + price(pos.liquidation), '5 4']);
    }
    for (const z of zones) { lo = Math.min(lo, z.low); hi = Math.max(hi, z.high); }
    for (const m of marks) { lo = Math.min(lo, m[0]); hi = Math.max(hi, m[0]); }
    for (const ln of o.lines) for (const v of ln.values) if (near(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    const pad = (hi - lo) * 0.05 || Math.abs(hi) * 0.01 || 1;
    lo -= pad; hi += pad;
    const ticks = niceTicks(lo, hi, small ? 5 : 6), step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
    const tickText = ticks.map(t => tickPrice(t, step));
    const ML = Math.max(small ? 40 : 50, 14 + 6.8 * Math.max(...tickText.map(x => x.length)));  // les petits prix (PEPE) restent lisibles
    const slot = (W - ML - MR) / n, body = Math.max(1, Math.min(8, slot * 0.66));
    const X = i => ML + slot * (i + 0.5), Y = v => MT + (hi - v) / (hi - lo) * (H - MT - MB);
    const root = svg('svg', {viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': o.label, tabindex: '0'});
    ticks.forEach((t, k) => {
      root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(t), y2: Y(t), class: 'grid'}));
      root.append(svg('text', {x: ML - 6, y: Y(t) + 4, 'text-anchor': 'end', class: 'tick'}, tickText[k]));
    });
    const labels = [];
    for (const z of zones) {
      const color = z.kind === 'support' ? 'var(--series-3)' : 'var(--series-2)', top = Y(z.high), bottom = Y(z.low);
      root.append(svg('rect', {x: ML, width: W - MR - ML, y: top, height: Math.max(2, bottom - top), fill: color, opacity: 0.14}));
      labels.push({y: Y(z.price), color: color, text: (small ? '' : z.kind === 'support' ? 'Support ' : 'Résistance ') + price(z.price)});
    }
    for (const ln of o.lines) {
      let pts = [];
      const flush = () => { if (pts.length > 1) root.append(svg('polyline', {points: pts.join(' '), class: 'line', stroke: ln.color,
        'stroke-dasharray': ln.dash ? '5 4' : null, opacity: ln.dash ? 0.8 : null})); pts = []; };
      ln.values.forEach((v, i) => { if (v === null || v === undefined || !near(v)) flush(); else pts.push(X(i) + ',' + Y(v)); });
      flush();
    }
    c.forEach((k, i) => {
      const color = k[4] >= k[1] ? 'var(--up)' : 'var(--down)';
      root.append(svg('line', {x1: X(i), x2: X(i), y1: Y(k[2]), y2: Y(k[3]), stroke: color, 'stroke-width': 1}));
      const top = Y(Math.max(k[1], k[4])), bottom = Y(Math.min(k[1], k[4]));
      root.append(svg('rect', {x: X(i) - body / 2, width: body, y: top, height: Math.max(1, bottom - top), fill: color}));
    });
    for (const [v, color, text, dash] of marks) {
      root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(v), y2: Y(v), stroke: color, 'stroke-width': 1.5,
        'stroke-dasharray': dash || null}));
      labels.push({y: Y(v), color: color, text: text});
    }
    const ts = c.map(k => k[0]);
    const at = t => { if (t === null || t === undefined || t < ts[0]) return -1; let i = 0; while (i + 1 < n && ts[i + 1] <= t) i++; return i; };
    const marker = (i, up, fill, stroke) => {  // sous la bougie pour un achat, au-dessus pour une vente
      const size = 6.5, y = up ? Y(c[i][3]) + 14 : Y(c[i][2]) - 14, dir = up ? 1 : -1;
      root.append(svg('path', {d: 'M' + X(i) + ',' + (y - size * dir) + 'L' + (X(i) + size) + ',' + (y + 0.8 * size * dir)
        + 'L' + (X(i) - size) + ',' + (y + 0.8 * size * dir) + 'Z', fill: fill, stroke: stroke,
        'stroke-width': fill === 'none' ? 1.6 : 1.5}));
    };
    for (const tr of o.rule_trades) {  // ce que la règle aurait fait : triangles vides
      const a = at(tr.entry), b = at(tr.exit), long = tr.side === 'long';
      if (a >= 0) marker(a, long, 'none', 'var(--text-secondary)');
      if (b >= 0) marker(b, !long, 'none', tr.net > 0 ? 'var(--up)' : 'var(--down)');
    }
    for (const tr of o.trades) {  // les vrais trades du bot : triangles pleins
      const a = at(tr.entry), b = at(tr.exit), long = tr.side === 'long';
      if (a >= 0) marker(a, long, 'var(--text-primary)', 'var(--surface-1)');
      if (b >= 0) marker(b, !long, tr.net > 0 ? 'var(--up)' : 'var(--down)', 'var(--surface-1)');
    }
    if (pos) { const a = at(pos.entry_ts); if (a >= 0) marker(a, pos.side === 'long', 'var(--text-primary)', 'var(--surface-1)'); }
    labels.sort((a, b) => a.y - b.y);
    let lastY = -Infinity;
    for (const l of labels) {
      const y = Math.min(H - MB, Math.max(l.y, lastY + 15));
      lastY = y;
      root.append(svg('rect', {x: W - MR + 6, y: y - 5, width: 10, height: 10, rx: 2, fill: l.color}));
      root.append(svg('text', {x: W - MR + 20, y: y + 4, class: 'tick'}, l.text));
    }
    const intraday = ts.length > 1 && ts[1] - ts[0] < 86400000, minutes = ts.length > 1 && ts[1] - ts[0] < 3600000;
    const fmt = ms => {
      const d = new Date(ms), hh = String(d.getHours()).padStart(2, '0') + 'h', mm = String(d.getMinutes()).padStart(2, '0');
      if (!intraday) return dayLabel(ms);
      if (small) return minutes ? hh + mm : dayLabel(ms) + ' ' + hh;
      return dayLabel(ms) + ' ' + hh + (minutes ? mm : '');
    };
    for (let k = 0; k < (small ? 3 : 5); k++) {
      const i = Math.round((n - 1) * (k + 0.5) / (small ? 3 : 5));
      root.append(svg('text', {x: X(i), y: H - 8, 'text-anchor': 'middle', class: 'tick'}, fmt(ts[i])));
    }
    const cross = svg('line', {y1: MT, y2: H - MB, class: 'crosshair'});
    root.append(cross);
    const wrap = el('div', {class: 'mini-chart'}), tip = el('div', {class: 'tip', hidden: true});
    wrap.append(root, tip);
    let index = n - 1;
    function showAt(i) {
      index = Math.max(0, Math.min(n - 1, i));
      const k = c[index], x = X(index);
      cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.style.visibility = 'visible';
      const rows = [el('div', {class: 'tip-date', text: new Date(k[0]).toLocaleString('fr-FR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'})}),
        el('div', {class: 'tip-row', text: 'Ouverture ' + price(k[1]) + ' · clôture ' + price(k[4])}),
        el('div', {class: 'tip-row', text: 'Plus haut ' + price(k[2]) + ' · plus bas ' + price(k[3])})];
      for (const ln of o.lines) if (ln.values[index] !== null && ln.values[index] !== undefined)
        rows.push(el('div', {class: 'tip-row', text: ln.label + ' : ' + price(ln.values[index])}));
      tip.replaceChildren(...rows);
      tip.hidden = false;
      const r = root.getBoundingClientRect(), host = wrap.getBoundingClientRect();
      const left = r.left - host.left + x / W * r.width;
      tip.style.left = (left + tip.offsetWidth + 16 > host.width ? Math.max(4, left - tip.offsetWidth - 12) : left + 12) + 'px';
      tip.style.top = '8px';
    }
    function hide() { cross.style.visibility = 'hidden'; tip.hidden = true; }
    root.addEventListener('pointermove', e => {
      const r = root.getBoundingClientRect();
      showAt(Math.round(((e.clientX - r.left) / r.width * W - ML) / slot - 0.5));
    });
    root.addEventListener('pointerleave', hide);
    root.addEventListener('focus', () => showAt(index));
    root.addEventListener('blur', hide);
    root.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft') { showAt(index - 1); e.preventDefault(); }
      if (e.key === 'ArrowRight') { showAt(index + 1); e.preventDefault(); }
    });
    return wrap;
  }
  function renderChoice() {
    const box = $('#fleet-choice'), d = fleetData;
    box.replaceChildren();
    const action = d && d.actions && d.actions['flotte-choix'];
    if (!d || !d.ready) {
      box.append(el('p', {class: 'empty-box', text: 'Pas encore de choix : « Choisir les 15 bots » backteste toutes les combinaisons '
        + 'sur l\'historique réel et garde les meilleures de chaque équipe.'}));
      if (action) box.append(el('div', {class: 'row'}, actionButton(action, true, action.title)));
      return;
    }
    box.append(el('p', {class: 'meta', text: 'Fait le ' + when(d.selection.date) + ' : ' + d.selection.tested + ' combinaisons '
      + 'backtestées sur ' + d.universe.length + ' cryptos (les plus échangées et les plus agitées du moment), avec les frais des '
      + 'contrats à terme. Chaque historique est coupé en trois : étude (la première moitié), validation (jusqu\'à 80 %), test '
      + 'final (le plus récent). Le classement ne regarde que l\'étude et la validation ; le test final dit si le choix tient.'}));
    for (const sec of d.sections) {
      const rows = (sec.top || []).slice(0, 12).map(r => el('tr', {},
        el('td', {text: coin(r.symbol) + ' · ' + r.technique + (r.target_r ? ' · objectif ' + dec(r.target_r) + 'R' : '')}),
        el('td', {text: (r.timeframe ? ({'1m': '1 min', '5m': '5 min', '15m': '15 min', '1h': '1 h', '4h': '4 h', '1d': '1 jour'}[r.timeframe] || r.timeframe) : '')
          + ' · ' + (r.side === 'long' ? 'achat' : 'vente')}),
        el('td', {class: 'n', text: String(r.sv_n)}),
        el('td', {class: 'n ' + cls(r.sv_mean), text: signed(100 * r.sv_mean, 3)}),
        el('td', {class: 'n ' + cls(r.test_mean), text: r.test_n ? signed(100 * r.test_mean, 3) : '—'}),
        el('td', {class: 'n', text: bigPct(r.total_return)}),
        el('td', {class: 'n', text: signed(100 * r.drawdown, 0)}),
        el('td', {text: r.eligible ? '✓ oui' : '✕ non'})));
      box.append(el('div', {class: 'choice-team'},
        el('h3', {text: sec.title + ' : ' + sec.eligible + ' gagnantes sur ' + sec.tested + ' essais'}),
        el('div', {class: 'table-wrap'}, el('table', {},
          el('thead', {}, el('tr', {}, el('th', {text: 'Combinaison'}), el('th', {text: 'Unité · sens'}),
            el('th', {class: 'n', text: 'Trades'}), el('th', {class: 'n', text: 'Par trade'}), el('th', {class: 'n', text: 'Test final'}),
            el('th', {class: 'n', text: 'Avec levier'}), el('th', {class: 'n', text: 'Pire baisse'}), el('th', {text: 'Gagnante ?'}))),
          el('tbody', {}, ...rows)))));
    }
    box.append(el('p', {class: 'note', text: 'Par trade : le gain moyen d\'un trade, frais et financement compris, sans levier (étude '
      + '+ validation). Avec levier : ce qu\'aurait fait le capital du bot sur tout l\'historique, en misant tout à chaque trade. '
      + 'Pire baisse : la plus forte chute de ce capital depuis un sommet.'}));
    if (action) box.append(el('div', {class: 'row'}, actionButton(action, false, 'Refaire le choix des bots')));
  }
  // --- l'école ---
  let schoolData = null;
  async function loadSchool(sub) {
    if (!schoolData) schoolData = await getJSON('/api/ecole');
    if (sub) renderLesson(sub); else renderSchoolList();
  }
  function doneLessons() { try { return JSON.parse(localStorage.getItem('ecole-faites') || '[]'); } catch (e) { return []; } }
  function markDone(id) {
    try { const done = new Set(doneLessons()); done.add(id); localStorage.setItem('ecole-faites', JSON.stringify([...done])); } catch (e) {}
  }
  function renderSchoolList() {
    $('#school-home').hidden = false;
    $('#lesson').hidden = true;
    const done = new Set(doneLessons()), box = $('#school-list');
    box.replaceChildren(...schoolData.lessons.map(l => el('article', {class: 'card'},
      el('div', {class: 'card-head'}, el('h3', {text: l.number + '. ' + l.title}), done.has(l.id) ? el('span', {class: 'done-mark', text: '✓ faite'}) : null),
      el('p', {class: 'muted', text: l.minutes + ' min · ' + l.quiz.length + ' questions'}),
      el('div', {class: 'row'}, el('a', {class: 'btn' + (done.has(l.id) ? '' : ' btn-primary'), href: '#ecole/' + l.id,
        text: done.has(l.id) ? 'Revoir' : 'Commencer'})))));
  }
  function renderLesson(id) {
    const l = schoolData.lessons.find(x => x.id === id);
    if (!l) { renderSchoolList(); return; }
    $('#school-home').hidden = true;
    const box = $('#lesson');
    box.hidden = false;
    box.replaceChildren(el('p', {class: 'eyebrow', text: 'Leçon ' + l.number + ' sur ' + schoolData.lessons.length + ' · ' + l.minutes + ' min'}),
      el('h1', {text: l.title}));
    for (const b of l.blocks) {
      if (b.text) box.append(el('p', {text: b.text}));
      else if (b.example) box.append(el('div', {class: 'example'}, el('strong', {text: 'Exemple'}), el('p', {text: b.example})));
      else if (b.figure) box.append(figure(b));
    }
    box.append(el('h2', {text: 'À retenir'}), el('ul', {class: 'remember'}, ...l.remember.map(r => el('li', {text: r}))),
      el('h2', {text: 'Mini-quiz'}), quiz(l));
    if (l.sources.length) box.append(el('p', {class: 'small-print'}, 'Sources : ', ...l.sources.flatMap((src, i) => [i ? ' · ' : null,
      el('a', {href: src.url, target: '_blank', rel: 'noopener', text: src.title})])));
    const next = l.next && schoolData.lessons.find(x => x.id === l.next);
    box.append(el('div', {class: 'row'}, el('a', {class: 'btn', href: '#ecole', text: 'Toutes les leçons'}),
      next ? el('a', {class: 'btn btn-primary', href: '#ecole/' + next.id, text: 'Leçon suivante : ' + next.title}) : null));
    window.scrollTo(0, 0);
  }
  function quiz(l) {
    const wrap = el('div', {class: 'quiz'});
    l.quiz.forEach((q, qi) => {
      const why = el('p', {class: 'why', hidden: true});
      const buttons = q.choices.map((choice, ci) => el('button', {class: 'btn', type: 'button', text: choice, 'aria-pressed': 'false',
        onclick: () => {
          buttons.forEach(b => { b.setAttribute('aria-pressed', 'false'); b.classList.remove('right', 'wrong'); });
          buttons[ci].setAttribute('aria-pressed', 'true');
          buttons[ci].classList.add(ci === q.answer ? 'right' : 'wrong');
          why.hidden = false;
          why.textContent = (ci === q.answer ? '✓ Exact. ' : '✕ Pas tout à fait : la bonne réponse est « ' + q.choices[q.answer] + ' ». ') + q.why;
          if (wrap.querySelectorAll('.why:not([hidden])').length === l.quiz.length) markDone(l.id);
        }}));
      wrap.append(el('div', {class: 'q'}, el('p', {text: (qi + 1) + '. ' + q.q}), el('div', {class: 'choices'}, ...buttons), why));
    });
    return wrap;
  }
  function figure(b) {
    if (b.figure === 'candle') return candleAnatomy();
    if (b.figure === 'risk') return riskSim(b.question);
    if (b.figure === 'leverage') return leverageSim(b.question);
    if (b.figure === 'fees') return feesSim(b.question);
    if (b.figure === 'diagnoses') return diagnosesBox();
    if (b.figure === 'chart') return lessonChart(b);
    return null;
  }
  function candleAnatomy() {
    const root = svg('svg', {viewBox: '0 0 440 250', role: 'img', 'aria-label': 'Une bougie verte (hausse) et une bougie rouge (baisse), avec leurs plus haut, plus bas, ouverture et clôture'});
    const draw = (x, high, top, bottom, low, color) => {
      root.append(svg('line', {x1: x, x2: x, y1: high, y2: low, stroke: color, 'stroke-width': 2}));
      root.append(svg('rect', {x: x - 16, width: 32, y: top, height: bottom - top, rx: 3, fill: color}));
    };
    const label = (x1, x2, y, text, anchor) => {
      root.append(svg('line', {x1: x1, x2: x2, y1: y, y2: y, class: 'grid'}));
      root.append(svg('text', {x: anchor === 'end' ? x1 - 4 : x2 + 4, y: y + 4, 'text-anchor': anchor, class: 'tick'}, text));
    };
    draw(130, 20, 62, 168, 214, 'var(--up)');
    label(96, 128, 20, 'Plus haut', 'end'); label(96, 112, 62, 'Clôture', 'end');
    label(96, 112, 168, 'Ouverture', 'end'); label(96, 128, 214, 'Plus bas', 'end');
    draw(310, 30, 70, 160, 204, 'var(--down)');
    label(328, 344, 70, 'Ouverture', 'start'); label(328, 344, 160, 'Clôture', 'start');
    label(312, 344, 30, 'mèche', 'start'); label(328, 344, 115, 'corps', 'start');
    root.append(svg('text', {x: 130, y: 242, 'text-anchor': 'middle', class: 'tick'}, 'Verte : le prix a monté'));
    root.append(svg('text', {x: 310, y: 242, 'text-anchor': 'middle', class: 'tick'}, 'Rouge : le prix a baissé'));
    return el('div', {class: 'mini-chart'}, root);
  }
  function slider(label, min, max, step, value, fmt, onchange) {
    const out = el('strong', {text: fmt(value)});
    const input = el('input', {type: 'range', min: min, max: max, step: step, value: value, 'aria-label': label});
    input.addEventListener('input', () => { out.textContent = fmt(Number(input.value)); onchange(); });
    return {node: el('label', {}, el('span', {text: label}), out, input), get: () => Number(input.value)};
  }
  const nb = (v, d) => Number(v).toLocaleString('fr-FR', {maximumFractionDigits: d === undefined ? 2 : d});
  function riskSim(question) {
    const res = el('p', {class: 'out'});
    const update = () => {
      const loss = cap.get() * risk.get() / 100, size = loss / (stop.get() / 100), lev = size / cap.get();
      res.textContent = 'Position : ' + nb(size, 0) + ' $. Si le stop est touché, tu perds ' + nb(loss) + ' $ ('
        + nb(risk.get(), 1) + ' % du compte). ' + (lev > 1 ? 'La position dépasse le compte : il faudrait un levier de '
        + dec(lev) + '.' : 'Pas besoin de levier.');
    };
    const cap = slider('Capital du compte', 100, 10000, 100, 1000, v => nb(v, 0) + ' $', update);
    const risk = slider('Risque par trade', 0.5, 5, 0.5, 1, v => nb(v, 1) + ' %', update);
    const stop = slider('Distance du stop sous l\'achat', 0.2, 10, 0.1, 2, v => nb(v, 1) + ' %', update);
    update();
    return el('div', {class: 'sim'}, question ? el('p', {class: 'question', text: question}) : null, cap.node, risk.node, stop.node, res);
  }
  function leverageSim(question) {
    const res = el('p', {class: 'out'});
    const update = () => {
      const l = lev.get(), m = move.get(), result = l * m, limit = 100 / l;
      res.textContent = (result <= -100 ? 'Liquidé : ta mise est perdue. ' : 'Sur ta mise : ' + signed(result, 1) + '. ')
        + 'Avec un levier de ' + nb(l, 0) + ', ta mise est perdue dès que le prix va de ' + nb(limit, 1) + ' % contre toi.';
    };
    const lev = slider('Levier', 1, 20, 1, 5, v => '×' + nb(v, 0), update);
    const move = slider('Mouvement du prix', -10, 10, 0.5, -2, v => signed(v, 1), update);
    update();
    return el('div', {class: 'sim'}, question ? el('p', {class: 'question', text: question}) : null, lev.node, move.node, res);
  }
  function feesSim(question) {
    const res = el('p', {class: 'out'});
    const FEES = [['Comptant', 0.30], ['Futures au marché', 0.14], ['Futures en limite', 0.04]];
    let fee = 0.30;
    const update = () => {
      const net = move.get() - fee;
      res.textContent = 'Après frais : ' + signed(net, 2) + ' par trade, soit environ ' + signed(100 * net, 0)
        + ' sur 100 trades. Il faut capter plus de ' + nb(fee, 2) + ' % par trade, en moyenne, rien que pour payer les frais.';
    };
    const seg = el('div', {class: 'seg', role: 'group', 'aria-label': 'Frais d\'un aller-retour'});
    const buttons = FEES.map(([label, value]) => el('button', {type: 'button', 'aria-pressed': String(value === fee),
      text: label + ' (' + nb(value, 2) + ' %)', onclick: () => {
        fee = value; buttons.forEach(b => b.setAttribute('aria-pressed', String(b === buttons[FEES.findIndex(f => f[1] === value)]))); update();
      }}));
    seg.append(...buttons);
    const move = slider('Gain moyen capté par trade, avant frais', 0, 1.5, 0.05, 0.25, v => nb(v, 2) + ' %', update);
    update();
    return el('div', {class: 'sim'}, question ? el('p', {class: 'question', text: question}) : null, seg, el('div', {class: 'row'}), move.node, res);
  }
  const KIND_HELP = {
    gagne: 'Le scénario prévu s\'est déroulé : le cas que la règle cherche.',
    gain_partiel: 'Gagné, mais le trade était monté bien plus haut avant la sortie.',
    frais: 'Le prix est allé dans le bon sens, pas assez pour payer les frais.',
    faux_depart: 'Le prix est reparti contre le trade tout de suite, jusqu\'au stop.',
    gain_rendu: 'Le trade a été gagnant, puis s\'est retourné jusqu\'au stop.',
    stop: 'Le prix a hésité, puis touché le stop.',
    temps: 'Le mouvement attendu n\'est pas venu à temps : le bot a coupé.',
    sortie_regle: 'La règle de sortie a coupé avant que le trade ne devienne gagnant.',
    liquidation: 'Avec le levier, la perte a atteint la marge : position fermée d\'office.',
  };
  function diagnosesBox() {
    const box = el('div', {class: 'sim'});
    box.append(el('p', {class: 'question', text: 'Les diagnostics que ton trader écrit après chaque vente :'}),
      el('ul', {}, ...Object.entries(KIND_HELP).map(([k, help]) => el('li', {}, el('strong', {text: (schoolData.kinds[k] || k) + ' : '}), help))));
    if (schoolData.examples.length) {
      box.append(el('p', {class: 'question', text: 'Des exemples tirés de tes propres trades :'}));
      for (const e of schoolData.examples) box.append(el('p', {}, el('strong', {text: coin(e.symbol) + ' · ' + e.play + ' · ' + signed(100 * e.net) + ' — ' + e.diagnosis.title + '. '}),
        e.diagnosis.text + (e.replay ? ' (rejeu)' : '')));
    } else {
      box.append(el('p', {class: 'muted', text: 'Pas encore de trade de ton trader : ses premiers exemples apparaîtront ici.'}));
    }
    return box;
  }
  function lessonChart(b) {
    const box = el('div', {}, el('p', {class: 'muted', text: 'Chargement du graphique…'}));
    getJSON('/api/graphique?symbole=' + encodeURIComponent(b.symbol) + '&unite=' + b.timeframe).then(d => {
      box.replaceChildren(candleChart({...d, width: box.clientWidth || 760, label: b.caption || coin(d.symbol)}),
        el('div', {class: 'legend'}, ...chartLegend(d).filter(Boolean)), el('p', {class: 'small-print', text: b.caption || ''}));
    }).catch(() => box.replaceChildren(el('p', {class: 'empty-box', text: 'Graphique indisponible pour l\'instant (le radar démarre, '
      + 'ou la plateforme ne répond pas). Il apparaîtra ici dès que les prix arrivent ; en attendant, ouvre la page Graphiques.'})));
    return box;
  }

  // --- l'actualité ---
  function ago(iso) {
    if (!iso) return '';
    const s = (Date.now() - Date.parse(iso)) / 1000;
    if (s < 3600) return 'il y a ' + Math.max(1, Math.round(s / 60)) + ' min';
    if (s < 2 * 86400) return 'il y a ' + Math.round(s / 3600) + ' h';
    return when(iso);
  }
  let newsReady = false;
  async function refreshNews() {
    const d = await getJSON('/api/actualite');
    newsReady = d.news.length > 0 || !!d.fng;
    renderFng(d.fng);
    const list = $('#news-list');
    $('#news-status').textContent = (d.news.length ? d.news.length + ' titres' + (d.updated ? ' · relevés ' + ago(d.updated) : '')
      : 'Chargement des titres…') + (d.errors.length ? ' · ' + d.errors.join(' ; ') : '');
    list.replaceChildren(...d.news.map(n => el('div', {class: 'news-item'},
      el('a', {href: n.link, target: '_blank', rel: 'noopener noreferrer', text: n.title}),
      el('div', {class: 'meta-line', text: n.source + ' · ' + ago(n.published)}),
      n.moves && n.moves.length ? el('div', {class: 'meta-line'}, ...n.moves.map(m => el('span', {class: 'coin'},
        el('strong', {text: m.coin}), el('span', {class: cls(m.change), text: m.change === null || m.change === undefined
          ? 'prix à la publication inconnu' : signed(100 * m.change, 1) + ' depuis'})))) : null)));
  }
  function renderFng(f) {
    const box = $('#fng-box');
    box.replaceChildren();
    if (!f) { box.append(el('p', {class: 'muted', text: 'Indice indisponible pour l\'instant.'})); return; }
    box.append(el('p', {class: 'fng-value', text: Math.round(f.value) + ' / 100'}),
      el('p', {class: 'muted', text: 'Indice peur et avidité : ' + f.zone + ' (' + new Date(f.date).toLocaleDateString('fr-FR') + ')'}));
    const meter = el('div', {class: 'meter', role: 'img', 'aria-label': 'Indice : ' + Math.round(f.value) + ' sur 100, ' + f.zone});
    meter.append(el('span', {class: 'mark', style: 'left:' + Math.max(0, Math.min(100, f.value)) + '%'}));
    box.append(meter, el('div', {class: 'meter-scale'}, el('span', {text: '0 · peur extrême'}), el('span', {text: '50 · neutre'}),
      el('span', {text: 'avidité extrême · 100'})));
    if (f.history && f.history.length > 30) {
      const xs = f.history.map(h => Date.parse(h[0])), ys = f.history.map(h => h[1]);
      box.append(lineChart({width: box.clientWidth || 700, xs: xs, ys: ys,
        refs: [{y: 25, label: 'Peur extrême (25)', short: '25'}, {y: 75, label: 'Avidité extrême (75)', short: '75'}],
        label: 'Indice peur et avidité, douze derniers mois', xTicks: spreadTicks(xs, 4), xTicksSmall: spreadTicks(xs, 3),
        xTick: monthLabel, yTick: v => String(Math.round(v)), endLabel: Math.round(ys[ys.length - 1]) + ' · ' + f.zone,
        endShort: String(Math.round(ys[ys.length - 1])), tip: i => [new Date(xs[i]).toLocaleDateString('fr-FR'), Math.round(ys[i]) + ' / 100']}));
    }
    box.append(el('p', {class: 'note', text: f.study_text}));
  }
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (view === 'graphiques') renderChart(); if (view === 'accueil') renderTrader();
      renderFleet(); }, 250);
  });

  // --- rythme : chaque source seulement quand sa page est affichée ---
  const last = {state: 0, journal: 0, radar: 0, prices: 0, trials: 0, trader: 0, news: 0, chart: 0, fleet: 0, charts: 0};
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
    if (view === 'accueil') every('trader', 15000, refreshTrader);
    if (view === 'actualite') every('news', newsReady ? 60000 : 2000, refreshNews);
    if (view === 'graphiques') every('chart', 60000, loadChart);
    if (['direct', 'equipe', 'bot', 'labos'].includes(view)) every('fleet', view === 'labos' ? 15000 : 5000, refreshFleet);
    if (view === 'equipe' || view === 'bot') every('charts', 30000, refreshCharts);
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
