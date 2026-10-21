/** 终端（features/terminals）。 */
import type { Messages } from "../en"

export const terminals: Messages["terminals"] = {
  terminals: "终端",
  press: {
    hide: "隐藏终端",
    open: "打开终端",
    open_on: "在 {name} 上打开终端",
    on: "{name} 上的终端",
    with_open: "{doing} · {n} 个已打开",
  },
  connection: "连接",
  numbered: "{name} ({n})",
  notice: {
    connecting: "正在连接……",
    ended: "Shell 已结束",
    ended_with: "Shell 已结束，状态为 {status}",
    lost: "与服务器的连接已丢失",
    sign_in: "请重新登录以打开终端",
  },
  close: "关闭此终端",
  open: "打开终端",
  none_menu: "你的连接都没有终端",
  none_menu_hint: "SSH 连接有",
  none: "你的连接都没有终端。SSH 连接有。",
  choose: "没有打开的终端。请选择要在其上打开终端的连接：",
  open_again: "再次打开",
  unlock: "解锁密钥",
}
