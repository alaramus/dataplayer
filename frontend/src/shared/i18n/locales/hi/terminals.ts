/** टर्मिनल (features/terminals)। */
import type { Messages } from "../en"

export const terminals: Messages["terminals"] = {
  terminals: "टर्मिनल",
  press: {
    hide: "टर्मिनल छिपाएँ",
    open: "टर्मिनल खोलें",
    open_on: "{name} पर टर्मिनल खोलें",
    on: "{name} पर टर्मिनल",
    with_open: "{doing} · {n} खुले",
  },
  connection: "कनेक्शन",
  numbered: "{name} ({n})",
  notice: {
    connecting: "कनेक्ट हो रहा है…",
    ended: "शेल समाप्त हो गया",
    ended_with: "शेल स्थिति {status} के साथ समाप्त हो गया",
    lost: "सर्वर से कनेक्शन टूट गया",
    sign_in: "टर्मिनल खोलने के लिए फिर से साइन इन करें",
  },
  close: "यह टर्मिनल बंद करें",
  open: "टर्मिनल खोलें",
  none_menu: "आपके किसी भी कनेक्शन में टर्मिनल नहीं है",
  none_menu_hint: "SSH कनेक्शन में होता है",
  none: "आपके किसी भी कनेक्शन में टर्मिनल नहीं है। SSH कनेक्शन में होता है।",
  choose: "कोई टर्मिनल खुला नहीं है। वह कनेक्शन चुनें जिस पर एक खोलना है:",
  open_again: "फिर से खोलें",
  unlock: "कुंजी अनलॉक करें",
}
