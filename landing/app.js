/* MERCI landing v6 vercel : interactions, mesure (GA4 après accord) et formulaire. Données dans donnees.js. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduit = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const { CAUSES, ASSOS } = window.MERCI;
  const parId = id => ASSOS.find(a => a.id === id);
  const picto = a => `assets/${CAUSES[a.cause].picto}.png`;
  const echappe = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  requestAnimationFrame(() => document.body.classList.add('charge'));

  /* ---------- Mesure : GA4 chargé seulement après accord ---------- */
  const GA4 = ($('meta[name="merci-ga4"]') || {}).content || '';
  const CLE_CHOIX = 'merci-cookies';
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { dataLayer.push(arguments); };
  gtag('consent', 'default', { analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' });
  let gaCharge = false;
  const chargeGA = () => {
    if (gaCharge || !GA4) return; gaCharge = true;
    gtag('consent', 'update', { analytics_storage: 'granted' });
    const s = document.createElement('script'); s.async = true; s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(GA4);
    document.head.appendChild(s); gtag('js', new Date()); gtag('config', GA4);
  };
  const mesure = (nom, params) => { if (gaCharge) gtag('event', nom, params || {}); };
  const lisChoix = () => { try { const c = JSON.parse(localStorage.getItem(CLE_CHOIX) || 'null'); return c && Date.now() - c.date < 182 * 864e5 ? c.choix : null; } catch (x) { return null; } };
  const bandeau = $('#cookies');
  const montreBandeau = v => { bandeau.hidden = !v; };
  bandeau.addEventListener('click', e => {
    const b = e.target.closest('[data-cookies]'); if (!b) return;
    const choix = b.dataset.cookies;
    localStorage.setItem(CLE_CHOIX, JSON.stringify({ choix, date: Date.now() }));
    montreBandeau(false);
    if (choix === 'accepte') chargeGA();
    else if (gaCharge) { gtag('consent', 'update', { analytics_storage: 'denied' }); location.reload(); }
  });
  document.addEventListener('click', e => { if (e.target.closest('[data-cookies-ouvrir]')) montreBandeau(true); });
  const choix0 = lisChoix();
  if (choix0 === 'accepte') chargeGA(); else if (!choix0) montreBandeau(true);
  document.addEventListener('click', e => { const c = e.target.closest('[data-cta]'); if (c) mesure('cta_click', { emplacement: c.dataset.cta }); });
  let vu75 = false;
  addEventListener('scroll', () => { if (vu75) return; const h = document.documentElement; if ((scrollY + innerHeight) / h.scrollHeight >= .75) { vu75 = true; mesure('scroll', { percent_scrolled: 75 }); } }, { passive: true });

  /* ---------- Barre flottante ---------- */
  const barre = $('#barre'); let dernierY = 0;
  addEventListener('scroll', () => {
    const y = scrollY;
    if (y > 300 && y > dernierY + 4) barre.classList.add('cachee');
    else if (y < dernierY - 4 || y < 300) barre.classList.remove('cachee');
    dernierY = y;
  }, { passive: true });

  /* ---------- Héros : parallaxe des galets ---------- */
  const amas = $('#amas');
  if (!reduit) {
    let mx = 0, my = 0, tx = 0, ty = 0;
    addEventListener('pointermove', e => { tx = e.clientX / innerWidth - .5; ty = e.clientY / innerHeight - .5; }, { passive: true });
    const boucle = () => {
      mx += (tx - mx) * .06; my += (ty - my) * .06;
      const s = Math.min(1.2, scrollY / innerHeight);
      if (s < 1.2) { amas.style.setProperty('--mx', mx.toFixed(4)); amas.style.setProperty('--my', my.toFixed(4)); amas.style.setProperty('--s', s.toFixed(4)); }
      requestAnimationFrame(boucle);
    };
    boucle();
  }

  /* ---------- Apparitions ---------- */
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('est-visible'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px' });
  const observe = r => $$('.m-revele:not(.est-visible)', r).forEach(el => io.observe(el));
  observe(document);

  /* ---------- Segments à galet glissant ---------- */
  const placeSegment = seg => { const b = $('[aria-pressed="true"]', seg); if (!b) return; seg.style.setProperty('--x', b.offsetLeft + 'px'); seg.style.setProperty('--w', b.offsetWidth + 'px'); };
  const tousSegments = () => $$('.m-segment').forEach(placeSegment);
  addEventListener('resize', tousSegments);
  document.fonts && document.fonts.ready.then(tousSegments);

  /* ---------- Bento ---------- */
  $('#bento-montants').addEventListener('click', e => { const b = e.target.closest('[data-m]'); if (!b) return; $$('#bento-montants button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); });
  const suiviBento = $('#bento-suivi'), etapesBento = $$('#bento-suivi li');
  let pb = 0;
  const avanceBento = () => { pb = (pb + 1) % 4; suiviBento.style.setProperty('--p', ((pb + 1) / 4).toFixed(2)); etapesBento.forEach((li, i) => li.classList.toggle('fait', i <= pb)); };
  etapesBento[0].classList.add('fait');
  if (!reduit) { const ioB = new IntersectionObserver(es => { if (es[0].isIntersecting) { setInterval(avanceBento, 1600); ioB.disconnect(); } }, { threshold: .5 }); ioB.observe(suiviBento); }

  /* ---------- Histoire défilante ---------- */
  const histoire = $('#histoire'), recits = $$('.recit'), pastilles = $$('.pastilles i');
  const MSG = ['Votre don est bien enregistré.', "Bien arrivé à l'association.", 'Il sert au repas du dimanche.', 'La facture est en ligne.', '42 repas servis. Merci !'];
  let etape = -1;
  const majHistoire = () => {
    const r = histoire.getBoundingClientRect();
    const p = Math.min(.999, Math.max(0, -r.top / (r.height - innerHeight)));
    const n = Math.floor(p * 5), tel = $('.tel', histoire);
    tel.style.setProperty('--rot', ((p - .5) * -6).toFixed(2) + 'deg'); tel.style.setProperty('--ty', ((p - .5) * -30).toFixed(1) + 'px');
    if (n === etape) return; etape = n; histoire.dataset.etape = n;
    recits.forEach((el, i) => { el.classList.toggle('actif', i === n); el.classList.toggle('passe', i < n); });
    pastilles.forEach((el, i) => el.classList.toggle('actif', i === n));
    $('#h-suivi').style.setProperty('--p', ((n + 1) / 5).toFixed(2)); $('#h-msg').textContent = MSG[n];
  };
  addEventListener('scroll', majHistoire, { passive: true }); majHistoire();

  /* ---------- Dock des causes : sélection + recommandations ---------- */
  const choisies = new Set(['solidarite']);
  const dock = $('#dock'), nom = $('#dock-nom');
  dock.innerHTML = Object.entries(CAUSES).map(([k, c]) => `<button type="button" data-cause="${k}" aria-pressed="${choisies.has(k)}" aria-label="${c.nom}"><img src="assets/${c.picto}.png" alt=""></button>`).join('');
  const boutonsDock = $$('button', dock);
  const montreNom = t => { nom.innerHTML = ''; const s = document.createElement('span'); s.textContent = t; nom.appendChild(s); };
  const grossit = x => boutonsDock.forEach(b => {
    const r = b.getBoundingClientRect(), d = Math.abs(x - (r.left + r.width / 2)), k = Math.max(0, 1 - d / (r.width * 2.6)), sc = 1 + .62 * Math.pow(k, 1.6);
    b.style.setProperty('--sc', sc.toFixed(3)); b.style.setProperty('--dy', (-(sc - 1) * 30).toFixed(1) + 'px');
  });
  const repos = () => boutonsDock.forEach(b => { b.style.setProperty('--sc', 1); b.style.setProperty('--dy', '0px'); });
  const resumeChoix = () => choisies.size ? [...choisies].map(k => CAUSES[k].nom).join(', ') : 'Aucune cause choisie';
  dock.addEventListener('pointermove', e => { if (e.pointerType === 'mouse') grossit(e.clientX); });
  dock.addEventListener('pointerleave', () => { repos(); montreNom(resumeChoix()); });
  boutonsDock.forEach(b => {
    b.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') montreNom(CAUSES[b.dataset.cause].nom); });
    b.addEventListener('focus', () => { montreNom(CAUSES[b.dataset.cause].nom); const r = b.getBoundingClientRect(); grossit(r.left + r.width / 2); });
    b.addEventListener('blur', repos);
    b.addEventListener('click', () => {
      const k = b.dataset.cause; choisies.has(k) ? choisies.delete(k) : choisies.add(k);
      b.setAttribute('aria-pressed', String(choisies.has(k))); montreNom(resumeChoix()); rendRecos();
    });
  });
  const rendRecos = () => {
    const liste = ASSOS.filter(a => choisies.has(a.cause)).slice(0, 3);
    $('#recos').innerHTML = liste.length ? liste.map((a, i) => `
      <article class="reco" style="--i:${i}">
        <div class="reco__haut"><img src="${picto(a)}" alt=""><div><h3 class="m-t3" style="font-size:22px">${a.nom}</h3><p class="m-micro">${a.quartier}</p></div></div>
        <p class="pourquoi">Parce que vous avez choisi ${CAUSES[a.cause].nom.toLowerCase()}.</p>
        <p class="m-petit">${a.accroche}</p>
        <div class="actions"><button class="m-galet m-galet--s" type="button" data-donner="${a.id}">Donner</button><button class="lien-fiche" type="button" data-voir="${a.id}">Voir la fiche</button></div>
      </article>`).join('') : '<p class="vide">Choisissez au moins une cause pour voir les associations qui s\'en occupent.</p>';
  };
  rendRecos();

  /* ---------- Associations : filtres + fiche ---------- */
  let filtre = 'tout', ouverte = null;
  const filtres = $('#filtres');
  filtres.innerHTML = [['tout', 'Toutes', null], ...Object.entries(CAUSES).map(([k, c]) => [k, c.nom, c.picto])]
    .map(([k, n, p]) => `<button class="m-puce${p ? '' : ' m-puce--sans-icone'}" type="button" data-filtre="${k}" aria-pressed="${k === filtre}">${p ? `<img src="assets/${p}.png" alt="">` : ''}${n}</button>`).join('');
  const chevron = '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const fiche = a => `
    <div class="fiche" id="fiche-${a.id}">
      <div class="fiche__col">
        <p>${a.description}</p>
        <div class="fiche__impact">
          <span class="m-micro">À quoi sert votre don</span>
          <b>Par exemple : ${a.impact[20]}.</b>
          <div class="repartition" role="img" aria-label="80 % pour le terrain, 20 % pour le fonctionnement"><span style="flex:80"></span><span style="flex:20"></span></div>
          <span class="m-petit">80 % pour les actions, 20 % pour le fonctionnement (exemple).</span>
        </div>
      </div>
      <div class="fiche__col">
        <span class="m-micro">Projets en cours</span>
        ${a.projets.map(p => `<div class="projet"><b>${p.nom}</b><ol class="jalons" aria-label="Avancement : ${p.jalons[p.etape]}">${p.jalons.map((j, i) => `<li class="${i < p.etape ? 'fait' : i === p.etape ? 'encours' : ''}"${i === p.etape ? ' aria-current="step"' : ''}>${j}</li>`).join('')}</ol></div>`).join('')}
      </div>
    </div>`;
  const rendAssos = () => {
    $('#assos').innerHTML = ASSOS.filter(a => filtre === 'tout' || a.cause === filtre).map(a => `
      <article class="asso${ouverte === a.id ? ' ouverte' : ''}" id="asso-${a.id}">
        <div class="asso__haut"><img src="${picto(a)}" alt=""><div><h3 class="m-t3" style="font-size:22px">${a.nom}</h3><p class="asso__meta">${CAUSES[a.cause].nom}, ${a.quartier}</p></div></div>
        <p class="asso__accroche">${a.accroche}</p>
        ${ouverte === a.id ? fiche(a) : ''}
        <div class="asso__actions">
          <button class="m-galet m-galet--s" type="button" data-donner="${a.id}">Donner</button>
          <button class="lien-fiche" type="button" data-fiche="${a.id}" aria-expanded="${ouverte === a.id}"${ouverte === a.id ? ` aria-controls="fiche-${a.id}"` : ''}>${ouverte === a.id ? 'Fermer la fiche' : 'Voir la fiche'} ${chevron}</button>
        </div>
      </article>`).join('');
  };
  filtres.addEventListener('click', e => {
    const b = e.target.closest('[data-filtre]'); if (!b) return;
    filtre = b.dataset.filtre; ouverte = null;
    $$('[data-filtre]', filtres).forEach(x => x.setAttribute('aria-pressed', String(x === b))); rendAssos();
  });
  const ouvreFiche = (id, defile) => {
    ouverte = ouverte === id ? null : id;
    if (ouverte && filtre !== 'tout' && parId(id).cause !== filtre) { filtre = 'tout'; $$('[data-filtre]', filtres).forEach(x => x.setAttribute('aria-pressed', String(x.dataset.filtre === 'tout'))); }
    rendAssos();
    const el = $('#asso-' + id);
    if (el) { if (defile) el.scrollIntoView({ behavior: reduit ? 'auto' : 'smooth', block: 'start' }); $('[data-fiche]', el).focus({ preventScroll: true }); }
  };
  rendAssos();


  /* ---------- Reçus et mercis (exemples) ---------- */
  const RECUS = [['panier', '12 sept. 2026'], ['ecole', '3 sept. 2026'], ['refuge', '18 juil. 2026']];
  $('#recus').innerHTML = RECUS.map(([id, d]) => { const a = parId(id); return `<li class="recu"><img src="${picto(a)}" alt=""><div><b>${a.nom}</b><small>${d}, ${a.taux} %</small></div><span class="pdf">PDF</span></li>`; }).join('');
  const FIL = [['forets', "Les haies de l'école du Neuhof sont plantées. Merci pour votre aide."], ['panier', '42 repas servis dimanche. Merci à vous.']];
  $('#fil').innerHTML = FIL.map(([id, t]) => { const a = parId(id); return `<li><img src="${picto(a)}" alt=""><p><b>${a.nom}</b>${t}</p></li>`; }).join('');

  /* ---------- Feuille « Soutenir » : aucun montant, version test ---------- */
  const feuille = $('#feuille'), voile = $('#voile'), corpsF = $('#corps-feuille');
  let asso = null, freq = 1, retour = null;
  const RYTHMES = ['Une fois', 'Tous les mois', 'Sur ma paie'];
  const rendFeuille = () => {
    const p = asso.projets[0];
    corpsF.innerHTML = `
      <div class="qui"><img src="${picto(asso)}" alt=""><div><span class="m-micro">Vous soutenez</span><div class="m-t3" id="f-nom" style="font-size:22px">${asso.nom}</div></div>
        <button class="m-galet m-galet--rond m-galet--s m-galet--creme" type="button" data-fermer aria-label="Fermer"><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div>
      <div class="m-segment" role="group" aria-label="Fréquence du don" style="justify-self:start">${RYTHMES.map((r, i) => `<button type="button" data-freq="${i}" aria-pressed="${freq === i}">${r}</button>`).join('')}</div>
      <div class="impact" aria-live="polite"><b>Projet du moment : ${p.nom}.</b><span>Par exemple : ${asso.impact[20]}. Vous suivrez chaque étape, jusqu'au merci.</span></div>
      <a class="m-galet m-galet--l" href="#pilote" data-cta="feuille" data-pilote-depuis-feuille>Rejoindre le pilote</a>
      <p class="note">Les dons ouvriront en 2027. Inscrivez-vous pour être prévenu.</p>`;
    placeSegment($('.m-segment', corpsF));
  };
  const ouvreDon = id => {
    asso = parId(id); freq = 1; retour = document.activeElement;
    rendFeuille(); feuille.dataset.etat = 'ouvert'; voile.dataset.etat = 'ouvert'; document.body.style.overflow = 'hidden';
    requestAnimationFrame(() => { placeSegment($('.m-segment', corpsF)); const b = $('[data-freq][aria-pressed="true"]', corpsF); b && b.focus({ preventScroll: true }); });
  };
  const fermeDon = (rendFocus = true) => { feuille.dataset.etat = 'ferme'; voile.dataset.etat = 'ferme'; document.body.style.overflow = ''; if (rendFocus && retour) retour.focus({ preventScroll: true }); };
  corpsF.addEventListener('click', e => {
    const f = e.target.closest('[data-freq]'); if (f) { freq = +f.dataset.freq; rendFeuille(); $(`[data-freq="${freq}"]`, corpsF).focus(); return; }
    if (e.target.closest('[data-fermer]')) return fermeDon();
    if (e.target.closest('[data-pilote-depuis-feuille]')) fermeDon(false);
  });
  voile.addEventListener('click', () => fermeDon());
  feuille.addEventListener('keydown', e => {
    if (e.key === 'Escape') fermeDon();
    if (e.key === 'Tab') { const f = $$('button:not([disabled]), input', feuille); if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f.at(-1).focus(); } else if (!e.shiftKey && document.activeElement === f.at(-1)) { e.preventDefault(); f[0].focus(); } }
  });
  let y0 = null;
  feuille.addEventListener('pointerdown', e => { if (e.target.closest('button, input')) return; y0 = e.clientY; feuille.style.transition = 'none'; });
  addEventListener('pointermove', e => { if (y0 === null) return; feuille.style.transform = `translateY(${Math.max(0, e.clientY - y0)}px)`; });
  addEventListener('pointerup', e => { if (y0 === null) return; const d = e.clientY - y0; y0 = null; feuille.style.transition = ''; feuille.style.transform = ''; if (d > 120) fermeDon(); });

  /* ---------- Merci ---------- */
  const merci = $('#merci');
  const valide = btn => {
    const r = btn.getBoundingClientRect();
    merci.style.setProperty('--cx', (r.left + r.width / 2) + 'px'); merci.style.setProperty('--cy', (r.top + r.height / 2) + 'px');
    $('#merci-texte').textContent = `Votre geste compte déjà. ${asso.nom} vous dira ce qu'il a construit.`;
    fermeDon(false); merci.hidden = false; document.body.style.overflow = 'hidden';
    requestAnimationFrame(() => requestAnimationFrame(() => merci.classList.add('ouvert')));
    const c = $('#confetti'); c.innerHTML = '';
    if (!reduit) {
      const coul = ['#53C973', '#D9EDBC', '#1E3F22', '#F1EDE3', '#FFFFFF'];
      for (let i = 0; i < 46; i++) {
        const el = document.createElement('i');
        el.style.cssText = `left:${Math.random() * 100}%;--t:${10 + Math.random() * 26}px;--c:${coul[i % coul.length]};--d:${2.4 + Math.random() * 2}s;--delai:${.35 + Math.random() * .9}s;--dx:${(Math.random() - .5) * 200}px;--rot:${(Math.random() - .5) * 720}deg`;
        c.appendChild(el);
      }
    }
    setTimeout(() => $('#merci-titre').focus(), 400);
  };
  const fermeMerci = () => {
    merci.classList.remove('ouvert'); document.body.style.overflow = '';
    setTimeout(() => { merci.hidden = true; histoire.scrollIntoView({ behavior: reduit ? 'auto' : 'smooth' }); }, reduit ? 0 : 700);
  };
  $('#fermer-merci').addEventListener('click', fermeMerci);
  merci.addEventListener('keydown', e => { if (e.key === 'Escape') fermeMerci(); });

  /* Délégation : Donner et Voir la fiche */
  document.addEventListener('click', e => {
    const d = e.target.closest('[data-donner]'); if (d) return ouvreDon(d.dataset.donner);
    const f = e.target.closest('[data-fiche]'); if (f) return ouvreFiche(f.dataset.fiche, false);
    const v = e.target.closest('[data-voir]'); if (v) return ouvreFiche(v.dataset.voir, true);
  });

  /* ---------- Formulaire pilote ---------- */
  let profil = 'donateur';
  const segProfil = $('#profil');
  segProfil.addEventListener('click', e => {
    const b = e.target.closest('[data-profil]'); if (!b) return;
    profil = b.dataset.profil; $$('button', segProfil).forEach(x => x.setAttribute('aria-pressed', String(x === b))); placeSegment(segProfil);
    const s = profil !== 'donateur'; $('#champ-structure').hidden = !s; $('#champs-entreprise').hidden = profil !== 'entreprise';
    $('#champ-structure label').textContent = profil === 'association' ? "Nom de l'association" : "Nom de l'entreprise";
  });
  document.addEventListener('click', e => {
    const l = e.target.closest('[data-profil-lien]'); if (!l) return;
    const b = segProfil.querySelector(`[data-profil="${l.dataset.profilLien}"]`); if (b) b.click();
  });
  let formCommence = false;
  $('#form-pilote').addEventListener('input', () => { if (!formCommence) { formCommence = true; mesure('form_start', { profil }); } });
  $('#form-pilote').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.currentTarget, err = $('#p-erreur');
    $$('.m-champ', f).forEach(c => c.classList.remove('m-champ--erreur'));
    const manque = [];
    if (!$('#p-prenom').value.trim()) manque.push(['#p-prenom', 'votre prénom']);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test($('#p-mail').value.trim())) manque.push(['#p-mail', 'un e-mail valide, par exemple prenom@mail.fr']);
    if (profil !== 'donateur' && !$('#p-structure').value.trim()) manque.push(['#p-structure', 'le nom de la structure']);
    if (!$('#p-ok').checked) manque.push(['#p-ok', "votre accord pour qu'on vous écrive"]);
    if (manque.length) {
      manque.forEach(([s]) => { const c = $(s).closest('.m-champ'); if (c) c.classList.add('m-champ--erreur'); });
      err.textContent = 'Il manque ' + manque.map(m => m[1]).join(', ') + '.'; err.hidden = false; $(manque[0][0]).focus(); return;
    }
    err.hidden = true;
    const utm = (new URLSearchParams(location.search).get('utm_source') || '').trim().slice(0, 60);
    const lead = {
      profil, prenom: $('#p-prenom').value.trim(), email: $('#p-mail').value.trim(), structure: profil === 'donateur' ? '' : $('#p-structure').value.trim(),
      source: 'landing', source_detail: utm || undefined,
      role: profil === 'entreprise' ? $('#p-role').value || undefined : undefined, effectif: profil === 'entreprise' ? $('#p-effectif').value || undefined : undefined, date: new Date().toISOString(),
      consentement: true, consentement_texte: $('#p-ok').closest('label').textContent.trim(), site_web: $('#p-site').value
    };
    const btn = $('button[type="submit"]', f); btn.disabled = true; btn.textContent = 'Envoi en cours';
    try {
      const local = ['127.0.0.1', 'localhost'].includes(location.hostname);
      const adresse = local && f.dataset.endpointLocal ? f.dataset.endpointLocal : f.dataset.endpoint;
      if (adresse) {
        const r = await fetch(adresse, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(lead) });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          const e = new Error(r.status);
          e.message_fr = r.status === 429 ? "Trop d'envois depuis cet appareil. Réessayez dans une minute."
            : r.status === 422 && typeof d.detail === 'string' ? d.detail + '.' : null;
          throw e;
        }
      }
      else { const l = JSON.parse(localStorage.getItem('merci-leads') || '[]'); l.push(lead); localStorage.setItem('merci-leads', JSON.stringify(l)); }
      mesure('generate_lead', { profil, source: utm || 'direct' });
      f.hidden = true; const ok = $('#pilote-ok'); ok.hidden = false; ok.focus();
    } catch (x) {
      err.textContent = x.message_fr || "L'envoi n'a pas abouti. Vérifiez votre connexion puis réessayez."; err.hidden = false;
      btn.disabled = false; btn.textContent = 'Rejoindre le pilote';
    }
  });

  /* ---------- Assistant ---------- */
  const QUESTIONS = [
    { q: 'Comment sont choisies les associations ?', k: ['choisi', 'sélection', 'critère', 'vérifi'], r: "Pour le pilote, nous rencontrons chaque association en Alsace et vérifions qu'elle peut délivrer des reçus fiscaux. Ensuite, elle publie un justificatif à chaque étape de ses projets." },
    { q: 'Mon don est-il sécurisé ?', k: ['sécur', 'paiement', 'carte', 'banc'], r: "Oui. Vos dons vont directement aux associations, par un organisme de paiement agréé. MERCI ne les garde jamais et ne voit pas vos coordonnées bancaires." },
    { q: 'Où trouver mes reçus fiscaux ?', k: ['reçu', 'fiscal', 'impôt', 'déclar'], r: "Dans votre compte, rubrique Reçus. Ils sont tous réunis, et au printemps un résumé est prêt pour votre déclaration." },
    { q: 'Comment arrêter un don mensuel ?', k: ['arrêt', 'annul', 'mensuel', 'stop'], r: "Depuis votre compte : ouvrez le don et choisissez Arrêter. C'est immédiat et gratuit. Si vous donnez par votre entreprise, la demande est transmise au service du personnel." },
    { q: 'MERCI prend-il une commission ?', k: ['frais', 'commission', 'gratuit', 'payant', 'prix'], r: "Non. Le donateur ne paie jamais et rien n'est retenu sur les dons. MERCI est financé par les entreprises, et par les associations qui choisissent des options." },
    { q: 'Comment donner avec mon entreprise ?', k: ['portefeuille', 'paie', 'salari', 'entreprise', 'abond'], r: "Si votre employeur propose MERCI, vous pouvez donner un peu chaque mois sur votre paie, et votre entreprise ajoute sa part. Vous choisissez vos associations quand vous voulez. Ce qui n'est pas attribué en fin d'année va à des projets de la région." },
    { q: 'Comment rejoindre le pilote ?', k: ['pilote', 'rejoindre', 'inscri', 'strasbourg', 'alsace'], r: "Laissez votre prénom et votre e-mail dans le formulaire en bas de la page. Nous vous écrirons avant l'ouverture en Alsace, en 2027." }
  ];
  const fil = $('#assistant-fil'), assistant = $('#assistant'), abtn = $('#assistant-btn');
  const bulle = (t, qui) => { const p = document.createElement('p'); p.className = `bulle bulle--${qui}`; p.textContent = t; fil.appendChild(p); fil.scrollTop = fil.scrollHeight; };
  const repond = texte => {
    bulle(texte, 'vous');
    const t = texte.toLowerCase(), trouve = QUESTIONS.find(x => x.k.some(k => t.includes(k)));
    setTimeout(() => bulle(trouve ? trouve.r : "Je n'ai pas la réponse à cette question. Laissez votre e-mail dans le formulaire du pilote, l'équipe vous répondra.", 'merci'), reduit ? 0 : 380);
  };
  const ouvreAssistant = ouvert => {
    assistant.dataset.etat = ouvert ? 'ouvert' : 'ferme'; abtn.setAttribute('aria-expanded', String(ouvert));
    if (ouvert) {
      if (!fil.children.length) { bulle('Bonjour ! Je réponds à vos questions sur MERCI. Choisissez une question ou posez la vôtre.', 'merci'); $('#questions').innerHTML = QUESTIONS.map((x, i) => `<button class="m-puce m-puce--sans-icone" type="button" data-q="${i}">${echappe(x.q)}</button>`).join(''); }
      setTimeout(() => $('#assistant-input').focus(), 80);
    } else abtn.focus();
  };
  abtn.addEventListener('click', () => ouvreAssistant(assistant.dataset.etat !== 'ouvert'));
  $('#assistant-fermer').addEventListener('click', () => ouvreAssistant(false));
  assistant.addEventListener('keydown', e => { if (e.key === 'Escape') ouvreAssistant(false); });
  $('#questions').addEventListener('click', e => { const b = e.target.closest('[data-q]'); if (!b) return; repond(QUESTIONS[+b.dataset.q].q); b.remove(); });
  $('#assistant-form').addEventListener('submit', e => { e.preventDefault(); const i = $('#assistant-input'), v = i.value.trim(); if (!v) return; i.value = ''; repond(v); });

  tousSegments();
})();
