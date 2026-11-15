"""IMAP's modified UTF-7 for folder names (RFC 3501, 5.1.3).

A server names `Входящие` as `&BBIERQQ+BDQETwRJBDgENQ-`: printable ASCII but
`&` stands for itself, `&-` is a literal `&`, and anything else is UTF-16 in
base64 with `,` for `/`, between `&` and `-`. Neither `imaplib` nor the
standard codecs know it.
"""

import base64


def decode(name: str) -> str:
    """The readable name; text that is not modified UTF-7 is left as it is."""
    out: list[str] = []
    i = 0
    while i < len(name):
        char = name[i]
        if char != "&":
            out.append(char)
            i += 1
            continue
        end = name.find("-", i + 1)
        if end < 0:
            return name
        if end == i + 1:
            out.append("&")
        else:
            chunk = name[i + 1 : end].replace(",", "/")
            try:
                raw = base64.b64decode(chunk + "=" * (-len(chunk) % 4))
                out.append(raw.decode("utf-16-be"))
            except ValueError:
                return name
        i = end + 1
    return "".join(out)


def encode(name: str) -> str:
    out: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            raw = "".join(pending).encode("utf-16-be")
            out.append("&" + base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",") + "-")
            pending.clear()

    for char in name:
        if 0x20 <= ord(char) <= 0x7E:
            flush()
            out.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    flush()
    return "".join(out)
