/* MERCI landing v4 socle : données de démonstration fictives (charte : jamais de logo d'organisme réel sans partenariat). */
window.MERCI = (function () {
  const CAUSES = {
    solidarite: { nom: 'Solidarité', picto: 'picto-solidarite' },
    education: { nom: 'Éducation', picto: 'picto-education' },
    sante: { nom: 'Santé et recherche', picto: 'picto-sante-et-recherche' },
    urgences: { nom: 'Urgences humanitaires', picto: 'picto-urgences-humanitaires' },
    climat: { nom: 'Climat et environnement', picto: 'picto-climat-et-environnement' },
    animaux: { nom: 'Animaux et biodiversité', picto: 'picto-animaux-et-biodiversite' },
    technologie: { nom: 'Technologie', picto: 'picto-technologie' },
    culture: { nom: 'Culture, sport et lien social', picto: 'picto-culture-sport-lien-social' }
  };

  // taux : 75 % aide aux personnes en difficulté, sinon 66 %
  const ASSOS = [
    { id: 'panier', nom: 'Le Panier Solidaire', cause: 'solidarite', quartier: 'Neudorf', taux: 75,
      accroche: 'Des repas chauds et une épicerie à petits prix pour les familles du quartier.',
      description: "L'association tient une épicerie solidaire et sert des repas le dimanche. Les bénévoles accompagnent aussi les familles dans leurs démarches.",
      impact: { 5: 'un repas chaud servi le dimanche', 10: 'deux repas chauds partagés', 20: 'le panier de la semaine pour une famille', 50: "une semaine d'épicerie pour trois familles" },
      projets: [{ nom: 'Repas du dimanche', etape: 2, jalons: ['Collecte', 'Achats', 'Cuisine', 'Repas servis'] }, { nom: "Agrandir l'épicerie", etape: 1, jalons: ['Local trouvé', 'Travaux', 'Équipement', 'Ouverture'] }] },
    { id: 'ecole', nom: 'École Saint Jean', cause: 'education', quartier: 'Hautepierre', taux: 66,
      accroche: 'Du soutien scolaire et des fournitures pour chaque enfant.',
      description: "Une équipe d'enseignants retraités et d'étudiants aide les élèves après la classe. À la rentrée, chaque enfant repart avec un cartable complet.",
      impact: { 5: 'un cahier et des crayons pour la rentrée', 10: "une heure de soutien scolaire", 20: 'un cartable complet pour un élève', 50: "un mois d'aide aux devoirs pour un enfant" },
      projets: [{ nom: 'Fournitures scolaires', etape: 3, jalons: ['Collecte', 'Achats', 'Distribution', 'Rentrée'] }, { nom: "Atelier lecture du mercredi", etape: 1, jalons: ['Bénévoles', 'Livres', 'Ateliers', 'Bilan'] }] },
    { id: 'recherche', nom: 'Fondation Recherche Rare', cause: 'sante', quartier: 'Hôpital civil', taux: 66,
      accroche: 'Faire avancer la recherche sur les maladies rares, et accompagner les familles.',
      description: "La fondation finance des bourses pour de jeunes chercheurs strasbourgeois et organise l'accueil des familles venues pour les soins.",
      impact: { 5: "une nuit d'accueil pour un parent", 10: 'des réactifs pour une expérience', 20: "une journée d'analyses au laboratoire", 50: "une semaine d'hébergement pour une famille" },
      projets: [{ nom: 'Bourse jeune chercheur', etape: 2, jalons: ['Appel', 'Sélection', 'Recherche', 'Publication'] }, { nom: 'Maison des familles', etape: 1, jalons: ['Étude', 'Financement', 'Travaux', 'Accueil'] }] },
    { id: 'relais', nom: 'Relais Urgence Rhin', cause: 'urgences', quartier: 'Port du Rhin', taux: 75,
      accroche: "Des kits d'hygiène et un toit pour les nuits d'hiver.",
      description: "Les maraudes du Relais vont à la rencontre des personnes à la rue chaque soir. L'hiver, l'association ouvre un accueil de nuit.",
      impact: { 5: "un kit d'hygiène", 10: 'un duvet pour une nuit dehors', 20: "une nuit à l'abri avec un repas", 50: 'une semaine de maraudes équipées' },
      projets: [{ nom: "Accueil de nuit d'hiver", etape: 1, jalons: ['Local', 'Bénévoles', 'Ouverture', 'Bilan'] }, { nom: 'Kits hygiène', etape: 3, jalons: ['Collecte', 'Tri', 'Distribution', 'Bilan'] }] },
    { id: 'forets', nom: 'Forêts de demain', cause: 'climat', quartier: 'Robertsau', taux: 66,
      accroche: 'Planter des haies et des arbres avec les habitants.',
      description: "Chaque saison, les habitants plantent des haies et des arbres fruitiers dans les écoles et les jardins partagés de la ville.",
      impact: { 5: 'un plant de haie champêtre', 10: 'un arbre fruitier planté', 20: "deux mètres de haie avec les écoliers", 50: "un verger d'école démarré" },
      projets: [{ nom: 'Haies des écoles', etape: 2, jalons: ['Repérage', 'Plants', 'Plantation', 'Suivi'] }, { nom: 'Jardin partagé du Wacken', etape: 3, jalons: ['Terrain', 'Aménagement', 'Plantation', 'Ouverture'] }] },
    { id: 'refuge', nom: 'Refuge des Collines', cause: 'animaux', quartier: 'Cronenbourg', taux: 66,
      accroche: 'Recueillir, soigner et faire adopter les animaux abandonnés.',
      description: "Le refuge accueille chiens et chats abandonnés, les soigne avec un vétérinaire partenaire et leur cherche une famille.",
      impact: { 5: 'une semaine de croquettes pour un chat', 10: 'un vaccin pour un chiot', 20: 'une consultation vétérinaire', 50: "la stérilisation d'une chatte" },
      projets: [{ nom: 'Nouvel enclos chiens', etape: 1, jalons: ['Plans', 'Financement', 'Construction', 'Ouverture'] }, { nom: "Campagne d'adoption", etape: 3, jalons: ['Photos', 'Annonces', 'Rencontres', 'Adoptions'] }] },
    { id: 'clic', nom: 'Clic Solidaire', cause: 'technologie', quartier: 'Esplanade', taux: 66,
      accroche: 'Réparer des ordinateurs et apprendre le numérique à tout âge.',
      description: "L'atelier reconditionne des ordinateurs donnés par les entreprises et propose des cours pour faire ses démarches en ligne.",
      impact: { 5: "une heure d'atelier numérique", 10: 'un clavier et une souris reconditionnés', 20: 'un cours complet de démarches en ligne', 50: 'un ordinateur reconditionné pour un lycéen' },
      projets: [{ nom: 'Ordinateurs pour lycéens', etape: 2, jalons: ['Collecte', 'Réparation', 'Remise', 'Suivi'] }, { nom: 'Ateliers seniors', etape: 1, jalons: ['Inscriptions', 'Ateliers', 'Bilan', 'Suite'] }] },
    { id: 'terrain', nom: 'Terrain Commun', cause: 'culture', quartier: 'Meinau', taux: 66,
      accroche: 'Du sport et des sorties pour que les voisins se rencontrent.',
      description: "Le club propose du football mixte, des sorties culturelles et une fête de quartier chaque été, ouverts à tous.",
      impact: { 5: 'une place de musée pour un jeune', 10: 'un ballon pour le club', 20: "une licence sportive d'un mois", 50: "un car pour la sortie d'été" },
      projets: [{ nom: 'Fête du quartier', etape: 2, jalons: ['Idées', 'Préparation', 'Fête', 'Merci'] }, { nom: 'Équipe féminine', etape: 1, jalons: ['Inscriptions', 'Entraînements', 'Matchs', 'Saison'] }] }
  ];
  return { CAUSES, ASSOS };
})();
