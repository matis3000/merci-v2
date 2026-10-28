/* Données d'exemple pour la preview uniquement. Personnes, entreprises et associations fictives. */
window.CRM = {
  aujourdhui: "lundi 9 novembre",
  piloteOuvert: "2 novembre",

  pipelines: {
    donateurs: { nom: "Donateurs", etapes: ["Inscrit", "Bienvenue envoyée", "Pilote ouvert", "Compte créé", "Premier don", "Fidèle"] },
    entreprises: { nom: "Entreprises", etapes: ["Prospect", "Contacté", "A répondu", "Démo planifiée", "Démo faite", "Abonnement signé", "Salariés activés"] },
    associations: { nom: "Associations", etapes: ["Inscrite", "Contactée", "Partenaire"] }
  },

  /* parcours client : 6 étapes de la spec, compteurs = somme des affaires */
  parcours: [
    { cle: "attirer", nom: "Attirer", d: 0, e: 0, info: "Visites de la landing" },
    { cle: "capturer", nom: "Capturer", d: 3, e: 9, info: "Inscrits et prospects" },
    { cle: "suivre", nom: "Suivre", d: 4, e: 6, info: "Bienvenue, contactés" },
    { cle: "relancer", nom: "Relancer", d: 5, e: 4, info: "Séquences actives" },
    { cle: "convertir", nom: "Convertir", d: 3, e: 2, info: "Compte créé, démo, signé" },
    { cle: "fideliser", nom: "Fidéliser", d: 1, e: 1, info: "Fidèles, salariés activés" }
  ],

  contacts: [
    { id: 1, prenom: "Camille", nom: "Roth", type: "donateur", email: "camille.roth@exemple.fr", source: "Landing", detail: "Instagram", pipeline: "donateurs", etape: "Inscrit", seq: { nom: "Bienvenue donateur", pas: 1, total: 1, etat: "due", quand: "à 10 h 15" }, act: "Inscrite il y a 12 min", ville: "Strasbourg" },
    { id: 2, prenom: "Hugo", nom: "Schmitt", type: "donateur", email: "hugo.schmitt@exemple.fr", source: "Landing", detail: "TikTok", pipeline: "donateurs", etape: "Inscrit", seq: { nom: "Bienvenue donateur", pas: 1, total: 1, etat: "due", quand: "à 10 h 15" }, act: "Inscrit il y a 40 min", ville: "Schiltigheim" },
    { id: 3, prenom: "Léa", nom: "Muller", type: "donateur", email: "lea.muller@exemple.fr", source: "Landing", detail: "Bouche à oreille", pipeline: "donateurs", etape: "Pilote ouvert", seq: { nom: "Ouverture du pilote", pas: 2, total: 3, etat: "active", quand: "jeudi" }, act: "Rappel ouvert hier", ville: "Strasbourg" },
    { id: 4, prenom: "Inès", nom: "Meyer", type: "donateur", email: "ines.meyer@exemple.fr", source: "Landing", detail: "Instagram", pipeline: "donateurs", etape: "Pilote ouvert", seq: { nom: "Ouverture du pilote", pas: 1, total: 3, etat: "pause", quand: "en pause" }, act: "Mise en pause par Valentin", ville: "Illkirch" },
    { id: 5, prenom: "Thomas", nom: "Klein", type: "donateur", email: "thomas.klein@exemple.fr", source: "Landing", detail: "Association", pipeline: "donateurs", etape: "Compte créé", seq: null, act: "Compte créé samedi", ville: "Strasbourg" },
    { id: 6, prenom: "Sarah", nom: "Weber", type: "donateur", email: "sarah.weber@exemple.fr", source: "Landing", detail: "Snapchat", pipeline: "donateurs", etape: "Premier don", seq: null, act: "Premier don hier", ville: "Lingolsheim" },
    { id: 7, prenom: "Nathan", nom: "Fischer", type: "donateur", email: "nathan.fischer@exemple.fr", source: "Landing", detail: "YouTube", pipeline: "donateurs", etape: "Bienvenue envoyée", seq: { nom: "Bienvenue donateur", pas: 1, total: 1, etat: "fini", quand: "" }, act: "Bienvenue ouverte", ville: "Strasbourg" },
    { id: 8, prenom: "Chloé", nom: "Wagner", type: "donateur", email: "chloe.wagner@exemple.fr", source: "Landing", detail: "Partenaire", pipeline: "donateurs", etape: "Fidèle", seq: null, act: "Deuxième don vendredi", ville: "Strasbourg" },
    { id: 9, prenom: "Louis", nom: "Hoffmann", type: "donateur", email: "louis.hoffmann@exemple.fr", source: "Landing", detail: "Instagram", pipeline: "donateurs", etape: "Pilote ouvert", seq: { nom: "Ouverture du pilote", pas: 3, total: 3, etat: "echec", quand: "rebond" }, act: "Adresse en rebond", ville: "Haguenau" },

    { id: 20, prenom: "Julie", nom: "Bauer", type: "entreprise", poste: "Responsable RSE", org: "Solvia Assurances Est", effectif: "420 salariés", email: "", source: "Prospection", detail: "Registre + LinkedIn", pipeline: "entreprises", etape: "A répondu", note: 10, raisons: ["Décideur RSE trouvé +4", "250 salariés et plus +3", "Post RSE il y a 12 jours +3"], seq: { nom: "Prospection LinkedIn", pas: 2, total: 4, etat: "arret", quand: "réponse reçue" }, act: "A répondu sur LinkedIn il y a 1 h", ville: "Strasbourg", afaire: "Planifier la démo" },
    { id: 21, prenom: "Marc", nom: "Lehmann", type: "entreprise", poste: "DRH", org: "Kronenfeld Logistique", effectif: "310 salariés", email: "", source: "Prospection", detail: "Registre + LinkedIn", pipeline: "entreprises", etape: "Contacté", note: 7, raisons: ["Décideur RH trouvé +4", "250 salariés et plus +3"], seq: { nom: "Prospection LinkedIn", pas: 1, total: 4, etat: "active", quand: "attend l'acceptation" }, act: "Invitation envoyée jeudi", ville: "Hoerdt" },
    { id: 22, prenom: "Anaïs", nom: "Kieffer", type: "entreprise", poste: "Chargée QVT", org: "Méridia Santé", effectif: "180 salariés", email: "a.kieffer@meridia-exemple.fr", source: "Landing", detail: "Case entreprise cochée", pipeline: "entreprises", etape: "Démo planifiée", note: 9, raisons: ["Décideur QVT +4", "50 à 249 salariés +2", "Offre d'emploi QVT ce mois +3"], seq: null, act: "Démo jeudi 12 novembre, 14 h", ville: "Strasbourg", afaire: "Préparer la démo de jeudi" },
    { id: 23, prenom: "Pierre", nom: "Ott", type: "entreprise", poste: "Directeur RH", org: "Batiplus Alsace", effectif: "95 salariés", email: "", source: "Prospection", detail: "Registre + LinkedIn", pipeline: "entreprises", etape: "Prospect", note: 6, raisons: ["Décideur RH trouvé +4", "50 à 249 salariés +2"], seq: { nom: "Prospection LinkedIn", pas: 1, total: 4, etat: "due", quand: "demain 9 h" }, act: "Trouvé ce matin", ville: "Molsheim" },
    { id: 24, prenom: "Nora", nom: "Haas", type: "entreprise", poste: "People & Culture", org: "Cité Numérique 67", effectif: "64 salariés", email: "", source: "Prospection", detail: "Registre + LinkedIn", pipeline: "entreprises", etape: "Prospect", note: 6, raisons: ["Décideur People trouvé +4", "50 à 249 salariés +2"], seq: { nom: "Prospection LinkedIn", pas: 1, total: 4, etat: "due", quand: "demain 9 h" }, act: "Trouvé ce matin", ville: "Strasbourg" },
    { id: 25, prenom: "", nom: "", type: "entreprise", poste: "", org: "Ill & Rhin Transports", effectif: "140 salariés", email: "", source: "Prospection", detail: "Registre seul", pipeline: "entreprises", etape: "Prospect", note: 2, raisons: ["Aucun décideur RH ou RSE trouvé", "50 à 249 salariés +2"], seq: null, act: "Sans décideur, à traiter à la main", ville: "Strasbourg" },
    { id: 26, prenom: "Claire", nom: "Burger", type: "entreprise", poste: "DRH", org: "Groupe Vosgia", effectif: "1 200 salariés", email: "c.burger@vosgia-exemple.fr", source: "Landing", detail: "Case entreprise cochée", pipeline: "entreprises", etape: "Abonnement signé", note: 10, raisons: ["Décideur RH +4", "250 salariés et plus +3", "Post RSE il y a 3 jours +3"], seq: null, act: "Abonnement signé mardi", ville: "Strasbourg", afaire: "Envoyer le lien d'invitation des salariés" },
    { id: 27, prenom: "Yann", nom: "Gross", type: "entreprise", poste: "Responsable RSE", org: "Atelier Rhénan", effectif: "72 salariés", email: "", source: "Prospection", detail: "Registre + LinkedIn", pipeline: "entreprises", etape: "Contacté", note: 9, raisons: ["Décideur RSE +4", "50 à 249 salariés +2", "Post RSE il y a 20 jours +3"], seq: { nom: "Prospection LinkedIn", pas: 3, total: 4, etat: "active", quand: "mercredi" }, act: "Message LinkedIn envoyé vendredi", ville: "Sélestat" },
    { id: 28, prenom: "Sophie", nom: "Marx", type: "entreprise", poste: "DRH", org: "Rhenus Conseil", effectif: "260 salariés", email: "s.marx@rhenus-exemple.fr", source: "Landing", detail: "Case entreprise cochée", pipeline: "entreprises", etape: "Démo faite", note: 7, raisons: ["Décideur RH +4", "250 salariés et plus +3"], seq: null, act: "Démo faite vendredi", ville: "Strasbourg", afaire: "Relancer pour la signature" },
    { id: 29, prenom: "Éric", nom: "Wolff", type: "entreprise", poste: "DRH", org: "Kehl Hôtellerie Est", effectif: "1 050 salariés", email: "e.wolff@khe-exemple.fr", source: "Landing", detail: "Case entreprise cochée", pipeline: "entreprises", etape: "Salariés activés", note: 10, raisons: ["Décideur RH +4", "250 salariés et plus +3", "Offre d'emploi RSE +3"], seq: null, act: "212 salariés ont activé leur compte", ville: "Strasbourg" },

    { id: 40, prenom: "Martine", nom: "Gerber", type: "association", org: "Les Jardins du Neudorf", email: "contact@jardins-exemple.fr", source: "Landing", detail: "Profil association", pipeline: "associations", etape: "Inscrite", seq: null, act: "Inscrite hier", ville: "Strasbourg", afaire: "Appeler l'association" },
    { id: 41, prenom: "Karim", nom: "Benali", type: "association", org: "Cartable Solidaire 67", email: "bonjour@cartable-exemple.fr", source: "Landing", detail: "Profil association", pipeline: "associations", etape: "Partenaire", seq: null, act: "Partenaire depuis le 20 octobre", ville: "Strasbourg" }
  ],

  fil: [
    { t: "Il y a 1 h", c: "linkedin", titre: "Réponse reçue sur LinkedIn", texte: "« Bonjour, le sujet nous intéresse pour notre plan RSE 2027. Jeudi après-midi, ça vous irait ? »", fort: true },
    { t: "Il y a 1 h", c: "systeme", titre: "Séquence arrêtée automatiquement", texte: "Raison : réponse reçue. Étape passée de Contacté à A répondu." },
    { t: "Mercredi 4 nov., 9 h 40", c: "linkedin", titre: "Message LinkedIn envoyé", texte: "Pas 2 de Prospection LinkedIn. « Merci pour l'acceptation, Julie. MERCI permet à vos salariés de donner et de suivre leurs dons… »" },
    { t: "Mardi 3 nov., 16 h 12", c: "linkedin", titre: "Invitation acceptée", texte: "" },
    { t: "Lundi 2 nov., 9 h 05", c: "linkedin", titre: "Invitation LinkedIn envoyée", texte: "Pas 1, avec une note de 212 caractères." },
    { t: "Lundi 2 nov., 6 h 02", c: "systeme", titre: "Trouvée par la prospection", texte: "Registre des entreprises (Bas-Rhin, 420 salariés), puis profil LinkedIn « Responsable RSE ». Note 10/10." }
  ],

  sequences: [
    { cle: "bienvenue", nom: "Bienvenue donateur", public: "Donateurs", declencheur: "Inscription sur la landing", actifs: 2, envoyes: 31, ouverts: 24, reponses: 0,
      pas: [{ j: "J0", canal: "email", titre: "Bienvenue chez MERCI", apercu: "Merci {prénom} ! Vous êtes inscrit au pilote de Strasbourg. On vous écrit dès l'ouverture." }] },
    { cle: "pilote", nom: "Ouverture du pilote", public: "Donateurs", declencheur: "Bouton « Ouvrir le pilote »", actifs: 3, envoyes: 58, ouverts: 41, reponses: 2,
      pas: [
        { j: "J0", canal: "email", titre: "Le pilote est ouvert", apercu: "{prénom}, votre compte MERCI vous attend. Créez-le en deux minutes et retrouvez tous vos dons au même endroit." },
        { j: "J+4", canal: "email", titre: "Votre compte vous attend", apercu: "Petit rappel : un seul compte pour donner, suivre vos dons et garder vos reçus." },
        { j: "J+10", canal: "email", titre: "Dernier rappel", apercu: "On ne vous écrira plus à ce sujet. Le lien reste valable." }] },
    { cle: "entrante", nom: "Entreprise entrante", public: "Entreprises", declencheur: "Case « entreprise » cochée", actifs: 0, envoyes: 9, ouverts: 8, reponses: 4,
      pas: [
        { j: "J0", canal: "email", titre: "Votre demande pour vos salariés", apercu: "Bonjour {prénom}, merci pour votre intérêt. Choisissez un créneau de 20 minutes pour une démo." },
        { j: "J+3", canal: "email", titre: "Un créneau cette semaine ?", apercu: "Je me permets de revenir vers vous au sujet de MERCI pour {entreprise}." },
        { j: "J+7", canal: "linkedin", titre: "Invitation LinkedIn", apercu: "Si le profil LinkedIn est connu." }] },
    { cle: "prospection", nom: "Prospection LinkedIn", public: "Entreprises", declencheur: "Prospect noté 6/10 ou plus", actifs: 4, envoyes: 46, ouverts: null, reponses: 5,
      pas: [
        { j: "J0", canal: "linkedin", titre: "Invitation avec note", apercu: "Bonjour {prénom}, je travaille sur le don en entreprise à Strasbourg, au plus près des associations locales. Ravi d'échanger." },
        { j: "Acceptée", canal: "linkedin", titre: "Message de présentation", apercu: "Merci pour l'acceptation, {prénom}. MERCI permet à vos salariés de donner et de suivre leurs dons…" },
        { j: "+4 j", canal: "linkedin", titre: "Relance", apercu: "Je reviens vers vous : une démo de 20 minutes la semaine prochaine ?" },
        { j: "+9 j", canal: "email", titre: "Relance par e-mail", apercu: "Si l'adresse est connue." }] }
  ],

  prospection: {
    cible: { zone: "Bas-Rhin (67)", effectif: "50 salariés et plus", postes: ["DRH", "RH", "RSE", "QVT", "People"], plafond: 20 },
    dernier: { quand: "Ce matin, 6 h", entreprises: 38, nouvelles: 6, decideurs: 4, enSequence: 2 },
    entreprises: [
      { nom: "Batiplus Alsace", ville: "Molsheim", effectif: "95", naf: "Construction", decideur: "Pierre Ott, Directeur RH", note: 6, suite: "Invitation demain 9 h" },
      { nom: "Cité Numérique 67", ville: "Strasbourg", effectif: "64", naf: "Services numériques", decideur: "Nora Haas, People & Culture", note: 6, suite: "Invitation demain 9 h" },
      { nom: "Ill & Rhin Transports", ville: "Strasbourg", effectif: "140", naf: "Transport routier", decideur: "", note: 2, suite: "À traiter à la main" },
      { nom: "Brasserie du Port Sud", ville: "Strasbourg", effectif: "58", naf: "Restauration", decideur: "", note: 2, suite: "À traiter à la main" },
      { nom: "Optima Laboratoires", ville: "Illkirch", effectif: "230", naf: "Recherche", decideur: "Élise Faure, Responsable RH", note: 6, suite: "File d'attente (plafond du jour)" },
      { nom: "Vitrail Est Industrie", ville: "Haguenau", effectif: "310", naf: "Industrie", decideur: "Hélène Roos, DRH", note: 7, suite: "File d'attente (plafond du jour)" }
    ]
  },

  equipe: [
    { prenom: "Valentin", role: "Admin", email: "valentin@merci-exemple.fr" },
    { prenom: "Romain", role: "Équipe", email: "romain@merci-exemple.fr" },
    { prenom: "Aïcha", role: "Équipe", email: "aicha@merci-exemple.fr" }
  ]
};
