/* MERCI landing v7 : pied de page animé.
   1. Ruban des mercis qui défile, accéléré par le défilement de la page.
   2. Titre qui apparaît mot par mot.
   3. Bac à galets : les huit causes tombent, rebondissent, s'empilent ; on peut les attraper et les lancer.
   Mouvement réduit : ruban immobile, galets posés d'emblée. */
(function () {
  'use strict';
  const pied = document.getElementById('pied'); if (!pied) return;
  const reduit = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Apparition ---------- */
  let visible = false;
  new IntersectionObserver(es => es.forEach(e => {
    visible = e.isIntersecting;
    if (visible) { pied.classList.add('vu'); demarrer(); }
  }), { threshold: .12 }).observe(pied);

  /* ---------- Ruban ---------- */
  const pistes = [...pied.querySelectorAll('.pied2__piste')];
  pistes.forEach(p => { p.innerHTML += p.innerHTML; }); // deux copies : boucle sans couture
  const etat = pistes.map(() => ({ x: 0 }));
  let dernierY = scrollY, elan = 0;
  addEventListener('scroll', () => { elan += Math.abs(scrollY - dernierY) * .6; dernierY = scrollY; }, { passive: true });
  const ruban = dt => {
    elan *= .92;
    pistes.forEach((p, i) => {
      const moitie = p.scrollWidth / 2, sens = +p.dataset.sens;
      etat[i].x -= sens * (40 + elan * 6) * dt * [1, .8, .65][i % 3];
      if (etat[i].x <= -moitie) etat[i].x += moitie;
      if (etat[i].x > 0) etat[i].x -= moitie;
      p.style.transform = `translate3d(${etat[i].x}px,0,0)`;
    });
  };
  if (pistes[2]) { etat[2].x = -pistes[2].scrollWidth / 3; pistes[2].style.transform = `translate3d(${etat[2].x}px,0,0)`; }
  if (!reduit) pistes[1].style.transform = `translate3d(${-pistes[1].scrollWidth / 4}px,0,0)`, etat[1].x = -pistes[1].scrollWidth / 4;

  /* ---------- Galets ---------- */
  const bac = document.getElementById('pied-bac');
  const CAUSES = [
    ['Solidarité', 'picto-solidarite', 'deg-rose-doux'], ['Éducation', 'picto-education', 'deg-vert-lumiere'],
    ['Santé et recherche', 'picto-sante-et-recherche', 'deg-rose-vert'], ['Urgences humanitaires', 'picto-urgences-humanitaires', 'deg-vert-profond'],
    ['Climat et environnement', 'picto-climat-et-environnement', 'deg-vert-lumiere'], ['Animaux et biodiversité', 'picto-animaux-et-biodiversite', 'deg-rose-doux'],
    ['Technologie', 'picto-technologie', 'deg-rose-vert'], ['Culture, sport et lien social', 'picto-culture-sport-lien-social', 'deg-vert-profond']
  ];
  let W = 0, H = 0, galets = [];
  const mesurer = () => { const r = bac.getBoundingClientRect(); W = r.width; H = r.height; };
  const creer = () => {
    mesurer();
    const base = Math.max(46, Math.min(W, 640) / 9.5);
    galets = CAUSES.map(([nom, picto, fond], i) => {
      const el = document.createElement('div');
      el.className = 'pied2-galet'; el.tabIndex = 0; el.setAttribute('role', 'button'); el.setAttribute('aria-label', nom);
      const r = base * (0.82 + ((i * 37) % 10) / 20);
      el.style.width = el.style.height = (r * 2) + 'px';
      el.style.backgroundImage = `url(assets/${fond}.jpg)`;
      el.innerHTML = `<img src="assets/${picto}.png" alt=""><span>${nom}</span>`;
      bac.appendChild(el);
      return { el, r, x: r + ((i * 0.61803) % 1) * (W - 2 * r), y: -r - i * r * 1.4, vx: (i % 2 ? 1 : -1) * 30, vy: 0, a: (i * 47) % 360, va: 0, tenu: false };
    });
  };
  const G = 1900, REBOND = .42, FROTTEMENT = .985;
  const pas = dt => {
    for (const g of galets) {
      if (g.tenu) continue;
      g.vy += G * dt; g.vx *= FROTTEMENT; g.vy *= .999;
      g.x += g.vx * dt; g.y += g.vy * dt; g.a += g.va * dt; g.va *= .97;
      if (g.y > H - g.r) { g.y = H - g.r; g.vy = -g.vy * REBOND; g.vx *= .9; g.va = g.vx * .9; if (Math.abs(g.vy) < 30) g.vy = 0; }
      if (g.x < g.r) { g.x = g.r; g.vx = Math.abs(g.vx) * REBOND; }
      if (g.x > W - g.r) { g.x = W - g.r; g.vx = -Math.abs(g.vx) * REBOND; }
    }
    for (let k = 0; k < 3; k++) for (let i = 0; i < galets.length; i++) for (let j = i + 1; j < galets.length; j++) {
      const a = galets[i], b = galets[j], dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || .01, min = (a.r + b.r) * .96;
      if (d >= min) continue;
      const nx = dx / d, ny = dy / d, sur = (min - d) / 2;
      const ma = a.tenu ? 0 : 1, mb = b.tenu ? 0 : 1, tot = ma + mb || 1;
      a.x -= nx * sur * 2 * ma / tot; a.y -= ny * sur * 2 * ma / tot; b.x += nx * sur * 2 * mb / tot; b.y += ny * sur * 2 * mb / tot;
      const rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
      if (rel < 0) { const imp = -(1 + REBOND) * rel / tot; a.vx -= imp * nx * ma; a.vy -= imp * ny * ma; b.vx += imp * nx * mb; b.vy += imp * ny * mb; }
    }
  };
  const dessiner = () => { for (const g of galets) g.el.style.transform = `translate3d(${g.x - g.r}px,${g.y - g.r}px,0) rotate(${g.a}deg)`; };

  /* Attraper, lancer */
  let tenu = null, traces = [];
  bac.addEventListener('pointerdown', e => {
    const el = e.target.closest('.pied2-galet'); if (!el) return;
    tenu = galets.find(g => g.el === el); tenu.tenu = true; el.classList.add('tenu'); bac.classList.add('touche');
    el.setPointerCapture(e.pointerId); traces = [[e.clientX, e.clientY, performance.now()]]; e.preventDefault();
  });
  bac.addEventListener('pointermove', e => {
    if (!tenu) return;
    const r = bac.getBoundingClientRect();
    tenu.x = Math.max(tenu.r, Math.min(W - tenu.r, e.clientX - r.left)); tenu.y = Math.max(tenu.r, Math.min(H - tenu.r, e.clientY - r.top));
    traces.push([e.clientX, e.clientY, performance.now()]); if (traces.length > 5) traces.shift();
    if (reduit) dessiner();
  });
  const lacher = () => {
    if (!tenu) return;
    const [a, b] = [traces[0], traces[traces.length - 1]], dt = Math.max(16, b[2] - a[2]) / 1000;
    tenu.vx = Math.max(-2400, Math.min(2400, (b[0] - a[0]) / dt)); tenu.vy = Math.max(-2400, Math.min(2400, (b[1] - a[1]) / dt)); tenu.va = tenu.vx * .6;
    tenu.tenu = false; tenu.el.classList.remove('tenu'); tenu = null; reveiller();
  };
  bac.addEventListener('pointerup', lacher); bac.addEventListener('pointercancel', lacher);
  /* Clavier : Entrée ou Espace fait sauter le galet */
  bac.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const g = galets.find(x => x.el === document.activeElement); if (!g) return;
    e.preventDefault(); g.vy = -900; g.vx = (Math.random() - .5) * 500; g.va = g.vx; bac.classList.add('touche'); reveiller();
  });

  /* ---------- Boucle ---------- */
  let tourne = false, avant = 0, calme = 0, lance = false;
  const boucle = t => {
    const dt = Math.min(.033, (t - avant) / 1000 || .016); avant = t;
    ruban(dt);
    if (galets.length) {
      const sous = 3; for (let s = 0; s < sous; s++) pas(dt / sous);
      dessiner();
      const bouge = galets.some(g => g.tenu || Math.abs(g.vx) > 4 || Math.abs(g.vy) > 4);
      calme = bouge ? 0 : calme + 1;
    }
    if (visible) requestAnimationFrame(boucle); else tourne = false;
  };
  const reveiller = () => { if (!reduit && !tourne && visible) { tourne = true; avant = performance.now(); requestAnimationFrame(boucle); } };
  /* Les galets ne tombent que lorsque le bac est bien visible, pour qu'on les voie tomber. */
  let bacVu = false;
  new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting && !bacVu) { bacVu = true; demarrer(); } }), { threshold: .45 }).observe(bac);
  function demarrer() {
    if (bacVu && !lance) {
      lance = true; creer();
      if (reduit) { for (let i = 0; i < 900; i++) pas(1 / 120); for (const g of galets) { g.vx = g.vy = g.va = 0; } dessiner(); return; }
    }
    reveiller();
  }
  addEventListener('resize', () => {
    if (!galets.length) return; mesurer();
    for (const g of galets) { g.x = Math.min(Math.max(g.r, g.x), W - g.r); g.y = Math.min(g.y, H - g.r); }
    if (reduit) { for (let i = 0; i < 400; i++) pas(1 / 120); dessiner(); } else reveiller();
  });
})();
