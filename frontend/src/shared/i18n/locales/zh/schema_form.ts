/** 由 JSON 模式绘制的表单（shared/SchemaForm）。 */
import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<已隐藏>",
  show_password: "显示密码",
  hide_password: "隐藏密码",
  choose: "选择 {label}",
  is_number: "{label} 是一个数字",
  at_least: "{label} 至少为 {n}",
  at_most: "{label} 至多为 {n}",
  required: "{label} 为必填项",
  min_length: "{label} 至少需要 {n} 个字符",
}
