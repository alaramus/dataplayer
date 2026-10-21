/** 组件库自己的文字：空状态、复制按钮、选择器（shared/ui）。 */
import type { Messages } from "../en"

export const kit: Messages["kit"] = {
  copy: {
    tooltip: "复制",
  },
  color_picker: {
    reset: "重置颜色",
  },
  file: {
    choose_one: "选择一个文件",
    choose_many: "选择文件",
  },
  date_time: {
    pick: "选择日期和时间，使用 UTC",
  },
  fullscreen: {
    enter: "全屏显示",
    leave: "退出全屏",
    unsupported: "此浏览器无法全屏显示",
  },
  layout: {
    user_menu: "用户菜单",
    preferences: "偏好设置",
    admin: "管理",
    sign_out: "退出登录",
  },
  option: {
    clear: "清除",
  },
  progress: {
    paused: "已暂停",
  },
  table: {
    empty: "没有可显示的内容",
  },
  tree: {
    tick: "勾选 {name}",
  },
}
