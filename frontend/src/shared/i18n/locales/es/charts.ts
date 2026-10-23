/** Gráficos de una página de filas (features/charts). */
import type { Messages } from "../en"

export const charts: Messages["charts"] = {
  read_failed: "No se pudo leer la página del gráfico",
  page: {
    none: "Página actual · Filas 0",
    range: "Página actual · Filas {first}–{last}",
    more: "No se incluyen las filas posteriores.",
    bounded: "El gráfico solo usa este resultado acotado.",
  },
  no_data: "No hay valores representables en esta página",
  no_measure: "Esta página no tiene una columna visible numérica que graficar",
  types: {
    line: "Línea",
    bar: "Barras",
    pie: "Circular",
  },
  row: "Fila",
  other: "Otros",
  numeric_on_page: "{name} (numérica en esta página)",
  fields: {
    suggestion: "Vista sugerida",
    type: "Tipo de gráfico",
    label: "Etiqueta",
    value: "Valor",
    x: "Eje X",
    y: "Eje Y",
  },
  best_fit: "Mejor ajuste",
  suggestions: {
    over: "{measure} a lo largo de {dimension}",
    by: "{measure} por {dimension}",
    share: "Proporción de {measure} por {dimension}",
  },
}
