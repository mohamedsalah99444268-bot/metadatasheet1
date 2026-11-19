import type { Lang } from "./i18n";
const CAT_FR: Record<string,string> = { electrical: "Électrique", thermal: "Thermique", mechanical: "Mécanique", timing: "Temporisation", interface: "Interface", memory: "Mémoire", identity: "Identité", other: "Autre" };
function frCats(s: string): string { return s.replace(/([a-z_]+)=(\d+)/g, (_, k: string, n: string) => `${CAT_FR[k] ?? k}\u00a0${n}`).replace(/,\s*/g, " · "); }

type Rule = [RegExp, (m: RegExpMatchArray) => string];

/** Known backend agent/event messages → French. Unknown messages are returned unchanged. */
const FR: Rule[] = [
  [/^Research phase entered\.?$/i, () => "Phase de recherche démarrée."],
  [/^Download phase entered\.?$/i, () => "Phase de téléchargement démarrée."],
  [/^Conflict review queued\.?$/i, () => "Revue des conflits planifiée."],
  [/^Using existing uploaded datasheet; no datasheet URL was generated\.?$/i, () => "Fiche technique importée utilisée ; aucune URL générée."],
  [/^Using caller-supplied verified datasheet URL\.?$/i, () => "URL de fiche technique vérifiée fournie utilisée."],
  [/^Existing uploaded PDF selected; no new file was downloaded\.?$/i, () => "PDF importé sélectionné ; aucun nouveau téléchargement."],
  [/^Extracted (\d+) evidence-linked field\(s\)\.?$/i, (m) => `${m[1]} champ(s) extrait(s) avec preuve.`],
  [/^Classified (\d+) spec\(s\): (.*?)\.(?: Local model relabelled (\d+) uncategorised spec\(s\)\.)?$/i, (m) => `${m[1]} spécification(s) classée(s) : ${frCats(m[2])}.${m[3] ? ` Le modèle local a reclassé ${m[3]} spécification(s) non catégorisée(s).` : ""}`],
  [/^Validation produced (\d+) result\(s\) \((\d+) evidence\/range check\(s\) flagged\)\.?$/i, (m) => `Validation : ${m[1]} résultat(s), ${m[2]} contrôle(s) de preuve ou de plage signalé(s).`],
  [/^Structured report generated from workflow state\.?$/i, () => "Rapport structuré généré."],
  [/^Indexed (\d+) chunk\(s\)\.?$/i, (m) => `${m[1]} passage(s) indexé(s).`],
  [/^Missing information recorded for review\.?$/i, () => "Informations manquantes enregistrées pour revue."],
  [/^No expected parameter is missing\.?$/i, () => "Aucun paramètre attendu ne manque."],
  [/^No specification was extracted\.?$/i, () => "Aucune spécification extraite."],
  [/^Download skipped because no datasheet was found\.?$/i, () => "Téléchargement ignoré : aucune fiche technique trouvée."],
  [/^Extraction skipped because no uploaded PDF is available\.?$/i, () => "Extraction ignorée : aucun PDF disponible."],
  [/^Deterministic extraction failed for the uploaded PDF\.?$/i, () => "L’extraction déterministe a échoué pour ce PDF."],
  [/^Local model extraction failed; deterministic fields were retained\.?$/i, () => "L’extraction par IA locale a échoué ; les champs déterministes sont conservés."],
  [/^Official datasheet downloaded and verified\.?$/i, () => "Fiche technique officielle téléchargée et vérifiée."],
  [/^Official datasheet was already downloaded\.?$/i, () => "Fiche technique officielle déjà téléchargée."],
  [/^No official datasheet was found for this manufacturer and part number\.?$/i, () => "Aucune fiche technique officielle trouvée pour ce fabricant et cette référence."],
  [/^No official datasheet candidate could be downloaded\.?$/i, () => "Aucune fiche technique candidate n’a pu être téléchargée."],
  [/^The official datasheet could not be downloaded\.?$/i, () => "La fiche technique officielle n’a pas pu être téléchargée."],
  [/^The official datasheet exceeds the local download size limit\.?$/i, () => "La fiche technique dépasse la taille de téléchargement autorisée."],
  [/^The official source did not expose a verified PDF download link\.?$/i, () => "La source officielle ne propose pas de lien PDF vérifié."],
  [/^No datasheet source was provided\.?$/i, () => "Aucune source de fiche technique fournie."],
  [/^No download source is available\.?$/i, () => "Aucune source de téléchargement disponible."],
  [/^No stored document available for RAG indexing\.?$/i, () => "Aucun document stocké à indexer."],
  [/^RAG indexing failed\.?$/i, () => "L’indexation a échoué."],
  [/^The local AI health check failed\.?$/i, () => "Le contrôle de l’IA locale a échoué."],
  [/^The local model returned an invalid or incomplete response\.?$/i, () => "L’IA locale a renvoyé une réponse invalide ou incomplète."],
  [/^Found (\d+) official datasheet candidate\(s\); best source: (.+?)\.?$/i, (m) => `${m[1]} fiche(s) candidate(s) trouvée(s) ; meilleure source : ${m[2]}.`],
  [/^Datasheet not found; provide a verified URL or upload a PDF\.?$/i, () => "Fiche technique introuvable : fournissez une URL vérifiée ou importez un PDF."],
  [/^Official datasheet matched an existing document\.?$/i, () => "La fiche technique officielle correspond à un document existant."],
  [/^Ollama is unavailable; deterministic-only workflow selected\.?$/i, () => "IA locale indisponible : traitement déterministe uniquement."],
  [/^Ollama is available and the required local model is installed\.?$/i, () => "L’IA locale est disponible et le modèle requis est installé."],
  [/^Validation conflicts require review before reporting\.?$/i, () => "Des conflits de validation doivent être revus avant le rapport."],
  [/^Workflow stopped before a report could be completed\.?$/i, () => "Le traitement s’est arrêté avant la fin du rapport."],
  [/^The selected document record no longer points to a readable PDF\.?$/i, () => "Le document sélectionné ne pointe plus vers un PDF lisible."],
  [/^The uploaded PDF could not be parsed by the deterministic extraction stack\.?$/i, () => "Le PDF importé n’a pas pu être analysé par l’extraction déterministe."],
  [/^Rejected (\d+) model candidate\(s\) without exact source evidence\.?$/i, (m) => `${m[1]} proposition(s) du modèle rejetée(s) faute de preuve exacte.`],
  [/^Every number of the extracted value must appear in its source evidence\.?$/i, () => "Chaque nombre extrait doit figurer dans sa preuve source."],
  [/^A database session is required to download and record datasheet sources\.?$/i, () => "Une session de base de données est requise pour télécharger et enregistrer les sources."],
  [/^Could not claim an analysis job$/i, () => "Impossible de réserver une tâche d’analyse."],
  [/^Could not persist agent run$/i, () => "Impossible d’enregistrer l’exécution de l’agent."],
  [/^Could not persist components for job (.+)$/i, (m) => `Impossible d’enregistrer les composants de la tâche ${m[1]}.`],
  [/^Could not process analysis job (.+)$/i, (m) => `Impossible de traiter la tâche d’analyse ${m[1]}.`],
  [/^DB job state lookup failed$/i, () => "Lecture de l’état de la tâche impossible."],
  [/^Deterministic extraction failed for document (.+)$/i, (m) => `L’extraction déterministe a échoué pour le document ${m[1]}.`],
  [/^Local model extraction failed for document (.+)$/i, (m) => `L’extraction par IA locale a échoué pour le document ${m[1]}.`],
  [/^Local datasheet URLs are not allowed\.?$/i, () => "Les URL locales de fiches techniques ne sont pas autorisées."],
  [/^No official datasheet source is configured for this manufacturer\.?$/i, () => "Aucune source officielle n’est configurée pour ce fabricant."],
  [/^Official datasheet attempt failed for (.+?): (.+)$/i, (m) => `Tentative de fiche officielle échouée pour ${m[1]} : ${m[2]}`],
  [/^Official datasheet download failed for (.+?): (.+)$/i, (m) => `Téléchargement de la fiche officielle échoué pour ${m[1]} : ${m[2]}`],
  [/^Official datasheet search failed: (.+)$/i, (m) => `Recherche de fiche officielle échouée : ${m[1]}`],
  [/^Official datasheet search is unavailable right now\.?$/i, () => "La recherche de fiches officielles est indisponible pour le moment."],
  [/^Ollama classification refinement skipped: (.+)$/i, (m) => `Affinage de la classification par IA locale ignoré : ${m[1]}`],
  [/^Only public HTTPS datasheet URLs are accepted\.?$/i, () => "Seules les URL HTTPS publiques sont acceptées."],
  [/^Private datasheet URLs are not allowed\.?$/i, () => "Les URL privées ne sont pas autorisées."],
  [/^The datasheet URL is not on a configured official manufacturer domain\.?$/i, () => "L’URL n’appartient pas à un domaine officiel configuré du fabricant."],
  [/^The official datasheet host could not be resolved\.?$/i, () => "Le serveur de la fiche officielle est introuvable."],
  [/^The official source did not provide a verified PDF\.?$/i, () => "La source officielle n’a pas fourni de PDF vérifié."],
  [/^Third-party datasheet mirrors are not accepted\.?$/i, () => "Les miroirs tiers de fiches techniques ne sont pas acceptés."],
  [/^Worker poll failed$/i, () => "Interrogation du worker échouée."],
  [/^RAG indexing: (.+)$/i, (m) => `Indexation : ${translateEvent(m[1], "fr")}`],
  [/^The official datasheet source returned HTTP (\d+)\.?$/i, (m) => `La source officielle a renvoyé HTTP ${m[1]}.`],
  [/^Verified datasheet URL$/i, () => "URL de fiche vérifiée"],
  [/^Logged out\.?$/i, () => "Déconnecté."],
];

export function translateEvent(message: string | null | undefined, lang: Lang): string {
  if (!message) return "";
  if (lang !== "fr") return message;
  for (const [re, fn] of FR) {
    const m = message.trim().match(re);
    if (m) return fn(m);
  }
  return message;
}
