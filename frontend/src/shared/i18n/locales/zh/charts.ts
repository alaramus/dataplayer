/** 行页面的图表（features/charts）。 */
import type { Messages } from "../en"

export const charts: Messages["charts"] = {
  read_failed: "无法读取图表页面",
  page: {
    none: "当前页 · 0 行",
    range: "当前页 · 第 {first}–{last} 行",
    more: "后续行未包含在内。",
    bounded: "图表仅使用此有限结果。",
  },
  no_data: "此页没有可绘制的值",
  no_measure: "此页没有可见的数值列可供绘制图表",
  types: {
    line: "折线",
    bar: "柱状",
    pie: "饼图",
  },
  row: "行",
  other: "其他",
  numeric_on_page: "{name}（此页为数值）",
  fields: {
    suggestion: "建议视图",
    type: "图表类型",
    label: "标签",
    value: "值",
    x: "X 轴",
    y: "Y 轴",
  },
  best_fit: "最佳匹配",
  suggestions: {
    over: "{measure}随 {dimension} 的变化",
    by: "按 {dimension} 的 {measure}",
    share: "{measure}按 {dimension} 的占比",
  },
}
