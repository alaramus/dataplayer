# Email

For changing how a mailbox is reached over IMAP and SMTP, what its tab shows,
how a letter is read, written, answered, forwarded, drafted, moved and put
away, where an attachment goes, and how new letters are announced. The contract every source keeps is in
[contract.md](contract.md); this one keeps it without a catalog.

Decisions here: D366, D367, D368, D369, D370, D371, D372, D373, D374, D375, D376.

```
backend/app/adapters/mailbox.py        SupportsMailbox and its models, nothing about IMAP
backend/app/adapters/mail/
├── options.py     address, login, IMAP and SMTP servers; SMTP's own login as a union
├── session.py     a session per operation in the thread pool; each step's failure named
├── utf7.py        IMAP's modified UTF-7 for folder names
├── folders.py     LIST, what a folder is for, STATUS counts, the Trash
├── messages.py    pages of headings, search, one message, marking, deleting
├── sending.py     composing, answering, forwarding, the copy in Sent
└── adapter.py     MailAdapter, registered as `mail`
backend/app/connectors/mail_routes.py  /connectors/{id}/mail/…, every one `own`
backend/app/connectors/mail_files.py   an attachment kept under Mail/<address>/; files of one's folder
backend/app/connectors/mail_arrivals.py  the `mail.arrivals` topic
frontend/src/features/mail/            the Mail tab, the reader, the letter window, arrivals
```

## D366. A mailbox is a source type that opens as a mailbox, not as a catalog

- The type `mail` is registered as every source is (D1): its form, its
  encrypted password, the check, switching it off, its page in the guide. Its
  category is **Mail**.
- `CatalogShape` has `mailbox` beside `levels` and `tree`. Opening a
  connection of that shape opens a **Mail** panel in the work column instead
  of a catalog; the screen reads the shape and never the type's name.
- One capability, `SupportsMailbox`, with models that say nothing about IMAP.
  Another way to a mailbox is another driver of it.
- No catalog and no rows: the catalog and fetch routes answer 501, and nothing
  that walks catalogs — search, kept names, the agent, pipelines, declared
  references — reaches a mailbox.
- Its routes live in `mail_routes.py`, not in the connector routes.

Known deviations:

- **A layout restored with a Mail tab** reads the folders again on mount; a
  letter that was open is not reopened.

Spec: [A mailbox as a source](../../decisions/2026-11-15-mail-source-design.md)

## D367. A mailbox is its owner's alone

Every mail route requires `own`. A grantee reads a shared connection with the
owner's credentials, which for a mailbox is reading somebody's letters, so a
grantee is answered 403 on every mail route while the connection itself stays
visible to them.

Spec: [A mailbox as a source](../../decisions/2026-11-15-mail-source-design.md)

## D368. IMAP, a session per operation in the thread pool; a message is a UID in a folder

- `imaplib` and `smtplib`, synchronous, one operation per call into the
  thread pool; no session kept between requests. `imaplib` is contained by an
  import contract.
- Security is `tls`, `starttls` or `none`, certificates checked against the
  system's store. STARTTLS is upgraded before the login is sent, and a server
  that will not upgrade is refused.
- One login and password for both servers, or SMTP's own as the
  `separate` member of the options union: an optional `SecretStr` would not
  be seen as a secret by the schema split (D16).
- The check opens both servers and says which step failed.
- A folder is named by the server's own name for it, decoded from modified
  UTF-7 for display, and checked against LIST before it is selected. Its role
  comes from SPECIAL-USE attributes, else from the common names; INBOX is
  always the inbox. Counts come from STATUS.
- A page of headings is read newest first by sequence number, at most 100,
  with `BODY.PEEK[HEADER.FIELDS …]` only. A search is `UID SEARCH CHARSET
  UTF-8 TEXT` with the words as a literal, so they are a value and never
  syntax; its UIDs are paged the same way.
- Opening a message fetches `BODY[]`, which marks it read. Above 32 MB it is
  refused unread. It arrives parsed: headings, text with LF line ends, HTML as
  written, inline images up to 2 MB together as `data:` URIs by Content-ID, and
  attachments by their place in the message's walk.

Known deviations:

- **"Has attachments" in a list is read off the top part's type**
  (`multipart/mixed`), without BODYSTRUCTURE; a letter that carries a file
  some other way shows none until opened.
- **A folder named by a client is checked with a LIST per request.** One more
  round trip; kept until sessions are kept.

Spec: [A mailbox as a source](../../decisions/2026-11-15-mail-source-design.md)

## D369. A message's HTML is untrusted and is shown without its scripts or remote images

The HTML is sanitised in the browser with DOMPurify (`features/mail/letter.ts`)
and drawn in an iframe whose `sandbox` allows nothing but popups — no scripts,
no forms, no same origin, no navigation of the page — so a link opens a tab of
its own. A Content-Security-Policy inside it allows images only from `data:`
until the reader presses **Show images** for that message, asked again for each
letter. The letter's own stylesheet is kept: with no scripts and nothing
loaded, it only paints. `cid:` images are drawn from what came with the
letter.

Spec: [A mailbox as a source](../../decisions/2026-11-15-mail-source-design.md)

## D370. Writing, answering, forwarding and deleting

- Sent through SMTP; a server that offers no AUTH is sent to without a login.
  A copy is appended to the folder whose role is `sent`, with `\Seen`, unless
  the connection's **Keep a copy in Sent** is off. No such folder, or a
  failure after sending, is said as no copy kept, never as a failure to send.
- An answer's `In-Reply-To` and `References` and a forward's attachments are
  read by the server from the original; the client names it by folder and UID.
  The original of an answer is marked `\Answered`.
- Bcc is a recipient and never a header. Addresses are checked by a pattern
  rather than pydantic's `EmailStr`, which refuses `.local` domains.
- A new letter's uploads and a forward's attachments together are at most
  25 MB.
- Delete moves to the folder whose role is `trash`, made as `Trash` when there
  is none: UID MOVE, or COPY then `\Deleted` and UID EXPUNGE. In Trash, delete
  is for good; the screen asks first.

Known deviations:

- **Without UIDPLUS, deleting expunges the whole folder**, which also removes
  what other clients had marked deleted there. No narrower command exists.

Spec: [A mailbox as a source](../../decisions/2026-11-15-mail-source-design.md)

## D371. An attachment goes to the computer or into the owner's folder

- **Download** hands the bytes over as `application/octet-stream` under the
  attachment's own name, made safe.
- **Save to my folder** writes under `Mail/<address>/` of the owner's storage:
  a folder the server names, a name made plain on both platforms, ` (2)` added
  rather than overwriting, symlinks refused, and the person's limit (D324)
  checked first — over it, 507 with the same sentence a file source gives.

Spec: [A mailbox as a source](../../decisions/2026-11-15-mail-source-design.md)

## D372. New letters are watched while their owner is in the application

- `app/connectors/mail_arrivals.py` is the topic `mail.arrivals`, built as
  `connector.health` is (D19): a monitor per user, started by the first
  subscriber, stopped after `HEALTH_GRACE_SECONDS` once the last one leaves.
- A round asks each of the user's own switched-on mailboxes — a type whose
  driver is `SupportsMailbox`, never a granted one (D367) — for
  `inbox_arrivals(mark)`: one `STATUS INBOX (UIDVALIDITY UIDNEXT UNSEEN)`,
  and only when `UIDNEXT` moved, `UID SEARCH UID n:*` and the newest three
  headings. Every `MAIL_ARRIVALS_INTERVAL_SECONDS`; a failure doubles the
  wait to `HEALTH_BACKOFF_CAP_SECONDS`.
- The mark is a `UIDVALIDITY` and a `UIDNEXT`; the first round only learns it,
  and a changed `UIDVALIDITY` learns it again.
- An event is sent when letters arrived or the unread count changed; a second
  socket gets the last counts. The browser (`features/mail/arrivals.ts`)
  records it with **Open** (D114) and reads that mailbox's lists again.

Known deviations:

- **Only the inbox is watched**; a server's filter that files letters
  elsewhere announces nothing.

Spec: [Mail, the second step](../../decisions/2026-11-15-mail-second-step-design.md)

## D373. Gmail is a card of the mail type with its servers filled in

`CatalogFace.options` is what a card fills into a new connection's form,
arriving as the window's draft and still editable. The mail type shows
**Email** and **Gmail** (TLS 993/465, **Keep a copy in Sent** off). Only the
card's key is stored. There is no Outlook card: Microsoft 365 and Outlook.com
refuse a password over IMAP, and a card that cannot sign in is a promise the
form breaks; it waits for OAuth.

Spec: [Mail, the second step](../../decisions/2026-11-15-mail-second-step-design.md)

## D374. A file from one's own folder is attached by its path, read by the server

`/mail/my-files` lists one folder of the owner's storage, folders first, dot
files and links out left out; a letter names files as `stored_files`, which
`mail_files.read_stored` resolves through `LocalStorage.place` — the one
containment rule (D8) — refusing a folder, a missing file and a path out, and
measuring them against the 25 MB before reading. Their media type comes from
Python's own table, not the system's: Windows' registry calls a CSV an Excel
sheet.

Spec: [Mail, the second step](../../decisions/2026-11-15-mail-second-step-design.md)

## D375. A draft is a letter appended to Drafts, and replaced when saved again

- **Save draft** appends to the `drafts` folder, made as `Drafts` if missing,
  flagged `\Draft \Seen`, without a Date and with its Bcc as a header. The
  window closes; the draft opens again from Drafts with **Edit**.
- A letter names `draft_of`: saving it again appends the new one and removes
  the old for good; sending it removes it. A draft of an answer keeps its
  `In-Reply-To`.
- `keep_parts` names the parts of `forward_of` or `draft_of` that go along;
  the window lists them and drops them one by one.
- A draft needs no recipient; sending without one is refused.

Spec: [Mail, the second step](../../decisions/2026-11-15-mail-second-step-design.md)

## D376. A letter moves to a folder chosen from the mailbox's own

**Move to a folder** offers the selectable folders but the current one; the
target is checked against LIST, then UID MOVE, or COPY and expunge of those
UIDs as delete does.

Spec: [Mail, the second step](../../decisions/2026-11-15-mail-second-step-design.md)
