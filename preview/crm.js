/* CRM MERCI, preview : rendu des vues à partir de donnees.js. Vue choisie par ?v= */
(function () {
  const D = window.CRM;
  const q = new URLSearchParams(location.search);
  const vue = q.get('v') || 'accueil';
  const $ = (s, el = document) => el.querySelector(s);

  /* ---------- Icônes (trait 1.7, currentColor) ---------- */
  const P = {
    accueil: '<path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z"/>',
    pipelines: '<rect x="4" y="4.5" width="4.5" height="15" rx="2"/><rect x="10" y="4.5" width="4.5" height="10" rx="2"/><rect x="16" y="4.5" width="4" height="6.5" rx="2"/>',
    contacts: '<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19c.6-3.2 2.9-5 5.5-5s4.9 1.8 5.5 5"/><circle cx="17" cy="9.5" r="2.4"/><path d="M16 14.2c2.3.1 4 1.6 4.5 4.3"/>',
    sequences: '<path d="M5 6h9M5 12h14M5 18h7"/><circle cx="18" cy="6" r="1.6"/><circle cx="15" cy="18" r="1.6"/>',
    prospection: '<circle cx="11" cy="11" r="6.2"/><path d="m16 16 4 4"/>',
    reglages: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M5.6 18.4l1.6-1.6M16.8 7.2l1.6-1.6"/>',
    email: '<rect x="3.5" y="5.5" width="17" height="13" rx="3"/><path d="m4.5 7.5 7.5 5.5 7.5-5.5"/>',
    linkedin: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M8 10.5V16M8 7.8v.1M11.5 16v-5.5M11.5 13c0-1.6 1-2.6 2.4-2.6s2.1 1 2.1 2.6V16"/>',
    systeme: '<path d="M12 4v3M12 17v3M4 12h3M17 12h3"/><circle cx="12" cy="12" r="4"/>',
    retour: '<path d="M14.5 6 8.5 12l6 6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    pause: '<rect x="6.5" y="5" width="3.6" height="14" rx="1.4"/><rect x="13.9" y="5" width="3.6" height="14" rx="1.4"/>',
    lecture: '<path d="M8 5.5v13l10.5-6.5z"/>',
    calendrier: '<rect x="4" y="5.5" width="16" height="14" rx="3"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    telephone: '<path d="M6.5 4h3l1.5 4-2 1.3a10 10 0 0 0 5.7 5.7l1.3-2 4 1.5v3a2 2 0 0 1-2 2A15 15 0 0 1 4.5 6a2 2 0 0 1 2-2z"/>',
    fleche: '<path d="M7 17 17 7M9 7h8v8"/>',
    import: '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
    export: '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M5 19.5h14"/>',
    attention: '<path d="M12 4.5 21 19.5H3z"/><path d="M12 10v4M12 16.8v.1"/>',
    coche: '<path d="m6 12.5 4 4 8-9"/>'
  };
  const ic = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n]}</svg>`;

  /* ---------- Aides ---------- */
  const nomComplet = (c) => (c.prenom || c.nom) ? `${c.prenom} ${c.nom}`.trim() : c.org;
  const initiales = (c) => (c.prenom ? (c.prenom[0] + (c.nom[0] || '')) : (c.org || '?').slice(0, 2)).toUpperCase();
  const classeInit = (c) => c.type === 'entreprise' ? ' c-initiales--e' : c.type === 'association' ? ' c-initiales--a' : '';
  const classeNote = (n) => n >= 9 ? 'haut' : n >= 7 ? 'bien' : n >= 6 ? 'moyen' : 'bas';
  const note = (n) => n == null ? '' : `<span class="c-note c-note--${classeNote(n)}">${n}/10</span>`;
  const etatSeq = (s) => {
    if (!s) return '<span class="c-etat">Pas de séquence</span>';
    const mots = { due: `Part ${s.quand}`, active: `Pas ${s.pas}/${s.total}, ${s.quand}`, pause: 'En pause', echec: `Échec : ${s.quand}`, arret: `Arrêtée : ${s.quand}`, fini: 'Terminée' };
    const cl = s.etat === 'fini' ? 'arret' : s.etat;
    return `<span class="c-etat c-etat--${cl}">${mots[s.etat]}</span>`;
  };
  const sousTitre = (c) => c.type === 'donateur' ? `Donateur, ${c.ville}` : c.type === 'association' ? `${c.org}` : [c.poste, c.org].filter(Boolean).join(', ');
  const lienFiche = (c) => `?v=fiche&id=${c.id}`;

  /* ---------- Parcours : chaque étape de pipeline rattachée à une étape du parcours ---------- */
  const RATTACHE = {
    donateurs: { 'Inscrit': 'capturer', 'Bienvenue envoyée': 'suivre', 'Pilote ouvert': 'relancer', 'Compte créé': 'convertir', 'Premier don': 'convertir', 'Fidèle': 'fideliser' },
    entreprises: { 'Prospect': 'capturer', 'A répondu': 'suivre', 'Contacté': 'relancer', 'Démo planifiée': 'convertir', 'Démo faite': 'convertir', 'Abonnement signé': 'convertir', 'Salariés activés': 'fideliser' }
  };
  const ETAPES = [
    { cle: 'attirer', nom: 'Attirer', info: 'D\'où ils viennent' },
    { cle: 'capturer', nom: 'Capturer', info: 'Inscrits, prospects' },
    { cle: 'suivre', nom: 'Suivre', info: 'Qualifier' },
    { cle: 'relancer', nom: 'Relancer', info: 'Séquences en cours' },
    { cle: 'convertir', nom: 'Convertir', info: 'Compte, démo, signature' },
    { cle: 'fideliser', nom: 'Fidéliser', info: 'Dons, salariés actifs' }
  ];
  function compteParcours(pipe) {
    const r = {}; ETAPES.forEach(e => r[e.cle] = { n: 0, detail: {} });
    D.contacts.filter(c => c.pipeline === pipe).forEach(c => {
      const k = RATTACHE[pipe][c.etape]; if (!k) return;
      r[k].n++; r[k].detail[c.etape] = (r[k].detail[c.etape] || 0) + 1;
      r.attirer.n++; const src = pipe === 'entreprises' ? c.source : c.detail; r.attirer.detail[src] = (r.attirer.detail[src] || 0) + 1;
    });
    return r;
  }
  const resume = (detail, attirer) => {
    const e = Object.entries(detail).sort((a, b) => b[1] - a[1]);
    if (!e.length) return 'Personne';
    if (attirer) return e.slice(0, 2).map(([k, v]) => `${k} ${v}`).join(', ');
    return e.map(([k, v]) => e.length > 1 ? `${k} ${v}` : k).join(', ');
  };

  /* ---------- Coque : menu à gauche, zone principale ---------- */
  const TITRES = { accueil: 'Accueil', pipelines: 'Pipelines', contacts: 'Contacts', fiche: 'Contacts', sequences: 'Séquences', prospection: 'Prospection', reglages: 'Réglages' };
  function coque(contenu) {
    const actif = vue === 'fiche' ? 'contacts' : vue;
    const nbSeq = D.contacts.filter(c => c.seq && ['due', 'active'].includes(c.seq.etat)).length;
    const lien = (k, l, nb) => `<a href="?v=${k}"${k === actif ? ' aria-current="page"' : ''}>${ic(k)}<span>${l}</span>${nb ? `<span class="c-nb">${nb}</span>` : ''}</a>`;
    let titre = `${ic(actif)}${TITRES[vue] || 'Accueil'}`;
    if (vue === 'fiche') { const c = D.contacts.find(x => x.id === +(q.get('id') || 20)) || D.contacts[0]; titre = `${ic('contacts')}<a href="?v=contacts">Contacts</a><i>/</i>${nomComplet(c)}`; }
    if (vue !== 'accueil' && vue !== 'fiche') contenu = contenu.replace(/<h1 class="c-titre">[^<]*<\/h1>/, '');
    contenu = contenu.replace(/<h1 class="c-titre">([\s\S]*?)<\/h1>/g, '<h2 class="c-titre">$1</h2>');
    return `
<a class="c-cache" href="#contenu">Aller au contenu</a>
<div class="c-app">
  <aside class="c-side">
    <a href="?v=accueil" aria-label="MERCI, accueil du CRM"><img class="c-side__logo" src="assets/logo-noir.png" alt="MERCI" width="80" height="22"></a>
    <nav class="c-nav" aria-label="Menu">
      ${lien('accueil', 'Accueil')}
      ${lien('pipelines', 'Pipelines')}
      ${lien('contacts', 'Contacts', D.contacts.length)}
      <div class="c-nav__sec">Automatisation</div>
      ${lien('sequences', 'Séquences', nbSeq)}
      ${lien('prospection', 'Prospection')}
      <div class="c-nav__sec">Compte</div>
      ${lien('reglages', 'Réglages')}
    </nav>
    <div class="c-side__relances">
      <label class="c-switch"><span id="pause-txt">Relances actives</span><input type="checkbox" id="pause-gen" checked aria-label="Relances automatiques"></label>
      <p>Lundi au vendredi, 9 h à 18 h.</p>
    </div>
    <div class="c-moi"><span class="c-moi__av">V</span><div><b>Valentin</b><span>valentin@merci-exemple.fr</span></div><a href="?v=reglages" aria-label="Réglages">${ic('reglages')}</a></div>
  </aside>
  <div class="c-main">
    <header class="c-top"><h1>${titre}</h1><span class="c-top__date">${D.aujourdhui[0].toUpperCase() + D.aujourdhui.slice(1)}</span><p class="c-exemple">Données d'exemple <a href="?v=connexion">Connexion</a></p></header>
    <main class="c-corps" id="contenu">
      <div class="c-bandeau" role="status">${ic('pause')}<span>Toutes les relances sont en pause. Rien ne part tant que vous ne les relancez pas.</span><button class="c-btn c-btn--s" type="button" id="reprendre">${ic('lecture')}Reprendre</button></div>
      ${contenu}
    </main>
  </div>
</div>`;
  }

  /* ---------- Accueil ---------- */
  function vAccueil() {
    const pd = compteParcours('donateurs'), pe = compteParcours('entreprises');
    const ligne = (titre, p, pipe) => `<div class="c-parcours__public">${titre}</div>` + ETAPES.map(e => {
      const v = p[e.cle]; const vide = v.n === 0 ? ' c-parcours__case--vide' : '';
      return `<a class="c-parcours__case${vide}" href="?v=pipelines&p=${pipe}"><strong>${v.n}</strong><small>${resume(v.detail, e.cle === 'attirer')}</small></a>`;
    }).join('');
    const afaire = D.contacts.filter(c => c.afaire);
    const reponses = D.contacts.filter(c => c.seq && c.seq.etat === 'arret');
    const echecs = D.contacts.filter(c => c.seq && c.seq.etat === 'echec');
    const items = [
      ...reponses.map(c => ({ ic: 'linkedin', cl: 'vert', quoi: `${c.prenom} a répondu sur LinkedIn`, qui: `${c.poste}, ${c.org}. ${c.afaire}.`, c, bouton: 'Lire la réponse' })),
      ...afaire.filter(c => !reponses.includes(c)).map(c => ({ ic: c.etape === 'Démo planifiée' ? 'calendrier' : c.type === 'association' ? 'telephone' : 'coche', cl: '', quoi: c.afaire, qui: `${nomComplet(c)}, ${c.org}`, c, bouton: 'Ouvrir' })),
      ...echecs.map(c => ({ ic: 'attention', cl: 'poudre', quoi: `E-mail en rebond pour ${c.prenom} ${c.nom}`, qui: `${c.email}. La séquence est suspendue.`, c, bouton: 'Corriger' }))
    ];
    const seqs = D.contacts.filter(c => c.seq);
    const nb = (e) => seqs.filter(c => c.seq.etat === e).length;
    const recents = D.contacts.filter(c => c.source === 'Landing').slice(0, 4);
    return coque(`
<div class="c-tete">
  <div><h1 class="c-titre">Bonjour Valentin</h1>
  <p class="c-sous">${D.aujourdhui[0].toUpperCase() + D.aujourdhui.slice(1)} : <b>${items.length} choses à faire</b>, ${nb('due')} relances partent ce matin.</p></div>
  <div class="c-actions"><a class="c-btn" href="?v=contacts">${ic('import')}Importer</a><a class="c-btn c-btn--plein" href="?v=contacts">${ic('plus')}Ajouter un contact</a></div>
</div>

<section class="c-parcours" aria-labelledby="parcours-titre">
  <h2 class="c-cache" id="parcours-titre">Parcours client</h2>
  <div class="c-parcours__grille">
    <div></div>${ETAPES.map(e => `<div class="c-parcours__etape"><b>${e.nom}</b><span>${e.info}</span></div>`).join('')}
    <div></div><div class="c-parcours__piste">${ETAPES.map((e, i) => `<i style="left:${(i + .5) / 6 * 100}%"></i>`).join('')}</div>
    ${ligne('Donateurs', pd, 'donateurs')}
    ${ligne('Entreprises', pe, 'entreprises')}
  </div>
</section>

<div class="c-deux">
  <section class="c-bloc" aria-labelledby="faire-titre">
    <div class="c-bloc__tete"><h2 class="c-h2" id="faire-titre">À faire aujourd'hui</h2><span class="m-micro">${items.length} éléments</span></div>
    <ul class="c-faire">${items.map(i => `<li><span class="c-pastille${i.cl ? ' c-pastille--' + i.cl : ''}">${ic(i.ic)}</span><div><p class="c-quoi">${i.quoi}</p><p class="c-qui">${i.qui}</p></div><a class="c-btn c-btn--s" href="${lienFiche(i.c)}">${i.bouton}</a></li>`).join('')}</ul>
  </section>
  <div class="c-pile">
    <section class="c-relances" aria-labelledby="rel-titre">
      <h2 class="c-h2" id="rel-titre">Relances automatiques</h2>
      <dl><div><dt>Partent ce matin</dt><dd>${nb('due')}</dd></div><div><dt>En cours</dt><dd>${nb('active')}</dd></div><div><dt>En pause</dt><dd>${nb('pause')}</dd></div><div><dt>En échec</dt><dd class="c-alerte">${nb('echec')}</dd></div></dl>
      <p>Envoi du lundi au vendredi, de 9 h à 18 h.</p>
    </section>
    <section class="c-bloc" aria-labelledby="ins-titre">
      <div class="c-bloc__tete"><h2 class="c-h2" id="ins-titre">Arrivés par la landing</h2><a class="c-lien-petit" href="?v=contacts&src=landing">Tout voir</a></div>
      <ul class="c-recents">${recents.map(c => `<li><span class="c-initiales${classeInit(c)}">${initiales(c)}</span><a href="${lienFiche(c)}" style="text-decoration:none"><b>${nomComplet(c)}</b><span>${c.type === 'entreprise' ? c.org : c.type === 'association' ? 'Association' : 'Donateur'}, via ${c.detail.toLowerCase()}</span></a><time>${c.act.replace(/^Inscrite? /, '')}</time></li>`).join('')}</ul>
    </section>
  </div>
</div>`);
  }

  /* ---------- Pipelines ---------- */
  function vPipelines() {
    const cle = q.get('p') || 'entreprises';
    const pipe = D.pipelines[cle];
    const contacts = D.contacts.filter(c => c.pipeline === cle);
    const onglets = Object.entries(D.pipelines).map(([k, p]) => `<button type="button" aria-pressed="${k === cle}" data-p="${k}">${p.nom} <span class="c-compte">${D.contacts.filter(c => c.pipeline === k).length}</span></button>`).join('');
    const col = (e) => {
      const cs = contacts.filter(c => c.etape === e);
      return `<section class="c-colonne" data-etape="${e}" aria-label="${e}"><div class="c-colonne__tete"><b>${e}</b><span class="c-compte">${cs.length}</span></div><div class="c-cartes">${cs.length ? cs.map(c => `
        <a class="c-carte" draggable="true" href="${lienFiche(c)}" data-id="${c.id}"><div class="c-carte__haut"><b>${c.type === 'entreprise' ? c.org : nomComplet(c)}</b>${note(c.note)}</div><span>${c.type === 'entreprise' ? (c.prenom ? `${c.prenom} ${c.nom}, ${c.poste}` : 'Aucun décideur trouvé') : c.type === 'association' ? c.org : 'Via ' + c.detail.toLowerCase()}</span>
        <div class="c-carte__pied">${etatSeq(c.seq)}</div></a>`).join('') : '<p class="c-vide">Glissez une carte ici</p>'}</div></section>`;
    };
    return coque(`
<div class="c-tete"><div><h1 class="c-titre">Pipelines</h1><p class="c-sous">Glissez une carte pour changer d'étape. La séquence en cours s'arrête si l'étape change à la main.</p></div>
<div class="c-actions"><a class="c-btn c-btn--plein" href="?v=contacts">${ic('plus')}Ajouter</a></div></div>
<div class="c-outils"><div class="c-seg js-segment" role="group" aria-label="Pipeline">${onglets}</div>
<div class="c-droite"><span class="c-perdus">Perdus : 0</span><label class="c-recherche">${ic('prospection')}<input type="search" placeholder="Chercher dans ce pipeline" aria-label="Chercher"></label></div></div>
<div class="c-colonnes" style="--n:${pipe.etapes.length}">${pipe.etapes.map(col).join('')}</div>`);
  }

  /* ---------- Contacts ---------- */
  function vContacts() {
    const filtre = q.get('t') || 'tous';
    const liste = D.contacts.filter(c => filtre === 'tous' || c.type === filtre);
    const types = [['tous', 'Tous'], ['donateur', 'Donateurs'], ['entreprise', 'Entreprises'], ['association', 'Associations']];
    return coque(`
<div class="c-tete"><div><h1 class="c-titre">Contacts</h1><p class="c-sous">${D.contacts.length} contacts, dont ${D.contacts.filter(c => c.source === 'Landing').length} arrivés par la landing et ${D.contacts.filter(c => c.source === 'Prospection').length} par la prospection.</p></div>
<div class="c-actions"><a class="c-btn" href="#">${ic('import')}Importer un CSV</a><a class="c-btn" href="#">${ic('export')}Exporter</a><a class="c-btn c-btn--plein" href="#">${ic('plus')}Ajouter</a></div></div>
<div class="c-outils"><div class="c-seg js-segment" role="group" aria-label="Type">${types.map(([k, l]) => `<button type="button" aria-pressed="${k === filtre}" data-t="${k}">${l}</button>`).join('')}</div>
<div class="c-droite"><label class="c-recherche">${ic('prospection')}<input type="search" placeholder="Nom, e-mail, entreprise" aria-label="Chercher un contact"></label></div></div>
<div class="c-liste" role="table" aria-label="Contacts">
  <div class="c-ligne c-ligne--tete" role="row"><span>Contact</span><span>Pipeline</span><span>Source</span><span>Note</span><span>Séquence</span><span>Dernière activité</span></div>
  ${liste.map(c => `<a class="c-ligne" role="row" href="${lienFiche(c)}">
    <span class="c-qui-cell"><span class="c-initiales${classeInit(c)}">${initiales(c)}</span><span><b>${nomComplet(c)}</b><span>${sousTitre(c) || c.org}</span></span></span>
    <span class="c-cell">${D.pipelines[c.pipeline].nom}<small>${c.etape}</small></span>
    <span class="c-cell">${c.source}<small>${c.detail}</small></span>
    <span class="c-cell">${note(c.note) || '<span class="c-cell--muet">Sans</span>'}</span>
    <span class="c-cell">${etatSeq(c.seq)}</span>
    <span class="c-cell c-cell--muet">${c.act}</span></a>`).join('')}
</div>`);
  }

  /* ---------- Fiche ---------- */
  function vFiche() {
    const c = D.contacts.find(x => x.id === +(q.get('id') || 20)) || D.contacts[0];
    const seqDef = c.seq ? D.sequences.find(s => s.nom === c.seq.nom) : null;
    const fil = c.id === 20 ? D.fil : [{ t: 'Récemment', c: 'systeme', titre: c.act, texte: '' }, { t: 'Création', c: 'systeme', titre: c.source === 'Landing' ? 'Inscription via la landing' : 'Trouvé par la prospection', texte: `Source : ${c.detail}.` }];
    const pipe = D.pipelines[c.pipeline];
    return coque(`
<div class="c-fiche-tete"><span class="c-initiales${classeInit(c)}">${initiales(c)}</span>
  <div><h1 class="c-titre">${nomComplet(c)}</h1><p class="c-sous">${sousTitre(c)}</p></div>
  <div class="c-actions"><label class="c-etiquette" style="gap:8px">Étape
    <select aria-label="Étape" style="border:0;background:none;font:inherit;font-weight:750">${pipe.etapes.map(e => `<option${e === c.etape ? ' selected' : ''}>${e}</option>`).join('')}<option>Perdu</option></select></label>
  ${c.type === 'entreprise' ? `<a class="c-btn c-btn--plein" href="#">${ic('calendrier')}Planifier la démo</a>` : `<a class="c-btn c-btn--plein" href="#">${ic('email')}Écrire</a>`}</div>
</div>
<div class="c-trois">
  <section class="c-bloc" aria-label="Coordonnées">
    <dl class="c-infos">
      ${c.org ? `<div><dt>${c.type === 'association' ? 'Association' : 'Entreprise'}</dt><dd>${c.org}${c.effectif ? `, ${c.effectif}` : ''}</dd></div>` : ''}
      <div><dt>E-mail</dt><dd>${c.email ? `<a href="mailto:${c.email}">${c.email}</a>` : 'Inconnu'}</dd></div>
      ${c.type === 'entreprise' ? `<div><dt>LinkedIn</dt><dd><a href="#">Profil LinkedIn</a></dd></div>` : ''}
      <div><dt>Ville</dt><dd>${c.ville}</dd></div>
      <div><dt>Source</dt><dd>${c.source}, ${c.detail.toLowerCase()}</dd></div>
      ${c.type !== 'entreprise' ? `<div><dt>Consentement</dt><dd>Accepté sur la landing</dd></div>` : ''}
    </dl>
    ${c.note != null ? `<div class="c-separe"></div><div class="c-bloc__tete" style="margin:0"><h2 class="c-h3">Note de prospection</h2></div>
    <div class="c-note-grande"><strong>${c.note}</strong><span>/10</span></div><ul class="c-raisons">${c.raisons.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
  </section>
  <section class="c-bloc" aria-labelledby="fil-titre">
    <div class="c-bloc__tete"><h2 class="c-h2" id="fil-titre">Activité</h2></div>
    <form class="c-noter" onsubmit="return false"><input placeholder="Ajouter une note, un appel, un compte rendu" aria-label="Ajouter une note"><button class="c-btn c-btn--s" type="submit">Ajouter</button></form>
    <ol class="c-fil">${fil.map(f => `<li><span class="c-pastille${f.c === 'linkedin' && f.fort ? ' c-pastille--vert' : ''}">${ic(f.c)}</span><div><b>${f.titre}</b><time>${f.t}</time>${f.texte ? `<p${f.fort ? ' class="c-citation"' : ''}>${f.texte}</p>` : ''}</div></li>`).join('')}</ol>
  </section>
  <section class="c-bloc c-bloc--creme" aria-labelledby="seq-titre">
    <div class="c-bloc__tete"><h2 class="c-h2" id="seq-titre">Séquence</h2>${c.seq && ['due', 'active', 'pause'].includes(c.seq.etat) ? `<label class="c-switch" style="font-size:14px">Active<input type="checkbox"${c.seq.etat !== 'pause' ? ' checked' : ''} aria-label="Séquence active pour ce contact"></label>` : ''}</div>
    ${seqDef ? `<p class="m-petit" style="margin-bottom:16px"><b style="color:var(--m-encre)">${seqDef.nom}</b>. ${etatSeq(c.seq)}</p>
    <ol class="c-pas">${seqDef.pas.map((p, i) => { const n = i + 1; const fait = n < c.seq.pas || (n === c.seq.pas && ['arret', 'fini'].includes(c.seq.etat)); const coupe = c.seq.etat === 'arret' && n > c.seq.pas;
      return `<li class="${fait ? 'c-fait' : ''}${coupe ? ' c-coupe' : ''}"><span class="c-pas__rond">${fait ? ic('coche') : n}</span><div><b>${p.titre}</b><span>${p.j}, ${p.canal === 'email' ? 'e-mail' : 'LinkedIn'}${coupe ? ', annulé' : ''}</span></div></li>`; }).join('')}</ol>
    ${c.seq.etat === 'arret' ? `<p class="c-arret"><b>Arrêtée automatiquement.</b> Le contact a répondu, la suite est à vous.</p>` : ''}`
      : `<p class="m-petit">Aucune séquence en cours.</p><a class="c-btn c-btn--s" href="?v=sequences" style="margin-top:16px">${ic('plus')}Inscrire à une séquence</a>`}
  </section>
</div>`);
  }

  /* ---------- Séquences ---------- */
  function vSequences() {
    const cle = q.get('s') || 'prospection';
    const s = D.sequences.find(x => x.cle === cle);
    const txt = (t) => t.replace(/\{([^}]+)\}/g, '<em>$1</em>');
    return coque(`
<div class="c-tete"><div><h1 class="c-titre">Séquences</h1><p class="c-sous">Elles partent seules, du lundi au vendredi, de 9 h à 18 h. Une réponse, une désinscription ou un changement d'étape les arrête.</p></div></div>
<div class="c-seq">
  <nav class="c-seq-liste" aria-label="Séquences">${D.sequences.map(x => `<a class="c-seq-item" href="?v=sequences&s=${x.cle}"${x.cle === cle ? ' aria-current="page"' : ''}><b>${x.nom}</b><span>${x.public}. ${x.declencheur}</span><span class="c-etat c-etat--${x.actifs ? 'active' : 'arret'}">${x.actifs} contacts en cours</span></a>`).join('')}</nav>
  <section class="c-bloc" aria-labelledby="s-titre">
    <div class="c-bloc__tete"><div><h2 class="c-h2" id="s-titre">${s.nom}</h2><p class="m-petit" style="margin-top:4px">Démarre : ${s.declencheur.toLowerCase()}.</p></div>
    <label class="c-switch" style="font-size:15px">Active<input type="checkbox" checked aria-label="Séquence active"></label></div>
    <dl class="c-chiffres"><div><dt>En cours</dt><dd>${s.actifs}</dd></div><div><dt>Envoyés</dt><dd>${s.envoyes}</dd></div><div><dt>${s.ouverts == null ? 'Acceptées' : 'Ouverts'}</dt><dd>${s.ouverts == null ? 19 : s.ouverts}</dd></div><div><dt>Réponses</dt><dd>${s.reponses}</dd></div></dl>
    <ol class="c-etapes-seq">${s.pas.map(p => `<li><div class="c-quand"><b>${p.j}</b><span class="c-canal">${ic(p.canal)}${p.canal === 'email' ? 'E-mail' : 'LinkedIn'}</span></div><div class="c-message"><b>${p.titre}</b><p>${txt(p.apercu)}</p></div></li>`).join('')}</ol>
    <p class="c-arret" style="margin-top:20px"><b>S'arrête seule si :</b> le contact répond, se désinscrit, l'e-mail rebondit, ou l'étape change à la main.</p>
  </section>
</div>`);
  }

  /* ---------- Prospection ---------- */
  function vProspection() {
    const p = D.prospection;
    return coque(`
<div class="c-tete"><div><h1 class="c-titre">Prospection</h1><p class="c-sous">Chaque matin à 6 h : le registre des entreprises, puis LinkedIn pour trouver les RH et RSE. Les prospects notés 6/10 ou plus entrent dans la séquence.</p></div>
<div class="c-actions"><a class="c-btn c-btn--plein" href="#">${ic('prospection')}Lancer maintenant</a></div></div>
<div class="c-cible">
  <section class="c-bloc" aria-labelledby="cible-titre"><div class="c-bloc__tete"><h2 class="c-h2" id="cible-titre">Cible</h2><a class="c-lien-petit" href="#">Modifier</a></div>
    <dl><div><dt>Zone</dt><dd>${p.cible.zone}</dd></div><div><dt>Taille</dt><dd>${p.cible.effectif}</dd></div><div><dt>Invitations par jour</dt><dd>${p.cible.plafond} au plus</dd></div></dl>
    <div class="c-postes" aria-label="Postes visés">${p.cible.postes.map(x => `<span>${x}</span>`).join('')}</div></section>
  <section class="c-passage" aria-labelledby="pass-titre"><h2 class="c-h2" id="pass-titre">${p.dernier.quand}</h2>
    <dl><div><dt>Entreprises vues</dt><dd>${p.dernier.entreprises}</dd></div><div><dt>Nouvelles</dt><dd>${p.dernier.nouvelles}</dd></div><div><dt>Décideurs trouvés</dt><dd>${p.dernier.decideurs}</dd></div><div><dt>Entrées en séquence</dt><dd>${p.dernier.enSequence}</dd></div></dl></section>
</div>
<div class="c-liste" role="table" aria-label="Entreprises trouvées ce matin">
  <div class="c-ligne c-ligne--pros c-ligne--tete" role="row"><span>Entreprise</span><span>Secteur</span><span>Salariés</span><span>Décideur</span><span>Note</span><span>Suite</span></div>
  ${p.entreprises.map(e => `<div class="c-ligne c-ligne--pros" role="row"><span class="c-cell"><b style="font-weight:700">${e.nom}</b><small>${e.ville}</small></span><span class="c-cell c-cell--muet">${e.naf}</span><span class="c-cell">${e.effectif}</span><span class="c-cell">${e.decideur || '<span class="c-cell--muet">Aucun trouvé</span>'}</span><span class="c-cell">${note(e.note)}</span><span class="c-cell c-cell--muet">${e.suite}</span></div>`).join('')}
</div>`);
  }

  /* ---------- Réglages ---------- */
  function vReglages() {
    return coque(`
<div class="c-tete"><div><h1 class="c-titre">Réglages</h1><p class="c-sous">Pilote de Strasbourg, ouvert le ${D.piloteOuvert}.</p></div></div>
<div class="c-reglages">
  <section class="c-bloc" aria-labelledby="r1"><h2 class="c-h2" id="r1">Relances</h2>
    <div class="c-option"><div><b>Relances automatiques</b><span>Coupe tout d'un coup. Les séquences reprennent là où elles étaient.</span></div><label class="c-switch"><input type="checkbox" checked class="js-pause-miroir" aria-label="Relances automatiques"></label></div>
    <div class="c-option"><div><b>Créneau d'envoi</b><span>Du lundi au vendredi, de 9 h à 18 h, heure de Paris</span></div><a class="c-lien-petit" href="#">Modifier</a></div>
    <div class="c-option"><div><b>Ouverture du pilote</b><span>Déclenche la séquence « Ouverture du pilote » pour tous les donateurs inscrits</span></div><span class="c-ok">Ouvert le ${D.piloteOuvert}</span></div>
    <div class="c-option"><div><b>Expéditeur</b><span>Valentin de MERCI, bonjour@merci-exemple.fr</span></div><a class="c-lien-petit" href="#">Modifier</a></div>
  </section>
  <section class="c-bloc" aria-labelledby="r2"><h2 class="c-h2" id="r2">Connexions</h2>
    <div class="c-option"><div><b>Formulaire de la landing</b><span>merci-pilote-strasbourg.vercel.app</span></div><span class="c-ok">Reçoit</span></div>
    <div class="c-option"><div><b>E-mails, Resend</b><span>Domaine d'envoi vérifié</span></div><span class="c-ok">Connecté</span></div>
    <div class="c-option"><div><b>LinkedIn</b><span>Compte de Valentin</span></div><span class="c-ok">Connecté</span></div>
    <div class="c-option"><div><b>App MERCI</b><span>Comptes créés et dons remontent tout seuls</span></div><a class="c-btn c-btn--s" href="#">Copier la clé</a></div>
  </section>
  <section class="c-bloc" aria-labelledby="r3"><div class="c-bloc__tete"><h2 class="c-h2" id="r3">Équipe</h2><a class="c-btn c-btn--s c-btn--plein" href="#">${ic('plus')}Inviter</a></div>
    ${D.equipe.map(m => `<div class="c-option"><div><b>${m.prenom}</b><span>${m.email}</span></div><span class="c-etiquette">${m.role}</span></div>`).join('')}
  </section>
</div>`);
  }

  /* ---------- Connexion ---------- */
  function vConnexion() {
    
    return `<main class="c-connexion"><div class="c-connexion__carte">
<img src="assets/logo-noir.png" alt="MERCI" width="110" height="30">
<h1 class="c-titre">Espace équipe</h1><p class="c-sous">Recevez un lien de connexion par e-mail.</p>
<form onsubmit="return false"><label for="mail">E-mail de l'équipe</label><input id="mail" type="email" autocomplete="email" placeholder="prenom@merci.fr">
<button class="c-btn c-btn--plein c-btn--l" type="submit">Recevoir le lien</button></form>
<p class="m-micro">Réservé à l'équipe MERCI. Le lien est valable 15 minutes.</p></div></main>
<p class="c-exemple">Preview <a href="?v=accueil">Retour au CRM</a></p>`;
  }

  const VUES = { accueil: vAccueil, pipelines: vPipelines, contacts: vContacts, fiche: vFiche, sequences: vSequences, prospection: vProspection, reglages: vReglages, connexion: vConnexion };
  document.body.innerHTML = (VUES[vue] || vAccueil)();
  document.title = 'CRM MERCI, ' + ({ accueil: 'accueil', pipelines: 'pipelines', contacts: 'contacts', fiche: 'fiche contact', sequences: 'séquences', prospection: 'prospection', reglages: 'réglages', connexion: 'connexion' }[vue] || 'accueil');

  /* ---------- Interactions ---------- */
  // Segments : galet glissant
  document.querySelectorAll('.js-segment').forEach(seg => {
    const place = () => { const b = seg.querySelector('[aria-pressed="true"]'); if (!b) return; seg.style.setProperty('--x', b.offsetLeft - 4 + 'px'); seg.style.setProperty('--w', b.offsetWidth + 'px'); };
    seg.classList.add('c-sans-anim'); place(); const go = () => { place(); requestAnimationFrame(() => seg.classList.remove('c-sans-anim')); }; document.fonts ? document.fonts.ready.then(go) : go();
    seg.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      const u = new URL(location.href);
      if (b.dataset.p) u.searchParams.set('p', b.dataset.p);
      if (b.dataset.t) u.searchParams.set('t', b.dataset.t);
      seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b)); place();
      setTimeout(() => location.href = u, 260);
    });
  });

  // Pause générale
  const pause = $('#pause-gen'), miroir = $('.js-pause-miroir');
  const applique = (on) => {
    document.documentElement.classList.toggle('relances-off', !on);
    if (pause) pause.checked = on; if (miroir) miroir.checked = on;
    const t = $('#pause-txt'); if (t) t.textContent = on ? 'Relances actives' : 'Relances en pause';
    sessionStorage.setItem('crm-pause', on ? '0' : '1');
  };
  applique(q.get('pause') === '1' ? false : sessionStorage.getItem('crm-pause') !== '1');
  [pause, miroir].forEach(x => x && x.addEventListener('change', () => applique(x.checked)));
  const rep = $('#reprendre'); if (rep) rep.addEventListener('click', () => applique(true));

  // Glisser-déposer dans les pipelines
  let tenu = null;
  document.querySelectorAll('.c-carte').forEach(c => {
    c.addEventListener('dragstart', e => { tenu = c; c.classList.add('c-tient'); e.dataTransfer.effectAllowed = 'move'; });
    c.addEventListener('dragend', () => { c.classList.remove('c-tient'); tenu = null; });
  });
  document.querySelectorAll('.c-colonne').forEach(col => {
    col.addEventListener('dragover', e => { if (!tenu) return; e.preventDefault(); col.classList.add('c-survol'); });
    col.addEventListener('dragleave', () => col.classList.remove('c-survol'));
    col.addEventListener('drop', e => {
      e.preventDefault(); col.classList.remove('c-survol'); if (!tenu) return;
      const ancien = tenu.closest('.c-colonne'); const z = col.querySelector('.c-cartes');
      const vide = z.querySelector('.c-vide'); if (vide) vide.remove();
      z.prepend(tenu);
      const pied = tenu.querySelector('.c-etat'); if (pied && !pied.classList.contains('c-etat--arret')) { pied.className = 'c-etat c-etat--arret'; pied.textContent = 'Arrêtée : étape changée'; }
      [ancien, col].forEach(k => { k.querySelector('.c-compte').textContent = k.querySelectorAll('.c-carte').length; if (!k.querySelector('.c-carte')) k.querySelector('.c-cartes').innerHTML = '<p class="c-vide">Glissez une carte ici</p>'; });
    });
  });
})();
