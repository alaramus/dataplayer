/** Graphiques d'une page de lignes (features/charts). */
import type { Messages } from "../en"

export const charts: Messages["charts"] = {
  read_failed: "La page du graphique n'a pas pu être lue",
  page: {
    none: "Page courante · lignes 0",
    range: "Page courante · lignes {first}–{last}",
    more: "Les lignes suivantes ne sont pas incluses.",
    bounded: "Le graphique n'utilise que ce résultat borné.",
  },
  no_data: "Aucune valeur représentable sur cette page",
  no_measure: "Cette page n'a aucune colonne numérique visible à représenter",
  types: {
    line: "Ligne",
    bar: "Barres",
    pie: "Secteurs",
  },
  row: "Ligne",
  other: "Autres",
  numeric_on_page: "{name} (numérique sur cette page)",
  fields: {
    suggestion: "Vue suggérée",
    type: "Type de graphique",
    label: "Étiquette",
    value: "Valeur",
    x: "Axe X",
    y: "Axe Y",
  },
  best_fit: "Meilleur ajustement",
  suggestions: {
    over: "{measure} sur {dimension}",
    by: "{measure} par {dimension}",
    share: "Part de {measure} par {dimension}",
  },
}
