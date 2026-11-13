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
.tabs .more { background: none; border: 0; padding: 8px 12px; color: var(--text-secondary); font: inherit;
  font-size: 14px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; }
.tabs .more[aria-expanded="true"] { color: var(--text-primary); }
.tabs .more::after { content: " ▾"; }
.tabs-more { margin-top: 0; padding-bottom: 2px; flex-wrap: wrap; }
.tabs[hidden] { display: none; }
.tabs-more a { font-size: 13px; }
.tabs .short { display: none; }
@media (max-width: 600px) { .tabs a, .tabs .more { padding: 8px 8px; } .tabs .long { display: none; } .tabs .short { display: inline; } }
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
.btn:focus-visible, .seg button:focus-visible, .tabs a:focus-visible, .zsvg:focus-visible { outline: 2px solid var(--accent);
  outline-offset: 2px; }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
.btn-small { padding: 4px 12px; font-size: 13px; min-width: 36px; }
.btn[disabled] { opacity: 0.5; cursor: not-allowed; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
  display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.card h3 { margin: 0; font-size: 15px; }
.card p { margin: 0; }
.card .row { margin-top: auto; padding-top: 8px; }
.card-head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.muted { color: var(--text-secondary); font-size: 13px; }
.mono { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 12px; }
.group-title { font-size: 14px; margin: 20px 0 8px; color: var(--text-secondary); text-transform: uppercase;
  letter-spacing: 0.05em; }
.empty-box { background: var(--surface-1); border: 1px dashed var(--border); border-radius: 12px; padding: 14px 16px;
  color: var(--text-secondary); }
.warn { margin-top: 16px; padding: 12px 16px; border-radius: 8px; border: 2px solid var(--warning); }
.warn-top { margin: 0 0 16px; }
.journal { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 12px; }
@media (max-width: 760px) { .journal { grid-template-columns: minmax(0, 1fr); } }
.task-list { display: flex; flex-direction: column; gap: 6px; }
.task-list button { text-align: left; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
  padding: 8px 12px; color: var(--text-primary); font: inherit; font-size: 14px; cursor: pointer; }
.task-list button[aria-pressed="true"] { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
.log { margin: 0; background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
  height: 64vh; overflow: auto; white-space: pre-wrap; word-break: break-word; line-height: 1.5; font-size: 12.5px; }
.controls { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; margin-bottom: 12px; }
.seg { display: inline-flex; flex-wrap: wrap; border: 1px solid var(--border); border-radius: 18px; overflow: hidden; }
.seg button { background: transparent; border: 0; padding: 6px 14px; color: var(--text-secondary); font: inherit;
  font-size: 13px; font-weight: 600; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--accent); color: #fff; }
.check { display: inline-flex; gap: 6px; align-items: center; font-size: 14px; color: var(--text-secondary); }
.status-line { margin: 0 0 12px; color: var(--text-secondary); font-size: 13px; }
.link { background: none; border: 0; padding: 0; font: inherit; font-weight: 600; color: var(--text-primary);
  text-decoration: underline; text-decoration-color: var(--accent); text-underline-offset: 3px; cursor: pointer; }
.link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.mini-chart { position: relative; background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
  padding: 8px; margin: 8px 0 4px; }
.mini-chart svg { display: block; width: 100%; height: auto; font-size: 12px; outline-offset: 4px; }
.band { fill: var(--series-1); opacity: 0.14; }
.small-print { color: var(--text-secondary); font-size: 12px; }
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
.section-head { display: flex; justify-content: space-between; align-items: center; gap: 8px 12px; flex-wrap: wrap;
  margin-bottom: 8px; }
.section-head h2 { margin: 0; }
.section-head p { margin: 0; }
.trade { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px;
  margin-bottom: 10px; }
.trade p { margin: 4px 0 0; }
.trade .head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.trade .head h3 { margin: 0; font-size: 15px; }
.trade .result { font-weight: 700; font-variant-numeric: tabular-nums; }
.lesson-line { margin: 0 0 6px; max-width: 900px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
.swatch.line { height: 3px; border-radius: 2px; }
.swatch.dashed { height: 0; border-top: 2px dashed; background: none; }
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
.pill { display: inline-flex; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--border); font-size: 13px;
  color: var(--text-primary); white-space: nowrap; }
.kpis.swarm-kpis .tile-value { font-size: 22px; }
.kpis.swarm-kpis .tile-hero .tile-value { font-size: 30px; }
tr.clickable { cursor: pointer; }
tr.clickable:hover td { background: var(--surface-2, rgba(127, 127, 127, 0.08)); }
td.pair a { color: var(--text-primary); text-decoration: none; font-weight: 700; }
td.pair a:hover { text-decoration: underline; text-decoration-color: var(--accent); }
td .sub { display: block; color: var(--text-secondary); font-size: 12px; font-weight: 400; white-space: nowrap; }
td.wrap { white-space: normal; min-width: 120px; }
.mob { display: none; }
tr.strong-row td:first-child { box-shadow: inset 3px 0 0 var(--good); }
td.focus { font-weight: 700; }
@media (max-width: 600px) { .opt { display: none; } td.wrap { min-width: 0; } td .sub.mob { display: block; white-space: normal; } }
.bot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 12px;
  margin-top: 10px; }
.botcard { gap: 4px; color: var(--text-primary); text-decoration: none; }
.botcard:hover { border-color: var(--accent); }
.botcard .big { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; margin: 2px 0 0; }
.botcard .big .delta { font-size: 14px; margin-left: 6px; }
.pos-line { font-size: 14px; font-variant-numeric: tabular-nums; }
.events { list-style: none; margin: 0; padding: 0; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 12px; }
.events li { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: 10px; padding: 8px 14px;
  border-bottom: 1px solid var(--grid); font-size: 14px; }
.events li:last-child { border-bottom: 0; }
.events time { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.events a { color: var(--text-primary); text-decoration: none; }
.events a:hover { text-decoration: underline; text-decoration-color: var(--accent); }
@media (max-width: 600px) { .events li { grid-template-columns: minmax(0, 1fr); gap: 0; } }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px 16px; flex-wrap: wrap; }
.panel-head h1 { margin: 2px 0 0; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.position-box { margin-top: 12px; padding: 12px 14px; border-radius: 10px; border: 1px solid var(--border);
  background: var(--surface-1); }
.position-box p { margin: 0; }
.facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 170px), 1fr)); gap: 8px 16px;
  margin-top: 8px; }
.fact .k { margin: 0; color: var(--text-secondary); font-size: 12px; }
.fact .v { margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; }
.compare { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
@media (max-width: 600px) { .compare { grid-template-columns: minmax(0, 1fr); } }
.crumb { margin: 0 0 8px; }
.ztools { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 4px; }
.zinfo { margin-left: 4px; }
.zchart { touch-action: pan-y; user-select: none; -webkit-user-select: none; cursor: grab; }
.zchart:active { cursor: grabbing; }
"""

BODY = """
<header class="site-top"><div class="site-top-inner">
  <div class="brand-row">
    <p class="brand">Trading bot <span class="badge" id="mode-badge">…</span></p>
    <button id="theme-toggle" class="theme" type="button">Clair / sombre</button>
  </div>
  <nav class="tabs" aria-label="Pages du site">
    <a href="#direct" data-view="direct">Direct</a>
    <a href="#cryptos" data-view="cryptos">Cryptos</a>
    <a href="#strategies" data-view="strategies"><span class="long">Stratégies</span><span class="short">Strat.</span></a>
    <a href="#actualite" data-view="actualite"><span class="long">Actualité</span><span class="short">Infos</span></a>
    <a href="#prix" data-view="prix">Prix</a>
    <button type="button" class="more" id="more-toggle" aria-expanded="false" aria-controls="more-tabs">Plus</button>
  </nav>
  <nav class="tabs tabs-more" id="more-tabs" aria-label="Autres pages" hidden>
    <a href="#ecole" data-view="ecole">École</a>
    <a href="#reglages" data-view="reglages">Réglages</a>
    <a href="#journal" data-view="journal">Journal</a>
  </nav>
</div></header>
<main class="site">
  <div id="settings-warning" class="warn warn-top" hidden></div>
  <div id="view-direct" class="view">
    <div class="hero" aria-live="polite">
      <p class="eyebrow">En direct · argent fictif</p>
      <h1 id="swarm-title">Chargement…</h1>
      <p id="swarm-text"></p>
      <div class="row" id="swarm-actions"></div>
    </div>
    <section><div class="kpis swarm-kpis" id="swarm-kpis"></div></section>
    <section id="trial-box" hidden>
      <div class="section-head"><h2>La mesure à l'essai</h2><a class="link" href="#strategies">Le classement des stratégies</a></div>
      <div class="facts" id="trial-facts"></div>
      <p class="note">À l'essai : toutes les combinaisons (technique, sens, sortie, unité de temps) tournent en argent
        fictif sur chaque crypto qui bouge, avec le même moteur que les bots. Leurs trades sont comptés sans rien choisir
        d'avance : la chance ne peut pas embellir cette mesure. Test final : ce que les combinaisons choisies par le labo
        ont fait sur la partie de l'historique qui n'a pas servi à les choisir. Point de référence : les chiffres du site
        avant cette mesure.</p>
    </section>
    <section>
      <div class="section-head"><h2>Tous les bots</h2><p class="muted" id="bots-count"></p></div>
      <div class="controls">
        <div class="seg" role="group" aria-label="Horizon des bots" id="filter-team"></div>
        <div class="seg" role="group" aria-label="État des bots" id="filter-status"></div>
        <label class="check" for="bots-sort">Trier par <select id="bots-sort">
          <option value="pnl">meilleur résultat</option><option value="worst">pire résultat</option>
          <option value="trades">nombre de trades</option><option value="coin">crypto</option>
          <option value="recent">plus récents</option></select></label>
      </div>
      <div class="table-wrap"><table><thead><tr><th>Bot</th><th class="opt">Technique</th><th class="opt">État</th>
        <th class="n">Résultat</th><th class="n">Position</th><th class="n opt">Trades</th></tr></thead>
        <tbody id="bots-rows"></tbody></table></div>
      <div class="row" id="bots-more"></div>
      <p class="note">Résultat : depuis le lancement du bot, frais compris. Position : ce que gagne ou perd le trade en
        cours, sur le capital du bot (levier compris). Touche un bot pour voir son graphique, son stop et son objectif.</p>
    </section>
    <section><h2>Ce qui vient de se passer</h2><ol class="events" id="swarm-events"></ol></section>
    <p class="note">Chaque bot a son capital fictif (1000 USDT, réglable) et le met en entier dans chaque trade, avec le
      levier de son horizon : un stop touché peut coûter plusieurs pourcents de son capital, et un bot peut être liquidé.
      Les combinaisons gagnantes sur l'historique sont souvent chanceuses : ce sont la mesure à l'essai et le direct qui
      tranchent. Un bot garde sa place d'un test à l'autre ; il n'est arrêté que s'il est liquidé, à moitié ruiné,
      nettement perdant après 20 trades, ou si sa stratégie est recalée.</p>
  </div>
  <div id="view-cryptos" class="view" hidden>
    <h1>Les cryptos suivies</h1>
    <p class="meta" id="coins-intro"></p>
    <div class="table-wrap"><table><thead><tr><th>Crypto</th><th class="n">24 h</th><th class="n opt">Amplitude</th>
      <th>État</th><th class="n">Bots</th><th class="n opt">En position</th><th class="n">Résultat</th></tr></thead>
      <tbody id="coins-rows"></tbody></table></div>
    <p class="note">Amplitude : l'écart entre le plus haut et le plus bas des dernières 24 heures. Résultat : la somme des
      bots de la crypto, en USDT fictifs.</p>
  </div>
  <div id="view-strategies" class="view" hidden>
    <h1>Les stratégies</h1>
    <div class="controls"><div class="seg" role="group" aria-label="Mesure affichée" id="rank-source"></div></div>
    <p class="meta" id="rank-meta"></p>
    <p class="status-line" id="rank-intro"></p>
    <div class="controls"><div class="seg" role="group" aria-label="Classer par" id="rank-period"></div>
      <div class="seg" role="group" aria-label="Unité de temps" id="rank-tf"></div></div>
    <div class="table-wrap"><table><thead><tr><th>Stratégie</th><th class="n opt">Trades</th><th class="n opt">Gagnants</th>
      <th class="n" id="rank-head">Par trade</th><th class="n opt">Fourchette à 95 %</th><th class="n opt">Aujourd'hui</th>
      <th class="n opt">7 jours</th><th>Verdict</th></tr></thead><tbody id="rank-rows"></tbody></table></div>
    <div class="row" id="rank-next"></div>
    <p class="note" id="rank-note"></p>
    <section id="rank-exits"></section>
    <section><div class="compare" id="rank-more"></div></section>
  </div>
  <div id="view-crypto" class="view" hidden>
    <p class="crumb"><a class="link" href="#cryptos">← Toutes les cryptos</a></p>
    <div id="coin-page"></div>
  </div>
  <div id="view-bot" class="view" hidden>
    <p class="crumb"><a class="link" href="#cryptos" id="bot-back">← Toutes les cryptos</a></p>
    <div id="bot-page"></div>
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
      prix a fait depuis la publication, et l'humeur du marché. Pour comprendre ce qui se passe : les bots ne tradent pas
      sur les titres (quand on les lit, le mouvement a souvent déjà eu lieu).</p>
    <section><h2>L'humeur du marché</h2><div id="fng-box"><p class="muted">Chargement…</p></div></section>
    <section><h2>Derniers titres</h2><p class="status-line" id="news-status" aria-live="polite"></p>
      <div id="news-list" class="news"></div></section>
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
        Un écart de 0,1 % ne couvre même pas les frais d'un aller-retour.</p>
      <ul class="note" id="prices-errors"></ul>
    </section>
  </div>
  <div id="view-journal" class="view" hidden>
    <h1>Journal</h1>
    <p class="meta">Ce que disent les commandes lancées depuis le site (dont les bots), en direct.</p>
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
      <p class="note">Quand tu changes un réglage des bots, ils redémarrent tout seuls avec les nouveaux réglages :
        leurs positions et leurs comptes sont repris. Le capital fictif choisi vaut pour les bots créés ensuite.</p>
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
    try { const r = await post('/api/reglages', {values: values}); toast('Réglages enregistrés (' + (r.saved.length || 0) + ').' + (r.restarted ? ' Les bots redémarrent avec les nouveaux réglages.' : '')); loadSettings(); refreshState(); }
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

  // --- petits outils des autres pages ---
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

  // --- petits outils ---
  function usdt(v, signed) {
    if (v === null || v === undefined || !isFinite(v)) return '—';
    const s = Math.abs(v).toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' USDT';
    return signed ? (v > 0 ? '+' : v < 0 ? MINUS : '') + s : (v < 0 ? MINUS : '') + s;
  }
  function tile(label, value, sub, hero) {
    return el('div', {class: 'tile' + (hero ? ' tile-hero' : '')}, el('p', {class: 'tile-label', text: label}),
      el('p', {class: 'tile-value', text: value}), el('p', {class: 'tile-sub', text: sub}));
  }
  function precise(v) {  // un prix au chiffre près : six chiffres utiles
    if (v === null || v === undefined || !isFinite(v) || v === 0) return '—';
    if (Math.abs(v) >= 1000) return v.toLocaleString('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    return Number(v.toPrecision(6)).toLocaleString('fr-FR', {maximumFractionDigits: 12});
  }
  function bigPct(v) {
    if (v === null || v === undefined || !isFinite(v)) return '—';
    const x = Math.round(100 * v);
    return (x > 0 ? '+' : x < 0 ? MINUS : '') + Math.abs(x).toLocaleString('fr-FR') + ' %';
  }
  function chip(kind, text) {
    const style = {ok: 'chip-good', bad: 'chip-critical', warn: 'chip-warning', idle: 'chip-muted'}[kind] || '';
    return el('span', {class: 'chip ' + style}, el('span', {text: kind === 'live' ? '●' : kind === 'ok' ? '✓' :
      kind === 'bad' ? '✕' : '•'}), text);
  }
  function pill(text) { return el('span', {class: 'pill', text: text}); }
  function fact(k, v, klass) { return el('div', {class: 'fact'}, el('p', {class: 'k', text: k}), el('p', {class: 'v ' + (klass || ''), text: v})); }
  function sideText(side) { return side === 'long' ? '▲ acheteur' : '▼ vendeur à découvert'; }
  function tradesText(n) { return !n ? 'aucun trade terminé' : n === 1 ? '1 trade' : n + ' trades'; }
  function winText(rate) { return rate === null || rate === undefined ? '' : ' · ' + Math.round(100 * rate) + ' % gagnants'; }
  const TEAMS = {scalping: 'Scalping', court: 'Court terme', long: 'Long terme'};
  const TF_LABELS = {'1m': '1 min', '5m': '5 min', '15m': '15 min', '1h': '1 h', '4h': '4 h', '1d': '1 jour'};
  const CHART_TFS = ['1m', '5m', '15m', '1h', '4h', '1d'];
  function chartEvery(tf) { return {'1m': 10000, '5m': 20000, '15m': 30000}[tf] || 60000; }
  function statusChip(b) {
    if (b.position) return chip('live', 'en position');
    if (b.dead) return chip('bad', 'arrêté');
    if (b.status === 'veille') return chip('idle', 'en veille');
    if (b.status === 'sortie') return chip('warn', 'en sortie');
    return chip('idle', 'attend son signal');
  }
  const SHORT_EXITS = {'sortie par la règle': '', 'objectif 2R': '2R', 'stop suiveur': 'stop suiveur',
    'objectif 2R + stop sécurisé': '2R + sécurisé', 'stop sécurisé': 'stop sécurisé'};
  function exitLabel(target, mode) {  // comme swarm.exit_label
    if (mode === 'suiveur') return 'stop suiveur';
    if (mode === 'securise') return target ? 'objectif 2R + stop sécurisé' : 'stop sécurisé';
    return target ? 'objectif 2R' : 'sortie par la règle';
  }
  function exitShort(b) { const s = SHORT_EXITS[b.exit || exitLabel(b.target_r, b.stop_mode)]; return s ? ' · ' + s : ''; }
  function liveChip(verdict) {
    if (verdict === 'prouvee') return chip('ok', 'stratégie prouvée à l\'essai');
    if (verdict === 'recalee') return chip('bad', 'stratégie recalée à l\'essai');
    return null;
  }
  function thousands(v) { return (v || 0).toLocaleString('fr-FR'); }
  function probaText(p) {
    if (!p) return 'Estimation disponible à la prochaine bougie.';
    return 'D\'après ' + p.trades + ' trades de son backtest, dans les conditions du moment (' + (p.conditions && p.conditions.length
      ? p.conditions.join(', ') : 'aucune assez fréquente : moyenne de la stratégie') + ') ; ' + Math.round(100 * p.base)
      + ' % en moyenne. Une estimation, pas une promesse.';
  }

  // --- navigation ---
  const VIEWS = ['direct', 'cryptos', 'crypto', 'bot', 'strategies', 'actualite', 'prix', 'ecole', 'reglages', 'journal'];
  const MORE_VIEWS = ['ecole', 'reglages', 'journal'];
  const moreToggle = $('#more-toggle'), moreTabs = $('#more-tabs');
  function setMore(open) { moreTabs.hidden = !open; moreToggle.setAttribute('aria-expanded', String(open)); }
  moreToggle.addEventListener('click', () => setMore(moreTabs.hidden));
  let view = 'direct', coinName = null, botKey = null;
  function show(name) {
    const parts = String(name || '').split('/'), head = parts[0], sub = parts.slice(1).join('/');
    if (head === 'crypto' && /^[A-Za-z0-9]{1,20}$/.test(sub)) {
      view = 'crypto';
      if (coinName !== sub.toUpperCase()) { coinName = sub.toUpperCase(); coinData = null; coinChart = null; coinTf = null; }
    } else if (head === 'bot' && /^[0-9a-f]{10}$/.test(sub)) {
      view = 'bot';
      if (botKey !== sub) { botKey = sub; botData = null; botChart = null; }
    } else view = VIEWS.includes(head) && head !== 'crypto' && head !== 'bot' ? head : 'direct';
    for (const v of VIEWS) $('#view-' + v).hidden = v !== view;
    const tab = view === 'crypto' || view === 'bot' ? 'cryptos' : view;
    document.querySelectorAll('.tabs a').forEach(a => {
      if (a.dataset.view === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (MORE_VIEWS.includes(view)) setMore(true);
    if (view === 'reglages') loadSettings();
    if (view === 'ecole') loadSchool(sub).catch(e => toast(e.message, true));
    for (const k in last) last[k] = 0;
    render();
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));

  // --- état général ---
  let state = null, pricesReady = false;
  async function refreshState() {
    try {
      state = await getJSON('/api/etat');
      $('#mode-badge').textContent = state.mode_label;
      const w = $('#settings-warning');
      w.hidden = !state.settings_error;
      w.textContent = state.settings_error ? 'Réglages invalides : ' + state.settings_error : '';
      renderJournalList(state.tasks);
    } catch (e) { $('#mode-badge').textContent = 'site arrêté ?'; }
  }
  async function launch(key) {
    try { await post('/api/lancer', {action: key}); toast('C\'est parti : les bots démarrent.'); last.swarm = 0; refreshState(); }
    catch (e) { toast(e.message, true); }
  }
  async function stopBots(task) {
    if (!confirm('Arrêter tous les bots ? Leurs positions et leurs comptes sont gardés : ils reprennent au prochain lancement.')) return;
    try { await post('/api/arreter', {tache: task.id}); toast('Les bots s\'arrêtent.'); last.swarm = 0; refreshState(); }
    catch (e) { toast(e.message, true); }
  }
  function render() {
    if (view === 'direct' && swarm) renderDirect();
    if (view === 'cryptos' && swarm) renderCoins();
    if (view === 'strategies' && swarm) renderStrategies();
    if (view === 'crypto') renderCoin();
    if (view === 'bot') renderBot();
  }

  // --- direct : tous les bots, en bref ---
  let swarm = null;
  const PAGE_SIZE = 30;
  const filter = {team: 'tous', status: 'tous', sort: 'pnl', limit: PAGE_SIZE};
  try { const f = JSON.parse(localStorage.getItem('filtre-bots') || '{}'); for (const k of ['team', 'status', 'sort']) if (f[k]) filter[k] = f[k]; } catch (e) {}
  function saveFilter() { try { localStorage.setItem('filtre-bots', JSON.stringify({team: filter.team, status: filter.status, sort: filter.sort})); } catch (e) {} }
  async function refreshSwarm() {
    try { swarm = await getJSON('/api/bots'); }
    catch (e) {
      $('#swarm-title').textContent = 'Le site ne répond plus';
      $('#swarm-text').textContent = 'La fenêtre noire du bot a peut-être été fermée. Relance « Ouvrir le bot ».';
      return;
    }
    render();
  }
  function seg(id, options, current, onpick) {
    $(id).replaceChildren(...options.map(([key, text]) => el('button', {type: 'button', 'aria-pressed': String(key === current),
      text: text, onclick: () => onpick(key)})));
  }
  const SORTS = {pnl: (a, b) => b.pnl - a.pnl, worst: (a, b) => a.pnl - b.pnl, trades: (a, b) => b.count - a.count,
    coin: (a, b) => a.coin.localeCompare(b.coin) || a.technique.localeCompare(b.technique),
    recent: (a, b) => String(b.started).localeCompare(String(a.started))};
  function renderDirect() {
    const d = swarm, step = d.step;
    $('#swarm-title').textContent = step.title;
    $('#swarm-text').textContent = step.text;
    const row = $('#swarm-actions'); row.replaceChildren();
    if (step.action) row.append(el('button', {class: 'btn btn-primary', type: 'button', disabled: !!d.action.blocked,
      title: d.action.blocked || null, text: 'Lancer les bots', onclick: () => launch('flotte')}));
    if (d.ready) row.append(el('a', {class: 'btn', href: '#cryptos', text: 'Voir les cryptos'}),
      el('a', {class: 'btn', href: '#strategies', text: 'Le classement des stratégies'}));
    const task = state && (state.tasks || []).find(x => x.action === 'flotte' && x.status === 'en cours');
    if (task) row.append(el('button', {class: 'btn', type: 'button', text: 'Arrêter les bots', onclick: () => stopBots(task)}));
    const t = d.totals || {};
    $('#swarm-kpis').replaceChildren(
      tile('Valeur de tous les bots', usdt(t.value), t.start ? 'pour ' + usdt(t.start) + ' fictifs au départ' : 'pas encore de bot', true),
      tile('Résultat', pct(t.pnl_pct), usdt(t.pnl, true) + (t.retired ? ' · ' + t.retired + ' bots arrêtés compris' : '')),
      tile('Bots', String(t.bots || 0), (t.positions || 0) + ' en position · jusqu\'à ' + (d.max_bots || '?')),
      tile('Trades terminés', String(t.count || 0), t.win_rate === null || t.win_rate === undefined ? 'aucun encore' :
        Math.round(100 * t.win_rate) + ' % gagnants'),
      tile('Humeur du marché', d.mood ? Math.round(d.mood.value) + ' / 100' : '—', d.mood ? 'peur et avidité : ' + d.mood.zone : 'indisponible'));
    const tr = d.trial || {}, ho = d.holdout || {}, ref = d.reference;
    $('#trial-box').hidden = !d.ready;
    $('#trial-facts').replaceChildren(
      fact('Bots à l\'essai', thousands(tr.bots) + (tr.coins ? ' sur ' + tr.coins + (tr.coins > 1 ? ' cryptos' : ' crypto') : '')),
      fact('Trades comptés', tr.n ? thousands(tr.n) + ' en ' + tr.days + (tr.days > 1 ? ' jours' : ' jour') : 'aucun encore'),
      fact('Par trade, à l\'essai', tr.n ? pct(tr.mean, 2) + (tr.lo === null || tr.lo === undefined ? '' : ' (de ' + pct(tr.lo, 2) + ' à ' + pct(tr.hi, 2) + ')') : '—', tr.n ? cls(tr.mean) : ''),
      fact('Test final des choix du labo', ho.n ? pct(ho.mean, 2) + ' par trade · ' + thousands(ho.n) + ' trades' : '—', ho.n ? cls(ho.mean) : ''),
      fact('Point de référence' + (ref ? ' (' + dayLabel(Date.parse(ref.saved)) + ')' : ''), !ref ? '—' : !ref.count ? 'aucun trade avant' :
        thousands(ref.count) + ' trades · ' + Math.round(100 * ref.win_rate) + ' % gagnants · ' + pct(ref.pnl_pct, 1)));
    seg('#filter-team', [['tous', 'Tous'], ['scalping', 'Scalping'], ['court', 'Court terme'], ['long', 'Long terme']], filter.team,
      k => { filter.team = k; filter.limit = PAGE_SIZE; saveFilter(); renderDirect(); });
    seg('#filter-status', [['tous', 'Tous'], ['position', 'En position'], ['actif', 'Actifs'], ['veille', 'En veille']], filter.status,
      k => { filter.status = k; filter.limit = PAGE_SIZE; saveFilter(); renderDirect(); });
    $('#bots-sort').value = filter.sort;
    let bots = (d.bots || []).filter(b => (filter.team === 'tous' || b.team === filter.team) &&
      (filter.status === 'tous' || (filter.status === 'position' ? !!b.position : b.status === filter.status)));
    bots.sort(SORTS[filter.sort] || SORTS.pnl);
    const total = bots.length;
    bots = bots.slice(0, filter.limit);
    $('#bots-count').textContent = total + (total > 1 ? ' bots' : ' bot') + (total > bots.length ? ' · les ' + bots.length + ' premiers' : '');
    const body = $('#bots-rows'); body.replaceChildren();
    if (!total) body.append(el('tr', {}, el('td', {colspan: '6', class: 'muted wrap', text: d.ready && (d.bots || []).length
      ? 'Aucun bot pour ce filtre.' : 'Les bots apparaîtront ici dès que le labo en direct aura trouvé des combinaisons gagnantes.'})));
    for (const b of bots) {
      const p = b.position;
      body.append(el('tr', {class: 'clickable', onclick: e => { if (!e.target.closest('a')) location.hash = '#bot/' + b.id; }},
        el('td', {class: 'pair'}, el('a', {href: '#bot/' + b.id, text: b.coin}),
          el('span', {class: 'sub', text: b.tf_label + ' · ' + (b.side === 'long' ? '▲ achat' : '▼ vente')}),
          el('span', {class: 'sub mob', text: b.technique + exitShort(b)})),
        el('td', {class: 'wrap opt', text: b.technique + exitShort(b)}),
        el('td', {class: 'opt'}, statusChip(b)),
        el('td', {class: 'n ' + cls(b.pnl), text: pct(b.pnl_pct, 1)}),
        el('td', {class: 'n ' + (p ? cls(p.roi) : ''), text: p ? pct(p.roi, 1) : '—'}),
        el('td', {class: 'n opt', text: String(b.count)})));
    }
    const more = $('#bots-more'); more.replaceChildren();
    if (total > bots.length) more.append(el('button', {class: 'btn', type: 'button', text: 'Voir ' + Math.min(PAGE_SIZE, total - bots.length) + ' bots de plus',
      onclick: () => { filter.limit += PAGE_SIZE; renderDirect(); }}));
    const events = $('#swarm-events'); events.replaceChildren();
    if (!(d.events || []).length) events.append(el('li', {}, el('span', {class: 'muted', text: 'Rien encore.'})));
    for (const e of (d.events || []).slice(0, 15)) {
      const href = e.bot ? '#bot/' + e.bot : e.symbol ? '#crypto/' + coin(e.symbol) : null;
      events.append(el('li', {class: 'ev-' + e.kind}, el('time', {datetime: e.t, text: ago(e.t)}),
        href ? el('a', {href: href, text: e.text}) : el('span', {text: e.text})));
    }
  }
  $('#bots-sort').addEventListener('change', e => { filter.sort = e.target.value; saveFilter(); renderDirect(); });

  // --- le classement des stratégies : à l'essai (toutes les combinaisons) ou en direct (les bots choisis) ---
  let rankBy = 'all', rankSource = 'essai', rankTf = 'toutes', rankLimit = PAGE_SIZE;
  // Le classement fait comme si chaque stratégie avait des trades nuls de plus : 10 pour les bots en direct, 200 pour la
  // mesure à l'essai, qui en compte cent fois plus.
  const PRUDENCE = {direct: 10, essai: 200};
  try { rankBy = localStorage.getItem('classement') || 'all'; rankSource = localStorage.getItem('classement-mesure') || 'essai'; } catch (e) {}
  const SIDE_NAMES = {long: '▲ à l\'achat', short: '▼ à la vente à découvert'};
  const RANK_TEXT = {
    essai: {all: '30 jours',
      meta: 'À l\'essai : toutes les combinaisons tournent en argent fictif sur chaque crypto qui bouge, et tous leurs trades sont comptés, sans '
        + 'rien choisir d\'avance. Une stratégie : une technique dans une unité de temps, toutes cryptos réunies. Après 7 jours, une stratégie '
        + 'nettement gagnante est « prouvée » et passe en priorité aux tests ; une stratégie nettement perdante est « recalée » : ses bots '
        + 's\'arrêtent après leur trade.',
      note: 'Fourchette : où se trouve probablement le vrai gain moyen. Elle compare les journées entre elles, parce que les trades d\'une même '
        + 'journée se ressemblent (quand le marché chute, toutes les ventes à découvert gagnent ensemble) : mille trades le même jour ne '
        + 'valent pas mille preuves. Tant qu\'elle contient zéro, rien n\'est prouvé ; « prouvée » demande en plus un seuil durci, parce que '
        + 'sur des dizaines de stratégies la chance en ferait gagner. '},
    direct: {all: 'Tout le direct',
      meta: 'En direct : seulement les trades finis de tes bots, comptés pour leur stratégie (une technique dans une unité de temps, toutes '
        + 'cryptos réunies). C\'est ce qu\'ils ont vraiment fait ; le verdict, lui, vient de la mesure à l\'essai, qui compte bien plus de trades.',
      note: 'Fourchette : où se trouve probablement le vrai gain moyen ; tant qu\'elle contient zéro, rien n\'est prouvé. '}};
  const rankNote = extra => '« Par trade » : le gain moyen d\'un trade, frais compris, sans levier (pour comparer des bots qui n\'ont pas le '
    + 'même levier). Classement prudent : une stratégie qui a peu de trades est tirée vers zéro (comme si elle avait ' + extra + ' trades nuls '
    + 'de plus), pour qu\'un seul coup de chance ne la mette pas en tête. Aujourd\'hui et 7 jours : gain moyen par trade · nombre de trades '
    + '(la journée commence à minuit en temps universel, 1 h du matin en France l\'hiver). Le classement du jour est là pour information : '
    + 'sur une journée, c\'est surtout du hasard.';
  function verdictChip(r, minDays) {
    if (r.verdict === 'prouvee') return chip('ok', 'prouvée');
    if (r.verdict === 'recalee') return chip('bad', 'recalée');
    if (r.days !== undefined && r.days < minDays) return chip('idle', r.days + ' / ' + minDays + ' jours');
    return chip('idle', 'à confirmer');
  }
  function periodText(n, mean) { return n ? pct(mean, 2) + ' · ' + thousands(n) : '—'; }
  function smallRanking(title, rows, name) {
    return el('div', {}, el('h3', {class: 'group-title', text: title}), rows.length ? el('div', {class: 'table-wrap'}, el('table', {},
      el('thead', {}, el('tr', {}, el('th', {text: ''}), el('th', {class: 'n', text: 'Trades'}), el('th', {class: 'n', text: 'Gagnants'}),
        el('th', {class: 'n', text: 'Par trade'}), el('th', {class: 'n opt', text: 'Aujourd\'hui'}))),
      el('tbody', {}, ...rows.map(r => el('tr', {}, el('td', {text: name(r.key)}), el('td', {class: 'n', text: thousands(r.n)}),
        el('td', {class: 'n', text: Math.round(100 * r.win) + ' %'}), el('td', {class: 'n ' + cls(r.mean), text: pct(r.mean, 2)}),
        el('td', {class: 'n opt ' + cls(r.today_mean), text: periodText(r.today_n, r.today_mean)})))))) :
      el('p', {class: 'muted', text: 'Pas encore de trade terminé.'}));
  }
  function renderStrategies() {
    const essai = rankSource !== 'direct', trial = swarm.trial || {}, text = RANK_TEXT[essai ? 'essai' : 'direct'];
    const r = (essai ? trial.ranking : swarm.ranking) || {strategie: [], sortie: [], sens: [], unite: []};
    const minDays = (trial.ranking || {}).min_days || 7;
    seg('#rank-source', [['essai', 'À l\'essai : tout est mesuré'], ['direct', 'En direct : tes bots']], essai ? 'essai' : 'direct', k => {
      rankSource = k; rankLimit = PAGE_SIZE; try { localStorage.setItem('classement-mesure', k); } catch (e) {} renderStrategies(); });
    $('#rank-meta').textContent = typo(text.meta);
    const extra = PRUDENCE[essai ? 'essai' : 'direct'];
    $('#rank-note').textContent = typo(text.note + rankNote(extra));
    seg('#rank-period', [['all', text.all], ['week', '7 jours'], ['today', 'Aujourd\'hui']], rankBy, k => {
      rankBy = k; rankLimit = PAGE_SIZE; try { localStorage.setItem('classement', k); } catch (e) {} renderStrategies(); });
    seg('#rank-tf', [['toutes', 'Toutes']].concat(['1m', '5m', '15m', '1h', '4h'].map(tf => [tf, TF_LABELS[tf]])), rankTf, k => {
      rankTf = k; rankLimit = PAGE_SIZE; renderStrategies(); });
    // la période choisie : nombre de trades et gain moyen ; le classement est prudent (peu de trades = tiré vers zéro)
    const period = x => rankBy === 'today' ? [x.today_n, x.today_mean] : rankBy === 'week' ? [x.week_n, x.week_mean] : [x.n, x.mean];
    const prudent = x => { const [n, m] = period(x); return n ? m * n / (n + extra) : -1e9; };
    const every = r.strategie || [];
    const wanted = every.filter(x => rankTf === 'toutes' || x.timeframe === rankTf).sort((a, b) => prudent(b) - prudent(a));
    const rows = wanted.slice(0, rankLimit);
    $('#rank-head').textContent = {all: 'Par trade', week: 'Par trade, 7 jours', today: 'Par trade, aujourd\'hui'}[rankBy];
    const proven = every.filter(x => x.verdict === 'prouvee').length, failed = every.filter(x => x.verdict === 'recalee').length;
    const verdicts = proven + ' prouvée' + (proven > 1 ? 's' : '') + ' · ' + failed + ' recalée' + (failed > 1 ? 's' : '') + '.';
    $('#rank-intro').textContent = !every.length ? (essai ? 'La mesure se remplit à chaque test d\'une crypto : les premiers trades arrivent '
        + 'une demi-heure à une heure après le lancement, puis toutes les 3 heures.' : 'Le classement se remplit à chaque trade fini d\'un bot.') :
      essai ? thousands(trial.bots) + ' bots à l\'essai · ' + thousands(trial.n) + ' trades comptés en ' + trial.days + (trial.days > 1 ? ' jours' : ' jour')
        + ' · ' + every.length + ' stratégies · ' + verdicts :
      every.length + ' stratégies ont déjà fini des trades en direct · ' + verdicts;
    const body = $('#rank-rows'); body.replaceChildren();
    if (!rows.length) body.append(el('tr', {}, el('td', {colspan: '8', class: 'muted wrap', text: every.length ? 'Aucune stratégie dans cette unité '
      + 'de temps pour l\'instant.' : 'Aucun trade terminé pour l\'instant.'})));
    for (const x of rows) {
      const [n, m] = period(x);
      body.append(el('tr', {class: x.verdict === 'prouvee' ? 'strong-row' : null},
      el('td', {class: 'wrap'}, el('strong', {text: x.technique}), el('span', {class: 'sub', text: x.tf_label + ' · ' + tradesText(n)})),
      el('td', {class: 'n opt', text: thousands(x.n)}),
      el('td', {class: 'n opt', text: Math.round(100 * x.win) + ' %'}),
      el('td', {class: 'n focus ' + cls(m), text: n ? pct(m, 2) : '—'}),
      el('td', {class: 'n opt', text: x.lo === null || x.lo === undefined ? '—' : pct(x.lo, 2) + ' à ' + pct(x.hi, 2)}),
      el('td', {class: 'n opt ' + cls(x.today_mean), text: periodText(x.today_n, x.today_mean)}),
      el('td', {class: 'n opt ' + cls(x.week_mean), text: periodText(x.week_n, x.week_mean)}),
      el('td', {}, verdictChip(x, minDays))));
    }
    const next = $('#rank-next'); next.replaceChildren();
    if (wanted.length > rows.length) next.append(el('button', {class: 'btn', type: 'button', text: 'Voir ' + Math.min(PAGE_SIZE, wanted.length - rows.length)
      + ' stratégies de plus (' + (wanted.length - rows.length) + ' restantes)', onclick: () => { rankLimit += PAGE_SIZE; renderStrategies(); }}));
    $('#rank-exits').replaceChildren(smallRanking('Par façon de sortir', r.sortie || [], k => k.charAt(0).toUpperCase() + k.slice(1)));
    $('#rank-more').replaceChildren(smallRanking('Par sens', r.sens || [], k => SIDE_NAMES[k] || k),
      smallRanking('Par unité de temps', r.unite || [], k => TF_LABELS[k] || k));
  }

  // --- les cryptos suivies ---
  function coinStatus(c) {
    if (!c) return ['idle', 'pas suivie en ce moment'];
    if (!c.followed) return ['idle', 'plus suivie'];
    if (!c.moving) return ['idle', 'en veille : pas assez de mouvement'];
    return {actif: ['ok', 'des bots tournent'], 'test en cours': ['live', 'test en cours'],
      'aucune stratégie gagnante': ['warn', 'rien de gagnant pour l\'instant'], 'en attente de test': ['idle', 'en attente de test'],
      'test impossible': ['bad', 'test impossible']}[c.status] || ['idle', c.status || '—'];
  }
  function renderCoins() {
    const d = swarm, t = d.totals || {}, minMove = (d.settings || {}).min_move;
    $('#coins-intro').textContent = (t.coins || 0) + ' cryptos suivies : les plus agitées du moment (au moins 5 M$ échangés par '
      + 'jour), relues toutes les 10 minutes. Une crypto dont l\'amplitude sur 24 h passe sous ' + pct(minMove === undefined ? 0.03 : minMove, 0).replace('+', '')
      + ' passe en veille : ses bots n\'ouvrent plus de trade. Touche une crypto pour voir ses bots, son graphique et ce que le labo y a testé.';
    const body = $('#coins-rows'); body.replaceChildren();
    if (!(d.coins || []).length) body.append(el('tr', {}, el('td', {colspan: '7', class: 'muted wrap', text: 'La liste arrive au premier tour des bots.'})));
    for (const c of d.coins || []) {
      const [kind, text] = coinStatus(c);
      body.append(el('tr', {class: 'clickable', onclick: e => { if (!e.target.closest('a')) location.hash = '#crypto/' + c.coin; }},
        el('td', {class: 'pair'}, el('a', {href: '#crypto/' + c.coin, text: c.coin})),
        el('td', {class: 'n ' + cls(c.change), text: pct(c.change, 1)}),
        el('td', {class: 'n opt', text: pct(c.amplitude, 1).replace('+', '')}),
        el('td', {class: 'wrap'}, chip(kind, text)),
        el('td', {class: 'n', text: String(c.bots)}),
        el('td', {class: 'n opt', text: String(c.positions)}),
        el('td', {class: 'n ' + cls(c.pnl), text: c.bots ? usdt(c.pnl, true) : '—'})));
    }
  }

  // --- une crypto : ses bots, son graphique, son test ---
  let coinData = null, coinChart = null, coinTf = null, coinSig = '';
  async function refreshCoin() {
    try { coinData = await getJSON('/api/crypto?c=' + encodeURIComponent(coinName)); }
    catch (e) { coinData = {error: e.message}; }
    if (!coinData.error) {
      if (!coinTf) { coinTf = coinData.timeframes[0] || '15m'; last.coinChart = 0; }
      const sig = coinData.bots.map(b => b.id + ':' + (b.position ? b.position.entry_ts : 0) + ':' + b.count).join(',');
      if (sig !== coinSig) { coinSig = sig; last.coinChart = 0; }  // une position ouverte ou fermée : le graphique suit
    }
    render();
  }
  async function refreshCoinChart() {
    const tf = coinTf;
    try { const d = await getJSON('/api/crypto-graphique?c=' + encodeURIComponent(coinName) + '&unite=' + tf); if (tf === coinTf) coinChart = d; }
    catch (e) { if (tf === coinTf) coinChart = {error: e.message}; last.coinChart = Date.now() - chartEvery(tf) + 5000; }
    drawCoinChart();
  }
  function coinSkeleton(box) {
    box.dataset.coin = coinName;
    box.replaceChildren(
      el('div', {class: 'panel-head', id: 'coin-head'}),
      el('div', {class: 'facts', id: 'coin-facts'}),
      el('section', {}, el('div', {class: 'section-head'}, el('h2', {text: 'Son graphique'}),
        el('div', {class: 'seg', role: 'group', 'aria-label': 'Unité de temps', id: 'coin-tfs'})),
        el('div', {id: 'coin-chart'}), el('div', {class: 'legend', id: 'coin-legend'})),
      el('section', {}, el('h2', {text: 'Ses bots'}), el('div', {id: 'coin-bots'})),
      el('section', {id: 'coin-reading'}),
      el('section', {id: 'coin-news'}),
      el('section', {id: 'coin-best'}));
  }
  function renderCoin() {
    const box = $('#coin-page');
    if (!coinData || coinData.error) {
      box.dataset.coin = '';
      box.replaceChildren(el('p', {class: coinData ? 'empty-box' : 'muted', text: coinData ? coinData.error : 'Chargement de ' + coinName + '…'}));
      return;
    }
    const fresh = box.dataset.coin !== coinName || !$('#coin-chart');
    if (fresh) coinSkeleton(box);
    const d = coinData, c = d.info || {};
    const [kind, text] = coinStatus(d.info);
    $('#coin-head').replaceChildren(el('div', {}, el('p', {class: 'eyebrow', text: 'Crypto suivie par les bots'}), el('h1', {text: d.coin})),
      el('div', {class: 'chips'}, chip(kind, text)));
    const price = coinChart && coinChart.last && coinChart.timeframe === coinTf ? coinChart.last : c.price;
    $('#coin-facts').replaceChildren(fact('Prix', precise(price)), fact('Sur 24 h', pct(c.change, 1), cls(c.change)),
      fact('Amplitude 24 h', pct(c.amplitude, 1).replace('+', '')), fact('Volume 24 h', money(c.volume)),
      fact('Bots', String(d.bots.length)), fact('Dernier test', c.tested ? when(c.tested) : 'pas encore'),
      fact('Prochain test', c.next_test ? when(c.next_test) : '—'));
    $('#coin-tfs').replaceChildren(...CHART_TFS.map(tf => el('button', {type: 'button', 'aria-pressed': String(tf === coinTf),
      text: TF_LABELS[tf] + (d.timeframes.includes(tf) ? ' ●' : ''), title: d.timeframes.includes(tf) ? 'Des bots tournent dans cette unité' : null,
      onclick: () => { coinTf = tf; coinChart = null; last.coinChart = 0; renderCoin(); drawCoinChart(); }})));
    $('#coin-bots').replaceChildren(d.bots.length ? el('div', {class: 'bot-grid'}, ...d.bots.map(botCard)) :
      el('p', {class: 'empty-box', text: c.status === 'aucune stratégie gagnante' ? 'Le dernier test n\'a trouvé aucune combinaison '
        + 'gagnante sur l\'étude et la validation : pas de bot ici, c\'est voulu.' : 'Pas de bot sur cette crypto pour l\'instant.'}));
    const mood = d.mood ? 'Humeur du marché : ' + Math.round(d.mood.value) + ' / 100 (' + d.mood.zone + ').' : 'Humeur du marché indisponible.';
    $('#coin-news').replaceChildren(el('h2', {text: 'L\'humeur et l\'actualité'}), el('p', {class: 'muted', text: mood}),
      ...(d.news.length ? d.news.map(n => el('div', {class: 'news-item'}, el('a', {href: n.link, target: '_blank', rel: 'noopener noreferrer', text: n.title}),
        el('div', {class: 'meta-line', text: n.source + ' · ' + ago(n.published)}))) :
        [el('p', {class: 'muted', text: 'Aucun titre récent ne cite ' + d.coin + '.'})]));
    $('#coin-best').replaceChildren(...bestTable(c));
    if (fresh) drawCoinChart();
  }
  function botCard(b) {
    const p = b.position;
    return el('a', {class: 'card botcard', href: '#bot/' + b.id},
      el('div', {class: 'card-head'}, el('h3', {text: b.technique}), statusChip(b)),
      el('p', {class: 'muted', text: b.tf_label + ' · ' + sideText(b.side) + ' · levier ×' + dec(b.leverage) + exitShort(b)
        + (b.live === 'prouvee' ? ' · stratégie prouvée' : '')}),
      el('p', {class: 'big'}, usdt(b.value), el('span', {class: 'delta ' + cls(b.pnl), text: pct(b.pnl_pct, 1)})),
      el('p', {class: 'muted', text: tradesText(b.count) + winText(b.win_rate) + (b.proba ? ' · chances estimées ' + Math.round(100 * b.proba.p) + ' %' : '')}),
      p ? el('p', {class: 'pos-line'}, (p.side === 'long' ? 'Acheté ' : 'Vendu ') + precise(p.price) + ' · stop ' + precise(p.stop)
        + (p.target ? ' · objectif ' + precise(p.target) : '') + ' · ', el('span', {class: cls(p.roi), text: pct(p.roi, 1)})) : null);
  }
  function bestTable(c) {
    const rows = (c.best || []).map(r => el('tr', {},
      el('td', {class: 'wrap', text: r.technique + exitShort(r) + (r.live === 'prouvee' ? ' · prouvée à l\'essai' : r.live === 'recalee'
        ? ' · recalée à l\'essai' : '')}),
      el('td', {text: TF_LABELS[r.timeframe] + ' · ' + (r.side === 'long' ? 'achat' : 'vente')}),
      el('td', {class: 'n', text: String(r.sv_n)}),
      el('td', {class: 'n ' + cls(r.sv_mean), text: pct(r.sv_mean, 2)}),
      el('td', {class: 'n opt ' + cls(r.test_mean), text: r.test_n ? pct(r.test_mean, 2) : '—'}),
      el('td', {class: 'n opt', text: bigPct(r.total_return)}),
      el('td', {text: r.eligible ? '✓' : '✕', title: r.eligible ? 'Gagnante sur l\'étude et la validation : peut devenir un bot' : null})));
    return [el('h2', {text: 'Ce que le labo en direct y a testé'}),
      el('p', {class: 'meta', text: c.n_tested ? c.n_tested + ' combinaisons testées sur l\'historique récent (frais des contrats à terme compris), '
        + (c.n_eligible || 0) + ' gagnantes sur l\'étude et la validation ; toutes sont mesurées à l\'essai. Les mieux classées :' : 'Pas encore testée.'}),
      rows.length ? el('div', {class: 'table-wrap'}, el('table', {}, el('thead', {}, el('tr', {}, el('th', {text: 'Combinaison'}),
        el('th', {text: 'Unité · sens'}), el('th', {class: 'n', text: 'Trades'}), el('th', {class: 'n', text: 'Par trade'}),
        el('th', {class: 'n opt', text: 'Test final'}), el('th', {class: 'n opt', text: 'Avec levier'}), el('th', {text: 'Bot'}))), el('tbody', {}, ...rows))) : null,
      el('p', {class: 'note', text: 'Par trade : le gain moyen d\'un trade, frais compris, sans levier, sur l\'étude et la validation. Test final : les '
        + 'derniers 20 % de l\'historique, jamais regardés pour choisir : ils mesurent ce que vaut le choix. Avec levier : le capital d\'un bot sur '
        + 'tout l\'historique. Choisir parmi des centaines de combinaisons fait toujours sortir des gagnants par chance : ce sont la mesure à '
        + 'l\'essai et le direct qui tranchent.'})];
  }
  function drawCoinChart() {
    const host = $('#coin-chart');
    if (!host) return;
    if (!coinChart || coinChart.error) {
      host._chart = null;
      host.replaceChildren(el('p', {class: 'muted', text: coinChart ? coinChart.error + ' Nouvel essai dans quelques secondes…' : 'Chargement du graphique…'}));
      $('#coin-legend').replaceChildren();
      return;
    }
    const d = coinChart, marks = [], markers = [], labelled = d.positions.length <= 2;
    for (const p of d.positions) {
      const who = labelled && d.positions.length > 1 ? ' (' + p.name + ')' : '';
      marks.push({price: p.price, color: 'var(--text-secondary)', label: labelled ? (p.side === 'long' ? 'Achat ' : 'Vente ') + precise(p.price) + who : null});
      marks.push({price: p.stop, color: 'var(--critical)', label: labelled ? 'Stop ' + precise(p.stop) + who : null});
      if (p.target) marks.push({price: p.target, color: 'var(--good)', label: labelled ? 'Objectif ' + precise(p.target) + who : null});
      markers.push({ts: p.entry_ts, up: p.side === 'long', fill: 'var(--text-primary)', stroke: 'var(--surface-1)'});
    }
    for (const t of d.trades) {
      markers.push({ts: t.entry, up: t.side === 'long', fill: 'var(--text-primary)', stroke: 'var(--surface-1)'});
      markers.push({ts: t.exit, up: t.side !== 'long', fill: t.net > 0 ? 'var(--up)' : 'var(--down)', stroke: 'var(--surface-1)'});
    }
    zoomChart(host, {key: 'coin-' + d.symbol + '-' + d.timeframe, candles: d.candles, lines: [], zones: d.levels,
      marks: marks, markers: markers, label: 'Graphique de ' + coin(d.symbol) + ' en ' + TF_LABELS[d.timeframe]});
    $('#coin-legend').replaceChildren(...chartLegend(d, d.positions.length > 0, false));
    const r = d.reading, box = $('#coin-reading');
    if (r && box) box.replaceChildren(el('h2', {text: 'Comme un trader la lit (' + TF_LABELS[d.timeframe] + ')'}),
      el('div', {class: 'facts'}, fact('Tendance de fond', r.trend || '—'),
        fact('RSI (14)', r.rsi === null || r.rsi === undefined ? '—' : String(Math.round(r.rsi))),
        fact('Bougie moyenne', pct(r.candle_pct, 2).replace('+', '')),
        fact('Sur 24 bougies', pct(r.change, 1), cls(r.change)),
        fact('Support', r.support ? precise(r.support.price) + ' (' + pct(r.support.distance, 1) + ')' : 'aucun proche'),
        fact('Résistance', r.resistance ? precise(r.resistance.price) + ' (' + pct(r.resistance.distance, 1) + ')' : 'aucune proche')),
      el('ul', {class: 'reading'}, ...(r.sentences || []).map(x => el('li', {text: x}))),
      el('p', {class: 'note', text: 'Une lecture pour comprendre, jamais un ordre : un bot n\'entre que sur le signal de sa règle testée.'}));
  }

  // --- un bot ---
  let botData = null, botChart = null, botSig = '';
  async function refreshBot() {
    try { botData = await getJSON('/api/bot?id=' + encodeURIComponent(botKey)); }
    catch (e) { botData = {error: e.message}; }
    if (!botData.error) {
      const sig = (botData.position ? botData.position.entry_ts : 0) + ':' + botData.count;
      if (sig !== botSig) { botSig = sig; last.botChart = 0; }
    }
    render();
  }
  async function refreshBotChart() {
    const key = botKey;
    try { const d = await getJSON('/api/bot-graphique?id=' + encodeURIComponent(key)); if (key === botKey) botChart = d; }
    catch (e) { if (key === botKey) botChart = {error: e.message}; last.botChart = Date.now() - 55000; }
    drawBotChart();
  }
  function botSkeleton(box) {
    box.dataset.bot = botKey;
    box.dataset.trades = '';
    box.replaceChildren(
      el('div', {class: 'panel-head', id: 'bot-head'}),
      el('p', {id: 'bot-rule'}), el('p', {class: 'muted', id: 'bot-exit'}),
      el('div', {id: 'bot-position'}),
      el('section', {}, el('h2', {id: 'bot-chart-title'}), el('div', {id: 'bot-chart'}), el('div', {class: 'legend', id: 'bot-legend'})),
      el('section', {id: 'bot-agents'}),
      el('section', {id: 'bot-compare'}),
      el('section', {id: 'bot-curve'}),
      el('section', {id: 'bot-trades'}),
      el('section', {id: 'bot-card'}));
  }
  function positionBox(b) {
    const p = b.position;
    if (!p) return el('div', {class: 'position-box'}, el('p', {class: 'muted', text: b.dead ? 'Arrêté : ' + b.dead + '.' :
      b.status === 'veille' ? 'En veille : la crypto ne bouge pas assez, il n\'ouvre pas de trade.' :
      b.status === 'sortie' ? 'En sortie : sa stratégie est recalée (elle perd nettement à l\'essai), il s\'arrête.' :
      'Pas de position : il attend son signal.' + (b.pending && b.pending.kind === 'entry' ? ' Son signal vient de tomber : il entre au prochain tour.' : '')}));
    const long = p.side === 'long';
    return el('div', {class: 'position-box'},
      el('p', {}, el('strong', {text: (long ? '▲ Acheté' : '▼ Vendu à découvert') + ' le ' + when(p.entry_at) + ' à ' + precise(p.price)}),
        ' · maintenant ' + precise(p.last)),
      el('div', {class: 'facts'},
        fact('Résultat latent', usdt(p.pnl, true) + ' (' + pct(p.roi, 1) + ' du capital)', cls(p.pnl)),
        fact('Stop (SL)', precise(p.stop) + ' (' + pct(p.stop / p.price - 1, 2) + ')' + (p.moved ? ' · ' + (long ? 'remonté' : 'descendu')
          + ' ' + p.moved + ' fois, au départ ' + precise(p.stop0) : '') + ((long ? p.stop > p.price : p.stop < p.price)
          ? ' · gain protégé (sauf saut de prix)' : '')),
        fact('Gestion du stop', {suiveur: 'suiveur : il suit le meilleur prix', securise: 'sécurisé : au prix d\'entrée dès +1R'}[p.stop_mode]
          || 'fixe'),
        fact('Objectif (TP)', p.target ? precise(p.target) + ' (' + pct(p.target / p.price - 1, 2) + ')' : 'sortie par sa règle'),
        fact('Liquidation', p.leverage > 1 ? precise(p.liquidation) + ' (' + pct(p.liquidation / p.price - 1, 1) + ')' : 'aucune (sans levier)'),
        fact('Levier', '×' + dec(p.leverage) + ' · ' + usdt(p.notional) + ' en jeu'),
        fact('Depuis', p.bars + (p.bars > 1 ? ' bougies' : ' bougie'))));
  }
  function tradeItem(t) {
    const d = t.diagnosis || {}, long = t.side === 'long';
    return el('article', {class: 'trade'},
      el('div', {class: 'head'}, el('h3', {text: (long ? '▲ Achat ' : '▼ Vente à découvert ') + precise(t.price) + ' → ' + precise(t.exit_price)}),
        el('span', {class: 'result ' + cls(t.pnl), text: pct(t.roi, 1) + ' du capital · ' + (d.title || t.reason)})),
      el('p', {class: 'muted', text: when(t.entry_at || new Date(t.entry_ts).toISOString()) + ' → ' + when(t.exit_at || new Date(t.exit_ts).toISOString())
        + ' · sortie : ' + t.reason + ' · levier ×' + dec(t.leverage) + ' · ' + pct(t.net, 2) + ' sur la position, frais compris'
        + (t.stop0 && Math.abs(t.stop0 - t.stop) > 1e-12 ? ' · stop ' + (long ? 'remonté' : 'descendu') + ' de ' + precise(t.stop0) + ' à '
          + precise(t.stop) : '')}),
      d.text ? el('p', {text: d.text}) : null,
      ...(t.analysis || []).map(x => el('p', {class: 'muted', text: x})),
      d.lesson ? el('p', {class: 'muted'}, el('strong', {text: 'La leçon : '}), d.lesson) : null);
  }
  function renderBot() {
    const box = $('#bot-page');
    if (!botData || botData.error) {
      box.dataset.bot = '';
      box.replaceChildren(el('p', {class: botData ? 'empty-box' : 'muted', text: botData ? botData.error : 'Chargement…'}));
      return;
    }
    const fresh = box.dataset.bot !== botKey || !$('#bot-chart');
    if (fresh) botSkeleton(box);
    const b = botData, bt = b.backtest || {};
    $('#bot-back').setAttribute('href', '#crypto/' + b.coin);
    $('#bot-back').textContent = '← ' + b.coin + ' et ses bots';
    const label = {'3': ['ok', 'test final gagnant'], '2': ['idle', 'test final : trop peu de trades'], '1': ['warn', 'test final perdant'],
      '0': ['warn', 'ne gagne plus au backtest']}[b.label] || ['idle', b.label || '—'];
    $('#bot-head').replaceChildren(
      el('div', {}, el('p', {class: 'eyebrow', text: (TEAMS[b.team] || '') + ' · ' + b.tf_label + ' · argent fictif'}),
        el('h1', {text: b.coin + ' · ' + b.technique})),
      el('div', {class: 'chips'}, statusChip(b), pill(sideText(b.side)), pill('levier ×' + dec(b.leverage)),
        pill(b.exit || exitLabel(b.target_r, b.stop_mode)), chip(label[0], label[1]), liveChip(b.live)));
    $('#bot-rule').textContent = typo(b.rule + ' ' + b.side_hint.charAt(0).toUpperCase() + b.side_hint.slice(1) + '.');
    $('#bot-exit').textContent = typo(b.exit_rule);
    $('#bot-position').replaceChildren(positionBox(b));
    $('#bot-chart-title').textContent = 'Son graphique (' + b.tf_label + ')';
    const ins = b.insights || {wins: [], losses: []}, proba = b.proba;
    $('#bot-agents').replaceChildren(el('h2', {text: 'Les agents d\'analyse'}),
      el('div', {class: 'compare'},
        el('div', {class: 'tile'}, el('p', {class: 'tile-label', text: 'Chances de gain, maintenant'}),
          el('p', {class: 'tile-value', text: proba ? Math.round(100 * proba.p) + ' %' : '—'}),
          el('p', {class: 'tile-sub', text: probaText(proba)})),
        el('div', {class: 'tile'}, el('p', {class: 'tile-label', text: 'Son signal à la dernière bougie'}),
          el('p', {class: 'tile-value', text: b.signal ? (b.signal.entry ? 'entrée' : b.signal.exit ? 'sortie' : 'rien') : '—'}),
          el('p', {class: 'tile-sub', text: 'Il n\'entre que sur ce signal, jamais sur une estimation.'}))),
      el('h3', {class: 'group-title', text: 'Où sa stratégie gagne'}),
      ...(ins.wins.length ? ins.wins.map(x => el('p', {class: 'lesson-line', text: x})) : [el('p', {class: 'muted', text: 'Pas d\'écart net dans son backtest.'})]),
      el('h3', {class: 'group-title', text: 'Où elle perd'}),
      ...(ins.losses.length ? ins.losses.map(x => el('p', {class: 'lesson-line', text: x})) : [el('p', {class: 'muted', text: 'Pas d\'écart net dans son backtest.'})]),
      el('p', {class: 'note', text: 'Mesuré sur les trades de son backtest : des tendances, pas des certitudes (peu de trades par case). '
        + 'Le bot ne change jamais ses réglages. Il garde sa place d\'un test à l\'autre : seuls ses garde-fous (liquidation, moitié du '
        + 'capital perdue, pertes nettes après 20 trades) ou une stratégie recalée l\'arrêtent.'}));
    $('#bot-compare').replaceChildren(el('h2', {text: 'En direct et dans le backtest'}),
      el('div', {class: 'compare'},
        el('div', {class: 'tile'}, el('p', {class: 'tile-label', text: 'En direct, depuis le ' + when(b.started)}),
          el('p', {class: 'tile-value', text: usdt(b.value)}),
          el('p', {class: 'tile-sub'}, el('span', {class: cls(b.pnl), text: pct(b.pnl_pct)}), ' · ' + tradesText(b.count)
            + winText(b.win_rate) + ' · pire baisse ' + pct(b.drawdown, 0))),
        el('div', {class: 'tile'}, el('p', {class: 'tile-label', text: 'Backtest de son dernier test (' + when(b.tested) + ')'}),
          el('p', {class: 'tile-value', text: pct(bt.mean, 2) + ' par trade'}),
          el('p', {class: 'tile-sub', text: (bt.trades || 0) + ' trades, frais compris, sans levier · avec levier ' + bigPct(bt.total_return)
            + ' · pire baisse ' + pct(bt.drawdown || 0, 0)}),
          el('p', {class: 'tile-sub', text: 'Étude ' + pct(bt.study_mean, 2) + ' · validation ' + pct(bt.valid_mean, 2) + ' · test final '
            + (bt.test_n ? pct(bt.test_mean, 2) : '—')}),
          el('p', {class: 'tile-sub', text: b.label_text || ''}))));
    const done = (b.trades || []).slice().reverse();  // du plus ancien au plus récent
    if (fresh || box.dataset.trades !== String(b.count)) {
      box.dataset.trades = String(b.count);
      $('#bot-curve').replaceChildren(...(done.length >= 2 ? [el('h2', {text: 'Son capital, trade après trade'}), lineChart({width: box.clientWidth || 700,
        xs: done.map(t => t.exit_ts), ys: done.map(t => t.equity), refs: [{y: b.start, label: 'Départ : ' + usdt(b.start), short: 'Départ'}],
        label: 'Capital du bot en direct', xTicks: spreadTicks(done.map(t => t.exit_ts), 4), xTicksSmall: spreadTicks(done.map(t => t.exit_ts), 3),
        xTick: dayLabel, yTick: v => Math.round(v).toLocaleString('fr-FR'), endLabel: usdt(done[done.length - 1].equity),
        endShort: Math.round(done[done.length - 1].equity).toLocaleString('fr-FR'),
        tip: i => [when(new Date(done[i].exit_ts).toISOString()), usdt(done[i].equity)]})] : []));
      $('#bot-trades').replaceChildren(el('h2', {text: 'Ses trades, expliqués'}), ...((b.trades || []).length ? b.trades.slice(0, 40).map(tradeItem)
        : [el('p', {class: 'muted', text: 'Pas encore de trade terminé.'})]));
    }
    const card = b.technique_card;
    if (fresh) $('#bot-card').replaceChildren(...(card ? [el('h2', {text: card.title}), el('p', {}, el('strong', {text: 'Ce que ça mesure. '}), card.measures),
      el('p', {}, el('strong', {text: 'Comment le lire. '}), card.reading), el('p', {}, el('strong', {text: 'Ce que dit la recherche. '}), card.research)] : []));
    if (fresh) drawBotChart();
  }
  function drawBotChart() {
    const host = $('#bot-chart');
    if (!host) return;
    if (!botChart || botChart.error) {
      host._chart = null;
      host.replaceChildren(el('p', {class: 'muted', text: botChart ? botChart.error + ' Nouvel essai dans quelques secondes…' : 'Chargement du graphique…'}));
      $('#bot-legend').replaceChildren();
      return;
    }
    const d = botChart, marks = [], markers = [], pos = d.position;
    if (pos) {
      marks.push({price: pos.price, color: 'var(--text-secondary)', label: (pos.side === 'long' ? 'Achat ' : 'Vente ') + precise(pos.price)});
      marks.push({price: pos.stop, color: 'var(--critical)', label: 'Stop ' + precise(pos.stop)});
      if (pos.target) marks.push({price: pos.target, color: 'var(--good)', label: 'Objectif ' + precise(pos.target)});
      if (pos.leverage > 1) marks.push({price: pos.liquidation, color: 'var(--critical)', label: 'Liquidation ' + precise(pos.liquidation), dash: '5 4', optional: true});
      if (pos.moved) marks.push({price: pos.stop0, color: 'var(--text-secondary)', label: 'Stop de départ ' + precise(pos.stop0), dash: '2 4', optional: true});
      markers.push({ts: pos.entry_ts, up: pos.side === 'long', fill: 'var(--text-primary)', stroke: 'var(--surface-1)'});
    }
    for (const t of d.rule_trades) {
      markers.push({ts: t.entry, up: t.side === 'long', fill: 'none', stroke: 'var(--text-secondary)'});
      markers.push({ts: t.exit, up: t.side !== 'long', fill: 'none', stroke: t.net > 0 ? 'var(--up)' : 'var(--down)'});
    }
    for (const t of d.trades) {
      markers.push({ts: t.entry, up: t.side === 'long', fill: 'var(--text-primary)', stroke: 'var(--surface-1)'});
      markers.push({ts: t.exit, up: t.side !== 'long', fill: t.net > 0 ? 'var(--up)' : 'var(--down)', stroke: 'var(--surface-1)'});
    }
    zoomChart(host, {key: 'bot-' + botKey, candles: d.candles, lines: d.lines, zones: d.levels, marks: marks, markers: markers,
      label: 'Graphique de ' + coin(d.symbol) + ' et de son bot'});
    $('#bot-legend').replaceChildren(...chartLegend(d, !!pos, true));
  }
  function chartLegend(d, pos, rule) {
    const item = (klass, color, text, dash) => el('span', {}, el('span', {class: 'swatch ' + klass + (dash ? ' dashed' : ''),
      style: dash ? 'border-color:' + color : 'background:' + color}), text);
    const out = [item('', 'var(--up)', 'hausse'), item('', 'var(--down)', 'baisse'), el('span', {text: 'barres du bas : le volume'})];
    const bands = new Set();
    for (const ln of d.lines || []) {
      if (ln.dash && /-(up|low)$|^span-|^psar$|^out$/.test(ln.key)) {
        const name = /^span-/.test(ln.key) ? 'le nuage (pointillés)' : /^(psar|out)$/.test(ln.key) ? ln.label + ' (pointillés)' : 'les bandes (pointillés)';
        if (!bands.has(name)) { bands.add(name); out.push(item('line', ln.color, name, true)); }
      } else out.push(item('line', ln.color, ln.label));
    }
    if ((d.levels || []).some(z => z.kind === 'support')) out.push(item('', 'var(--series-3)', 'zone de support'));
    if ((d.levels || []).some(z => z.kind === 'resistance')) out.push(item('', 'var(--series-2)', 'zone de résistance'));
    if ((d.trades || []).length || pos) out.push(el('span', {text: '▲▼ pleins : les vrais trades (vert gagné, rouge perdu)'}));
    if (rule && (d.rule_trades || []).length) out.push(el('span', {text: '△▽ vides : ce que sa règle aurait fait sur ces bougies'}));
    if (pos) out.push(item('line', 'var(--critical)', 'stop (SL)'), item('line', 'var(--good)', 'objectif (TP)'));
    return out;
  }

  // --- le graphique zoomable : molette, glisser, pincer, boutons, clavier ---
  const zooms = {};
  function shortLabel(text) {  // sur téléphone, les étiquettes de prix tiennent dans la marge
    return text.replace(/^Résistance /, 'Rés. ').replace(/^Support /, 'Sup. ').replace(/^Stop /, 'SL ')
      .replace(/^Objectif /, 'TP ').replace(/^(Achat|Vente) /, 'Prix ').replace(/^Liquidation /, 'Liq. ').replace(/ \(.*\)$/, '');
  }
  function zoomChart(box, o) {
    if (box._chart && box._chart.key === o.key) { box._chart.update(o); return; }
    let c = o.candles || [], n = c.length;
    if (!n) { box._chart = null; box.replaceChildren(el('p', {class: 'muted', text: 'Pas de bougies pour l\'instant.'})); return; }
    const start = (box.clientWidth || 860) < 560 ? 60 : 140;  // sur téléphone, moins de bougies au départ
    const z = zooms[o.key] || (zooms[o.key] = {span: Math.min(n, start), end: n - 1, endTs: null, follow: true});
    const ts = () => c.map(k => k[0]);
    let times = ts();
    function at(t) {  // la bougie qui contient l'instant t (ou -1)
      if (t === null || t === undefined || !n || t < times[0]) return -1;
      let lo = 0, hi = n - 1;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (times[mid] <= t) lo = mid; else hi = mid - 1; }
      return lo;
    }
    function clamp() {
      z.span = Math.max(Math.min(15, n), Math.min(n, Math.round(z.span)));
      z.end = Math.max(z.span - 1, Math.min(n - 1, Math.round(z.end)));
      z.follow = z.end >= n - 1;
      z.endTs = times[z.end];
    }
    if (z.follow) z.end = n - 1; else if (z.endTs !== null) z.end = Math.max(0, at(z.endTs));
    const info = el('span', {class: 'muted zinfo'});
    const tools = el('div', {class: 'ztools'},
      el('button', {class: 'btn btn-small', type: 'button', text: '−', 'aria-label': 'Dézoomer : voir plus de bougies', onclick: () => zoomBy(1.5)}),
      el('button', {class: 'btn btn-small', type: 'button', text: '+', 'aria-label': 'Zoomer', onclick: () => zoomBy(1 / 1.5)}),
      el('button', {class: 'btn btn-small', type: 'button', text: '◀', 'aria-label': 'Plus ancien', onclick: () => panBy(-Math.max(1, Math.round(z.span / 3)))}),
      el('button', {class: 'btn btn-small', type: 'button', text: '▶', 'aria-label': 'Plus récent', onclick: () => panBy(Math.max(1, Math.round(z.span / 3)))}),
      el('button', {class: 'btn btn-small', type: 'button', text: 'Maintenant', onclick: () => { z.end = n - 1; clamp(); draw(); }}),
      info);
    const holder = el('div', {class: 'mini-chart zchart'}), tip = el('div', {class: 'tip', hidden: true});
    box.classList.add('zhost');
    box.replaceChildren(tools, holder);
    function zoomBy(f, anchor) {
      const old = z.span;
      z.span = old * f;
      clamp();
      if (anchor !== undefined) z.end = anchor + (z.end - anchor) * z.span / old;
      clamp(); draw();
    }
    function panBy(k) { z.end += k; clamp(); draw(); }
    clamp();
    let geo = null;
    function draw() {
      const W = Math.max(300, Math.round(holder.clientWidth || box.clientWidth || 860)), small = W < 560;
      const H = small ? 360 : 460, VH = small ? 46 : 64, MT = 12, MB = 26, MR = small ? 120 : 196;
      const a = z.end - z.span + 1, b = z.end, m = b - a + 1;
      const vis = c.slice(a, b + 1);
      let lo = Math.min(...vis.map(k => k[3])), hi = Math.max(...vis.map(k => k[2]));
      const span0 = hi - lo || hi * 0.01 || 1;
      const near = v => v !== null && v !== undefined && isFinite(v) && v >= lo - 0.6 * span0 && v <= hi + 0.6 * span0;
      const zones = (o.zones || []).filter(zn => zn.high >= lo - 0.25 * span0 && zn.low <= hi + 0.25 * span0);
      const marks = (o.marks || []).filter(mk => isFinite(mk.price) && (!mk.optional || near(mk.price)));
      for (const zn of zones) { lo = Math.min(lo, zn.low); hi = Math.max(hi, zn.high); }
      for (const mk of marks) { lo = Math.min(lo, mk.price); hi = Math.max(hi, mk.price); }
      for (const ln of o.lines || []) for (let i = a; i <= b; i++) { const v = ln.values[i]; if (near(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
      const pad = (hi - lo) * 0.05 || Math.abs(hi) * 0.01 || 1;
      lo -= pad; hi += pad;
      const ticks = niceTicks(lo, hi, small ? 5 : 7), step = ticks.length > 1 ? ticks[1] - ticks[0] : 1;
      const tickText = ticks.map(t => tickPrice(t, step));
      const ML = Math.max(small ? 40 : 50, 14 + 6.8 * Math.max(...tickText.map(x => x.length)));
      const PB = H - MB - VH - 10;  // bas de la zone des prix ; le volume dessous
      const slot = (W - ML - MR) / m, body = Math.max(1, Math.min(12, slot * 0.66));
      const X = i => ML + slot * (i - a + 0.5), Y = v => MT + (hi - v) / (hi - lo) * (PB - MT);
      const maxVol = Math.max(...vis.map(k => k[5] || 0)) || 1;
      const VY = v => H - MB - (v / maxVol) * VH;
      const root = svg('svg', {viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': o.label, tabindex: '0', class: 'zsvg'});
      ticks.forEach((t, k) => {
        if (Y(t) < MT - 1 || Y(t) > PB + 1) return;
        root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(t), y2: Y(t), class: 'grid'}));
        root.append(svg('text', {x: ML - 6, y: Y(t) + 4, 'text-anchor': 'end', class: 'tick'}, tickText[k]));
      });
      root.append(svg('line', {x1: ML, x2: W - MR, y1: PB + 5, y2: PB + 5, class: 'grid'}));
      const labels = [];
      for (const zn of zones) {
        const color = zn.kind === 'support' ? 'var(--series-3)' : 'var(--series-2)', top = Y(Math.min(hi, zn.high)), bottom = Y(Math.max(lo, zn.low));
        root.append(svg('rect', {x: ML, width: W - MR - ML, y: top, height: Math.max(2, bottom - top), fill: color, opacity: 0.14}));
        labels.push({y: Y(zn.price), color: color, text: (zn.kind === 'support' ? 'Support ' : 'Résistance ') + precise(zn.price)});
      }
      for (const ln of o.lines || []) {
        let pts = [];
        const flush = () => { if (pts.length > 1) root.append(svg('polyline', {points: pts.join(' '), class: 'line', stroke: ln.color,
          'stroke-dasharray': ln.dash ? '5 4' : null, opacity: ln.dash ? 0.8 : null})); pts = []; };
        for (let i = a; i <= b; i++) { const v = ln.values[i]; if (!near(v)) flush(); else pts.push(X(i).toFixed(1) + ',' + Y(v).toFixed(1)); }
        flush();
      }
      for (let i = a; i <= b; i++) {
        const k = c[i], color = k[4] >= k[1] ? 'var(--up)' : 'var(--down)';
        root.append(svg('line', {x1: X(i), x2: X(i), y1: Y(k[2]), y2: Y(k[3]), stroke: color, 'stroke-width': 1}));
        const top = Y(Math.max(k[1], k[4])), bottom = Y(Math.min(k[1], k[4]));
        root.append(svg('rect', {x: X(i) - body / 2, width: body, y: top, height: Math.max(1, bottom - top), fill: color}));
        const vy = VY(k[5] || 0);
        root.append(svg('rect', {x: X(i) - body / 2, width: body, y: vy, height: Math.max(0, H - MB - vy), fill: color, opacity: 0.35}));
      }
      for (const mk of marks) {
        root.append(svg('line', {x1: ML, x2: W - MR, y1: Y(mk.price), y2: Y(mk.price), stroke: mk.color, 'stroke-width': 1.5,
          'stroke-dasharray': mk.dash || null}));
        if (mk.label) labels.push({y: Y(mk.price), color: mk.color, text: mk.label});
      }
      for (const mk of o.markers || []) {
        const i = at(mk.ts);
        if (i < a || i > b) continue;
        const size = small ? 5.5 : 6.5, y = mk.up ? Y(c[i][3]) + 14 : Y(c[i][2]) - 14, dir = mk.up ? 1 : -1;
        root.append(svg('path', {d: 'M' + X(i) + ',' + (y - size * dir) + 'L' + (X(i) + size) + ',' + (y + 0.8 * size * dir) + 'L' + (X(i) - size) + ',' +
          (y + 0.8 * size * dir) + 'Z', fill: mk.fill, stroke: mk.stroke, 'stroke-width': mk.fill === 'none' ? 1.6 : 1.5}));
      }
      labels.sort((p, q) => p.y - q.y);
      let lastY = -Infinity;
      for (const l of labels) {  // les étiquettes ne se recouvrent jamais
        const y = Math.max(l.y, lastY + 15);
        if (y > PB + 8) break;
        lastY = y;
        root.append(svg('rect', {x: W - MR + 6, y: y - 5, width: 10, height: 10, rx: 2, fill: l.color}));
        root.append(svg('text', {x: W - MR + 20, y: y + 4, class: 'tick'}, small ? shortLabel(l.text) : l.text));
      }
      const gap = n > 1 ? times[1] - times[0] : 86400000, intraday = gap < 86400000, minutes = gap < 3600000;
      const fmt = ms => { const d = new Date(ms), hh = String(d.getHours()).padStart(2, '0') + 'h', mm = String(d.getMinutes()).padStart(2, '0');
        if (!intraday) return dayLabel(ms); if (small) return minutes ? hh + mm : dayLabel(ms) + ' ' + hh; return dayLabel(ms) + ' ' + hh + (minutes ? mm : ''); };
      const nx = small ? (intraday && !minutes ? 2 : 3) : 5;  // « 05/11 16h » est long : deux dates sur téléphone
      for (let k = 0; k < nx; k++) {
        const i = a + Math.round((m - 1) * (k + 0.5) / nx);
        root.append(svg('text', {x: X(i), y: H - 8, 'text-anchor': 'middle', class: 'tick'}, fmt(times[i])));
      }
      const vline = svg('line', {y1: MT, y2: H - MB, class: 'crosshair'}), hline = svg('line', {x1: ML, x2: W - MR, class: 'crosshair'});
      const ptag = svg('text', {x: W - MR - 4, 'text-anchor': 'end', class: 'end-label', visibility: 'hidden'});
      root.append(vline, hline, ptag);
      holder.replaceChildren(root, tip);
      info.textContent = m + ' bougies sur ' + n + ' · ' + (small ? 'boutons ou glisser' : 'molette pour zoomer, glisser pour se déplacer');
      geo = {W, H, ML, MR, MT, PB, a, b, slot, lo, hi, root, vline, hline, ptag};
    }
    function index(e) {
      const r = geo.root.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * geo.W;
      return {i: Math.max(geo.a, Math.min(geo.b, Math.round(geo.a + (x - geo.ML) / geo.slot - 0.5))), y: (e.clientY - r.top) / r.height * geo.H, r};
    }
    function hover(e) {
      const {i, y, r} = index(e), k = c[i], x = geo.ML + geo.slot * (i - geo.a + 0.5);
      geo.vline.setAttribute('x1', x); geo.vline.setAttribute('x2', x); geo.vline.style.visibility = 'visible';
      if (y >= geo.MT && y <= geo.PB) {
        const v = geo.hi - (y - geo.MT) / (geo.PB - geo.MT) * (geo.hi - geo.lo);
        geo.hline.setAttribute('y1', y); geo.hline.setAttribute('y2', y); geo.hline.style.visibility = 'visible';
        geo.ptag.setAttribute('y', y - 4); geo.ptag.textContent = precise(v); geo.ptag.setAttribute('visibility', 'visible');
      } else { geo.hline.style.visibility = 'hidden'; geo.ptag.setAttribute('visibility', 'hidden'); }
      const rows = [el('div', {class: 'tip-date', text: new Date(k[0]).toLocaleString('fr-FR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'})}),
        el('div', {class: 'tip-row', text: 'Ouverture ' + precise(k[1]) + ' · clôture ' + precise(k[4])}),
        el('div', {class: 'tip-row', text: 'Plus haut ' + precise(k[2]) + ' · plus bas ' + precise(k[3])}),
        el('div', {class: 'tip-row', text: 'Sur la bougie : ' + pct(k[4] / k[1] - 1) + ' · volume ' + Math.round(k[5] || 0).toLocaleString('fr-FR')})];
      for (const ln of o.lines || []) if (ln.values[i] !== null && ln.values[i] !== undefined)
        rows.push(el('div', {class: 'tip-row', text: ln.label + ' : ' + precise(ln.values[i])}));
      tip.replaceChildren(...rows);
      tip.hidden = false;
      const host = holder.getBoundingClientRect(), left = r.left - host.left + x / geo.W * r.width;
      tip.style.left = (left + tip.offsetWidth + 16 > host.width ? Math.max(4, left - tip.offsetWidth - 12) : left + 12) + 'px';
      tip.style.top = '8px';
    }
    function hide() {
      if (!geo) return;
      geo.vline.style.visibility = 'hidden'; geo.hline.style.visibility = 'hidden';
      geo.ptag.setAttribute('visibility', 'hidden'); tip.hidden = true;
    }
    const pointers = new Map();
    let drag = null, pinch = null, frame = 0;
    function later() { if (!frame) frame = requestAnimationFrame(() => { frame = 0; draw(); }); }
    holder.addEventListener('wheel', e => {
      if (!geo) return;
      e.preventDefault();
      zoomBy(e.deltaY > 0 ? 1.2 : 1 / 1.2, index(e).i);
    }, {passive: false});
    holder.addEventListener('pointerdown', e => {
      pointers.set(e.pointerId, e.clientX);
      if (pointers.size === 1) drag = {x: e.clientX, end: z.end, moved: false};
      if (pointers.size === 2) { const xs = [...pointers.values()]; pinch = {d: Math.abs(xs[0] - xs[1]) || 1, span: z.span}; drag = null; }
    });
    holder.addEventListener('pointermove', e => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, e.clientX);
      if (pinch && pointers.size === 2) {
        const xs = [...pointers.values()], d = Math.abs(xs[0] - xs[1]) || 1;
        z.span = pinch.span * pinch.d / d; clamp(); later(); return;
      }
      if (drag && geo) {
        const r = geo.root.getBoundingClientRect(), dx = (e.clientX - drag.x) / r.width * geo.W;
        if (!drag.moved && Math.abs(dx) > 4) {
          drag.moved = true;
          try { holder.setPointerCapture(e.pointerId); } catch (err) { /* déjà relâché */ }
        }
        if (drag.moved) { z.end = drag.end - dx / geo.slot; clamp(); later(); hide(); return; }
      }
      if (geo && e.pointerType !== 'touch') hover(e);
    });
    const end = e => { pointers.delete(e.pointerId); if (pointers.size < 2) pinch = null; if (!pointers.size) drag = null; };
    holder.addEventListener('pointerup', end);
    holder.addEventListener('pointercancel', end);
    holder.addEventListener('pointerleave', e => { if (e.pointerType !== 'touch') { end(e); hide(); } });
    holder.addEventListener('dblclick', () => { z.span = Math.min(n, start); z.end = n - 1; clamp(); draw(); });
    holder.addEventListener('keydown', e => {
      const keys = {'+': () => zoomBy(1 / 1.5), '=': () => zoomBy(1 / 1.5), '-': () => zoomBy(1.5),
        ArrowLeft: () => panBy(-Math.max(1, Math.round(z.span / 10))), ArrowRight: () => panBy(Math.max(1, Math.round(z.span / 10)))};
      if (keys[e.key]) { keys[e.key](); e.preventDefault(); }
    });
    box._chart = {key: o.key, redraw: draw, update: next => {
      o = next; c = o.candles || []; n = c.length; times = ts();
      if (!n) { box._chart = null; box.replaceChildren(el('p', {class: 'muted', text: 'Pas de bougies pour l\'instant.'})); return; }
      if (z.follow) z.end = n - 1; else z.end = Math.max(0, at(z.endTs));
      clamp(); draw();
    }};
    draw();
  }
  function lessonChart(b) {
    const box = el('div', {}, el('p', {class: 'muted', text: 'Chargement du graphique…'}));
    getJSON('/api/crypto-graphique?c=' + encodeURIComponent(coin(b.symbol)) + '&unite=' + b.timeframe).then(d => {
      const holder = el('div', {});
      box.replaceChildren(holder, el('div', {class: 'legend'}, ...chartLegend(d, false, false)), el('p', {class: 'small-print', text: b.caption || ''}));
      zoomChart(holder, {key: 'lecon-' + b.symbol + b.timeframe, candles: d.candles, lines: [], zones: d.levels, marks: [], markers: [],
        label: b.caption || coin(d.symbol)});
    }).catch(() => box.replaceChildren(el('p', {class: 'empty-box', text: 'Graphique indisponible pour l\'instant (la plateforme ne répond '
      + 'pas). Il apparaîtra ici dès que les prix arrivent.'})));
    return box;
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
    securise: 'Le stop avait été remonté au prix d\'entrée : le trade sort presque à zéro au lieu de perdre.',
  };
  function diagnosesBox() {
    const box = el('div', {class: 'sim'});
    box.append(el('p', {class: 'question', text: 'Les diagnostics que tes bots écrivent après chaque vente :'}),
      el('ul', {}, ...Object.entries(KIND_HELP).map(([k, help]) => el('li', {}, el('strong', {text: (schoolData.kinds[k] || k) + ' : '}), help))));
    if (schoolData.examples.length) {
      box.append(el('p', {class: 'question', text: 'Des exemples tirés des trades de tes bots :'}));
      for (const e of schoolData.examples) box.append(el('p', {}, el('strong', {text: coin(e.symbol) + ' · ' + e.play + ' · ' + signed(100 * e.net) + ' — ' + e.diagnosis.title + '. '}),
        e.diagnosis.text + (e.replay ? ' (rejeu)' : '')));
    } else {
      box.append(el('p', {class: 'muted', text: 'Pas encore de trade de tes bots : leurs premiers exemples apparaîtront ici.'}));
    }
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

  let resizeTimer = null, lastWidth = window.innerWidth;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (window.innerWidth === lastWidth) return;  // sur téléphone, la barre d'adresse qui se cache ne compte pas
      lastWidth = window.innerWidth;
      document.querySelectorAll('.zhost').forEach(box => { if (box._chart) box._chart.redraw(); });
      if (view === 'bot') { $('#bot-page').dataset.trades = ''; renderBot(); }
    }, 250);
  });

  // --- rythme : chaque source seulement quand sa page est affichée ---
  const last = {state: 0, journal: 0, prices: 0, news: 0, swarm: 0, coin: 0, coinChart: 0, bot: 0, botChart: 0};
  const busy = {};
  async function every(name, ms, fn) {
    const now = Date.now();
    if (busy[name] || now - last[name] < ms) return;
    busy[name] = true; last[name] = now;
    try { await fn(); } catch (e) { if (name === 'prices') $('#prices-status').textContent = e.message; }
    finally { busy[name] = false; }
  }
  function tick() {
    if (document.hidden) return;
    every('state', 4000, refreshState);
    if (view === 'journal') every('journal', 1500, refreshJournal);
    if (view === 'prix') every('prices', pricesReady ? 10000 : 2000, refreshPrices);
    if (view === 'actualite') every('news', newsReady ? 60000 : 2000, refreshNews);
    if (view === 'direct' || view === 'cryptos' || view === 'strategies') every('swarm', 5000, refreshSwarm);
    if (view === 'crypto') {
      every('coin', 5000, refreshCoin);
      if (coinTf) every('coinChart', chartEvery(coinTf), refreshCoinChart);
    }
    if (view === 'bot') {
      every('bot', 5000, refreshBot);
      if (botData && !botData.error) every('botChart', chartEvery(botData.timeframe), refreshBotChart);
    }
  }
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


def code_page() -> str:
    return simple_page("Code du bot", (
        '<div class="hero"><p class="eyebrow">Accès depuis un autre appareil</p><h1>Entre le code du bot</h1>'
        "<p>Il est affiché dans la fenêtre noire du bot, sur l'ordinateur. L'appareil s'en souviendra.</p>"
        '<form class="row" method="get" action="/"><div class="field"><input name="code" inputmode="numeric" '
        'autocomplete="one-time-code" aria-label="Code à 6 chiffres" maxlength="6" required></div>'
        '<button class="btn btn-primary" type="submit">Entrer</button></form></div>'))
