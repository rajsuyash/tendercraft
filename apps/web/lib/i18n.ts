/**
 * Interface strings, EN/FR.
 *
 * **This dictionary covers the interface and nothing else.** It never touches a tender's title,
 * a requirement, a clause, a citation or a source anchor — those are the legal document, shown
 * in the language the buyer published them in, and a translated requirement would be a claim
 * about a text that does not exist (docs/multi-market.md).
 *
 * So a French workspace read by an English-preferring reviewer legitimately shows English
 * chrome around French tender text. That is correct, not half-finished.
 *
 * No dependency: a Record and a lookup is the whole mechanism. `next-intl` and friends earn
 * their weight on plural rules and message formats across dozens of locales; two locales and a
 * flat key space do not need them.
 */

export type Locale = "en" | "fr";

export const LOCALES: Locale[] = ["en", "fr"];
export const DEFAULT_LOCALE: Locale = "en";

export function isLocale(value: string | undefined | null): value is Locale {
  return value === "en" || value === "fr";
}

/** Keys are English so a missing translation degrades to something readable rather than to a
 *  key name — an untranslated string is a cosmetic defect, a bare `nav.opportunities` is a bug
 *  the user has to interpret. */
const FR: Record<string, string> = {
  // ── navigation ─────────────────────────────────────────────
  Dashboard: "Tableau de bord",
  Opportunities: "Opportunités",
  Tenders: "Consultations",
  Proposals: "Propositions",
  "Knowledge Base": "Base documentaire",
  Learning: "Apprentissage",
  "Price history": "Historique des prix",
  "Vendor Profile": "Profil entreprise",
  Settings: "Paramètres",
  "User guide": "Guide d'utilisation",
  WORKSPACE: "ESPACE DE TRAVAIL",

  // ── opportunity feed ───────────────────────────────────────
  "Live public tenders on {portal}, deduplicated and matched against your rules and profile.":
    "Marchés publics en cours sur {portal}, dédoublonnés et rapprochés de vos règles et de votre profil.",
  Refresh: "Actualiser",
  "Check bid status": "Vérifier le statut des offres",
  "Check the evaluation stage of your watched bids on the portal":
    "Vérifier l'étape d'évaluation de vos offres suivies sur le portail",
  "No watched bids to check.": "Aucune offre suivie à vérifier.",
  "Could not check bid status.": "Impossible de vérifier le statut des offres.",
  "Stage only — a clarification or document request appears in your GeM seller account, which we do not access.":
    "Étape uniquement — une demande de clarification ou de document apparaît dans votre compte vendeur GeM, auquel nous n'accédons pas.",
  // The value interpolated into {portal}. A bare portal name ("TED") needs no entry and
  // degrades to the key; this one is a descriptive phrase, so it needs translating or it
  // leaks English into French chrome.
  "GeM and other Indian portals": "GeM et autres portails publics indiens",
  "Sweeping {portal}…": "Collecte {portal} en cours…",
  swept: "collecté le",
  "Swept from {portal}": "Avis collectés sur {portal}",
  "deduplicated by reference number": "dédoublonnés par numéro d'avis",
  "In your feed": "Dans votre flux",
  "no rules yet": "aucune règle définie",
  "rule applied": "règle appliquée",
  "rules applied": "règles appliquées",
  "Below the turnover bar": "Sous le seuil de CA",
  "needs your turnover on file": "renseignez votre chiffre d'affaires",
  "no tender in your feed states one": "aucun avis de votre flux n'en fixe",
  of: "sur",
  "that state one": "qui en fixent un",
  "against your": "face à votre",
  "Hidden by your rules": "Masqués par vos règles",
  "never by the system": "jamais par le système",
  "In scope": "Retenus",
  Excluded: "Écartés",
  "Only my keywords": "Uniquement mes mots-clés",
  // "clôturé" is already this dictionary's word for a passed deadline (see `closed` below),
  // so these follow it rather than introducing a second term for the same state.
  "Hide closed": "Masquer les clôturées",
  "Show closed tenders": "Afficher les consultations clôturées",
  "Every tender in this list has closed": "Toutes les consultations de cette liste sont clôturées",
  "All {n} matched tenders passed their deadline. Widen your capability keywords, or show them anyway.":
    "Les {n} consultations correspondantes ont dépassé leur date limite. Élargissez vos mots-clés, ou affichez-les malgré tout.",
  Sort: "Trier",
  "Best fit": "Pertinence",
  "Closing soonest": "Clôture la plus proche",
  "Turnover bar": "Seuil de CA",
  "Estimated value": "Montant estimé",

  // ── table ──────────────────────────────────────────────────
  Tender: "Consultation",
  Buyer: "Acheteur",
  Fit: "Pertinence",
  Closes: "Clôture",
  "Turnover required": "Seuil de CA",
  EMD: "Garantie",
  Deposit: "Garantie",
  "Excluded by": "Écarté par",
  "none stated": "non précisé",
  none: "aucune",
  "not published": "non publiée",
  today: "aujourd'hui",
  closed: "clôturé",
  day: "jour",
  days: "jours",
  "keyword match": "correspondance mots-clés",
  "Untitled tender": "Consultation sans intitulé",
  "Not published": "Non publié",

  // ── the one verdict chip still rendered ────────────────────
  "BELOW BAR": "SOUS LE SEUIL",

  // ── empty and error states ─────────────────────────────────
  "No opportunities yet": "Aucune opportunité pour le moment",
  "Nothing is hidden": "Aucun avis masqué",
  "Refresh to sweep {portal} for live tenders and match them against your rules and vendor profile.":
    "Actualisez pour collecter les avis {portal} en cours et les rapprocher de vos règles et de votre profil.",
  "Your rules have not excluded anything. Every tender we found is in the in-scope list.":
    "Vos règles n'ont écarté aucun avis. Tous les avis trouvés figurent dans la liste des retenus.",
  "The feed could not be loaded": "Le flux n'a pas pu être chargé",
  "Your rules and shortlist are unaffected — nothing has been excluded. Retry once the discovery service is reachable.":
    "Vos règles et votre sélection sont intactes — rien n'a été écarté. Réessayez lorsque le service de collecte sera de nouveau joignable.",

  // ── vendor profile ─────────────────────────────────────────
  "What you bid on": "Ce sur quoi vous candidatez",
  "Capability and expertise": "Compétences et domaines d'expertise",
  "Keywords you bid on": "Mots-clés de vos candidatures",
  "See your ranked feed →": "Voir votre flux classé →",
  "Not provided": "Non renseigné",
  "Update profile": "Mettre à jour le profil",
  "Update vendor profile": "Mettre à jour le profil entreprise",
  "Legal identity": "Identité juridique",
  Financials: "Données financières",
  Certifications: "Certifications",

  "Sweep {portal} now": "Lancer la collecte {portal}",
  Source: "Source",
  "Turnover and deposit figures are read from each notice by a deterministic parser; eligibility is provisional until the tender is fully analysed.":
    "Les seuils de chiffre d'affaires et les garanties sont extraits de chaque avis par un analyseur déterministe ; l'éligibilité reste provisoire tant que la consultation n'a pas été analysée dans son intégralité.",
  "Hidden by": "Masqués par",
  "Nothing here was hidden by the system — every row names the rule you wrote.":
    "Rien n'a été masqué par le système — chaque ligne nomme la règle que vous avez écrite.",

  "Not provided — without it your opportunity feed is ranked on keywords alone.":
    "Non renseigné — sans cela, votre flux d'opportunités est classé sur les seuls mots-clés.",
  // Past bids: language, not evidence — the phrasing must not imply they affect eligibility.
  "past bid": "candidature passée",
  "past bids": "candidatures passées",
  won: "remportée(s)",
  "house style measured": "style rédactionnel mesuré",
  "house style not measured yet": "style rédactionnel pas encore mesuré",
  "manage in the knowledge base": "gérer dans la base de connaissances",
  "No past bids uploaded — proposals will be drafted in a neutral voice.":
    "Aucune candidature passée déposée — les propositions seront rédigées dans un style neutre.",
  "Add one": "En ajouter une",

  Active: "Actif",
  complete: "complété",
  "item blocks": "élément empêche une",
  "items block": "éléments empêchent une",
  "accurate analysis": "analyse fiable",
  "Registered name": "Raison sociale",
  "Statutory identifiers for this market are not captured yet. Nothing here blocks your feed or your analyses.":
    "Les identifiants légaux de ce pays ne sont pas encore collectés. Cela ne bloque ni votre flux ni vos analyses.",
  "3-yr average turnover": "CA moyen sur 3 ans",
  Year: "Exercice",
  Turnover: "Chiffre d'affaires",
  "No financial years on file": "Aucun exercice enregistré",
  "Net worth": "Capitaux propres",
  "Working capital": "Fonds de roulement",
  "Experience records": "Références",
  Project: "Projet",
  Client: "Client",
  Value: "Montant",
  Tags: "Domaines",
  Completed: "Achevé le",
  "No experience records yet": "Aucune référence enregistrée",
  Expired: "Expirée",
  "Valid until": "Valable jusqu'au",
  "No expiry on file": "Aucune échéance enregistrée",
  "No certifications on file": "Aucune certification enregistrée",

  // ── dashboard ──────────────────────────────────────────────
  "Your active tenders and what needs attention.":
    "Vos consultations en cours et les points à traiter.",
  "Active tenders": "Consultations en cours",
  "Awaiting verification": "En attente de vérification",
  "Drafts in review": "Projets en relecture",
  "Analyses left": "Analyses restantes",
  Unlimited: "Illimitées",
  "Find opportunities": "Trouver des opportunités",
  "Live public tenders from {portal}, matched against your rules and profile":
    "Marchés publics en cours sur {portal}, rapprochés de vos règles et de votre profil",
  "Start a new bid": "Démarrer une candidature",
  "Upload the tender document and we'll extract the requirements":
    "Déposez le dossier de consultation et nous en extrairons les exigences",
  Deadlines: "Échéances",
  "No deadline set": "Aucune échéance définie",
  Closed: "Clôturé",
  "Due in": "Dans",
  Due: "Le",
  "No tenders yet": "Aucune consultation pour le moment",
  "Upload a tender package to get a verified criteria checklist the same afternoon.":
    "Déposez un dossier de consultation pour obtenir une grille de critères vérifiée dans la journée.",
  "Upload your first tender": "Déposer votre première consultation",

  // ── profile edit form ──────────────────────────────────────
  "Used to rank your opportunity feed. Nothing is hidden because of what you write here unless you switch on the narrow feed yourself.":
    "Sert à classer votre flux d'opportunités. Rien n'est masqué à cause de ce que vous écrivez ici, sauf si vous activez vous-même le flux restreint.",
  "Keywords you bid on (comma separated)":
    "Mots-clés de vos candidatures (séparés par des virgules)",
  "Registered company name": "Raison sociale",
  "As it appears on the certificate of incorporation":
    "Telle qu'elle figure sur l'extrait Kbis",
  "The registered name is written into the proposal directly. It is never taken from an uploaded document.":
    "La raison sociale est reprise telle quelle dans la proposition. Elle n'est jamais extraite d'un document déposé.",
  "Annual turnover": "Chiffre d'affaires annuel",
  "Turnover thresholds are checked against these figures.":
    "Les seuils de chiffre d'affaires sont vérifiés à partir de ces montants.",
  "Financial year": "Exercice",
  "Udyam registration": "Immatriculation Udyam",
  "An expired certificate fails its criterion and is excluded from retrieval — keep the validity date current.":
    "Une certification expirée échoue à son critère et est exclue de la recherche documentaire — tenez la date de validité à jour.",
  "Certification name": "Intitulé de la certification",
  "Past projects": "Références",
  "Similar-works criteria are matched against these, by scope and value.":
    "Les critères de prestations similaires sont rapprochés de ces références, par périmètre et par montant.",
  "Project name": "Intitulé du projet",
  "Completion date": "Date d'achèvement",
  Remove: "Supprimer",
  "Add a financial year": "Ajouter un exercice",
  "Add a certification": "Ajouter une certification",
  "Add a project": "Ajouter une référence",
  "Saving…": "Enregistrement…",
  "Save profile": "Enregistrer le profil",
  Cancel: "Annuler",
  "Re-match any open bid afterwards so its eligibility is recalculated.":
    "Relancez ensuite le rapprochement de vos candidatures en cours pour recalculer leur éligibilité.",
  "Could not save the profile": "Le profil n'a pas pu être enregistré",

  // ── watched markets ────────────────────────────────────────
  India: "Inde",
  "your chosen countries": "vos pays sélectionnés",
  // France: "France" needs no entry — identical in both, and a self-mapping key is noise.
  "Where you bid": "Où vous candidatez",
  "See your feed →": "Voir votre flux →",
  "Which countries' tenders appear in your opportunity list. Unticking one hides its tenders from you and nobody else — your workspace's currency and statutory fields follow where you are registered, not this choice.":
    "Les pays dont les avis apparaissent dans votre liste d'opportunités. Décocher un pays en masque les avis pour vous seul — la devise et les champs légaux de votre espace de travail suivent votre pays d'immatriculation, pas ce choix.",
  "registered here": "immatriculé ici",
  "Choose at least one country — an empty feed would look like no tenders.":
    "Choisissez au moins un pays — un flux vide donnerait l'impression qu'aucun avis n'est publié.",
  "Could not change which countries you watch.":
    "Impossible de modifier les pays suivis.",
  "Updating your feed…": "Mise à jour de votre flux…",
  "Save and re-match": "Enregistrer et relancer le rapprochement",

  // ── the feed emptied by your own rule ──────────────────────
  "Your rules hid every tender we found": "Vos règles ont masqué tous les avis trouvés",
  "tenders were swept and all of them were hidden by:":
    "avis ont été collectés et tous ont été masqués par :",
  "That rule keeps only tenders matching your capability keywords. If none match, check the keywords are single terms a tender title would actually contain — a whole sentence matches nothing.":
    "Cette règle ne conserve que les avis correspondant à vos mots-clés. Si aucun ne correspond, vérifiez que ce sont bien des termes simples qu'un intitulé d'avis peut contenir — une phrase entière ne correspond à rien.",
  "Show everything again": "Réafficher tous les avis",
  "Edit my keywords": "Modifier mes mots-clés",
  "See what was hidden": "Voir les avis masqués",
  "These are sentences rather than keywords and will match almost nothing — a term is matched whole against a tender's title:":
    "Ce sont des phrases et non des mots-clés : elles ne correspondront presque à rien, car chaque terme est comparé en entier à l'intitulé de l'avis :",

  // ── company, website, annual report, keyword suggestions ───
  "Your company": "Votre entreprise",
  Website: "Site web",
  "Annual report": "Rapport annuel",
  "Both are read only when you ask for keyword suggestions — never crawled on a schedule.":
    "Les deux ne sont lus que lorsque vous demandez des suggestions de mots-clés — jamais explorés automatiquement.",
  "Annual report on file": "Rapport annuel enregistré",
  "in your knowledge base": "dans votre base documentaire",
  "Stored in your knowledge base with your other evidence. It is also read when you ask for keyword suggestions — an annual report names what you sell in the words the market uses.":
    "Conservé dans votre base documentaire avec vos autres pièces. Il est également lu lorsque vous demandez des suggestions de mots-clés — un rapport annuel nomme ce que vous vendez dans les termes employés par le marché.",
  "Reading the document…": "Lecture du document…",
  "Could not read that file.": "Ce fichier n'a pas pu être lu.",
  "This file still contains template placeholders":
    "Ce fichier contient encore des champs de modèle non remplis",
  "Suggest keywords from my profile": "Proposer des mots-clés à partir de mon profil",
  "Reading your profile…": "Lecture de votre profil…",
  "Could not read your profile for suggestions.":
    "Impossible de lire votre profil pour établir des suggestions.",
  Read: "Sources lues",
  "your capability statement": "votre descriptif de compétences",
  "existing keywords": "mots-clés existants",
  "your website": "votre site web",
  "your annual report": "votre rapport annuel",
  "could not read the website": "site web illisible",
  "suggestions came from splitting your existing terms only — the model was unavailable":
    "suggestions issues du seul découpage de vos termes existants — le modèle était indisponible",
  "Nothing to suggest — add a capability statement or a website first.":
    "Rien à proposer — renseignez d'abord un descriptif de compétences ou un site web.",

  "Filled in from your website — edit or delete any of them in the box above before saving.":
    "Renseignés à partir de votre site web — modifiez ou supprimez-en dans le champ ci-dessus avant d'enregistrer.",
  "Add all": "Tout ajouter",

  // ── routing (M12) ──────────────────────────────────────────
  Owner: "Responsable",
  Unassigned: "Non attribué",
  "Former member": "Ancien membre",
  "Watch this tender": "Suivre cette consultation",
  "Stop watching": "Ne plus suivre",
  "Could not route this tender. Nothing was changed.":
    "Impossible d'attribuer cette consultation. Rien n'a été modifié.",

  // ── provenance footer ──────────────────────────────────────
  "Tender content stays on the source portal and is linked, not reproduced.":
    "Le contenu des avis reste sur le portail source : il est lié, jamais reproduit.",
};

const DICTIONARIES: Record<Locale, Record<string, string>> = { en: {}, fr: FR };

/**
 * `t("Refresh")` → "Actualiser" in fr, "Refresh" in en.
 *
 * An untranslated key falls through to the English it already is. That is deliberate: a
 * half-translated screen is a cosmetic problem, whereas a screen full of dotted key paths is
 * unusable — and in a compliance product an unreadable label is worse than an English one.
 */
export function translator(locale: Locale) {
  const dictionary = DICTIONARIES[locale] ?? {};
  return (key: string): string => dictionary[key] ?? key;
}
