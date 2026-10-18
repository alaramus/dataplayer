/** Diagramme einer Seite mit Zeilen (features/charts). */
import type { Messages } from "../en"

export const charts: Messages["charts"] = {
  read_failed: "Die Diagrammseite konnte nicht gelesen werden",
  page: {
    none: "Aktuelle Seite · Zeilen 0",
    range: "Aktuelle Seite · Zeilen {first}–{last}",
    more: "Spätere Zeilen sind nicht enthalten.",
    bounded: "Das Diagramm verwendet nur dieses begrenzte Ergebnis.",
  },
  no_data: "Keine darstellbaren Werte auf dieser Seite",
  no_measure: "Diese Seite hat keine sichtbare numerische Spalte für ein Diagramm",
  types: {
    line: "Linie",
    bar: "Balken",
    pie: "Kreis",
  },
  row: "Zeile",
  other: "Sonstiges",
  numeric_on_page: "{name} (numerisch auf dieser Seite)",
  fields: {
    suggestion: "Vorgeschlagene Ansicht",
    type: "Diagrammtyp",
    label: "Beschriftung",
    value: "Wert",
    x: "X-Achse",
    y: "Y-Achse",
  },
  best_fit: "Am besten passend",
  suggestions: {
    over: "{measure} über {dimension}",
    by: "{measure} nach {dimension}",
    share: "Anteil {measure} nach {dimension}",
  },
}
