# A mailbox as a source

Decisions D366–D371. The first slice of mail: one person's mailbox, read and
written over IMAP and SMTP, in a tab of its own.

## The problem

DataPlayer is installed inside a company's network, each person gets an
account and spends the day in it. Mail is the one tool they still leave for.
What is asked for is a plain mail client: see the folders, read a message,
write one, answer, forward, delete, and take an attachment either to the
computer or into the person's own folder, where the rest of DataPlayer can
open it.

Mail is not wanted as data. Nobody asked to filter messages in a grid, page
them into a table or feed them to a pipeline, and a grid is a poor way to read
a letter.

## What was taken

### D366. A mailbox is a source type that opens as a mailbox, not as a catalog

- **A connection like any other.** The type `mail` is registered as every
  source is (D1): its form, its encrypted password (`SecretStr`), the check
  before saving, switching it off (D20), its icon and its page in the guide
  (D183). One new category, **Mail**.
- **What a source looks like opened is the type's to say.** `CatalogShape`
  gains `mailbox`, beside `levels` and `tree`. A screen that opens a
  connection reads the shape and opens a **Mail** tab instead of a catalog; no
  screen names the type (D62).
- **One capability, `SupportsMailbox`**, in `app/adapters/mailbox.py`, with
  its models: folders, a page of message headings, one message, sending,
  marking, deleting, and an attachment's bytes. The models say nothing about
  IMAP, so another way to a mailbox (Microsoft Graph, JMAP) is another driver
  of the same capability rather than another screen.
- **No catalog and no rows.** The type does not implement `SupportsCatalog` or
  `SupportsFetch`, so those routes answer 501 for it as for any source without
  them (D2), and nothing that walks catalogs — search, kept names, the agent,
  pipelines, declared references — ever reaches a mailbox.
- **Its routes are their own module**, `app/connectors/mail_routes.py`, under
  `/connectors/{id}/mail/…`: the connector routes are already the largest
  file in the backend, and nothing in them is shared with mail beyond
  resolving the adapter.

### D367. A mailbox is its owner's alone

Every mail route requires `own` (D33). A connection can be shared, and a
grantee reads with the owner's credentials — for a database that is the point,
for a mailbox it would be reading somebody's letters. So a grantee of a mail
connection is answered 403 on every mail route; the connection itself stays
visible to them, as every shared connection is.

### D368. IMAP, a session per operation in the thread pool; a message is a UID in a folder

- **The standard library.** `imaplib` and `smtplib` are synchronous, so one
  operation — connect, sign in, do the work, log out — is one call into the
  thread pool, as kazoo is for ZooKeeper (D297). No session is kept between
  requests in this slice. `email` with `policy.default` parses and composes.
  No new dependency.
- **Security is one of three**: TLS from the first byte (993, 465), STARTTLS
  (143, 587), or none, for a server inside the network that offers neither.
  Certificates are verified with the system's store. STARTTLS is upgraded
  before the login is sent, and a server that refuses the upgrade is refused
  rather than signed in to in plain text.
- **One login and password for both**, and an optional SMTP login and
  password for a server that signs the two in apart; empty means the same.
- **The check says which step failed**: reaching the IMAP server, signing in
  to it, reaching the SMTP server, signing in to it. Each is its own message,
  because "check failed" leaves a person guessing between a wrong port and a
  wrong password.
- **A folder's counts** — messages and unread — come from STATUS, one per
  folder, in the session that listed them.
- **A folder is named by the server's own name** for it, as LIST returns it,
  and decoded from IMAP's modified UTF-7 for display. A folder named by a
  client is checked against LIST before it is selected — an identifier is
  validated against the source (ENGINEERING.md).
- **What a folder is for** is read from SPECIAL-USE attributes (`\Sent`,
  `\Trash`, `\Drafts`, `\Junk`, `\Archive`) and, where the server sends none,
  from the common names. INBOX is always the inbox.
- **A message is a UID in a folder.** A page of headings is read newest
  first by sequence number — the order every server keeps without the SORT
  extension many lack — at most 100 at a time, with UID, flags, size, sender,
  recipients, subject and date. A search is IMAP `SEARCH` over sender, subject
  and text, words given as values and never as syntax (D2c); its UIDs are
  paged the same way.
- **Opening a message marks it read**, as every client does: the body is
  fetched with `BODY[]`, not `BODY.PEEK[]`. A message above 32 MB is refused
  rather than read whole.
- **The message arrives parsed**: headings, the plain text, the HTML as the
  sender wrote it, inline images up to 2 MB together as `data:` URIs keyed by
  Content-ID, and the attachments as a list of part number, filename, type and
  size. An attachment's bytes are read on their own request.

### D369. A message's HTML is untrusted and is shown without its scripts, styles reaching out, or remote images

The HTML of a letter is written by a stranger. It is sanitised in the browser
with DOMPurify, the same one Markdown uses, and drawn in an iframe with an
empty `sandbox` — no scripts, no forms, no navigation of the page — and a
Content-Security-Policy that allows images only from `data:` until the reader
presses **Show images** for that message. A remote image is how a sender
learns that and when a letter was read. A link opens in a new browser tab, and
nothing in the letter can open one by itself.

### D370. Writing, answering, forwarding and deleting

- **Sent through SMTP**, signed in with the same login and password, and a
  copy appended to the Sent folder with `\Seen` unless the connection says the
  server keeps one itself (Gmail does, and a second copy would be a
  duplicate). No Sent folder found is not an error: the letter is sent and the
  answer says no copy was kept.
- **Answering** carries `In-Reply-To` and `References` from the original,
  read by the server rather than sent by the client, and marks the original
  `\Answered`. **Forwarding** takes the original's attachments along, read by
  the server as well.
- **Attachments of a new letter** are uploaded from the computer, 25 MB in all.
- **Delete moves to Trash** — MOVE where the server has it, otherwise COPY,
  `\Deleted` and EXPUNGE of those UIDs (UID EXPUNGE where offered). A server
  with no Trash gets one made, as other clients do. **Deleting in Trash is for
  good**, and the screen asks first.
- **Read and unread** are `\Seen` set or cleared on the chosen messages.

### D371. An attachment goes to the computer or into the owner's folder

- **Download** hands the bytes over with the attachment's own filename.
- **Save to my folder** writes it under `Mail/<address>/` in the owner's
  personal storage, where the file explorer opens it. The name is the
  attachment's, made safe on both platforms, with ` (2)`, ` (3)` added rather
  than overwriting. The folder is the server's choice, never the client's
  (D8), and the write counts against the person's limit (D324): over it, the
  answer is the same 507 a file source gives.

## Rejected

- **Mail as rows in a grid.** Everything a grid gives — filters, paging into
  tables, export, pipelines — is what nobody asked for, and reading a letter
  in a cell is worse than in any client.
- **A message as a representation of a catalog node (D47).** It would put a
  folder tree into the catalog column and a letter into the work column: three
  tabs to read one letter, and a list of messages that is a catalog level with
  none of a mail list's behaviour.
- **A server-side HTML sanitiser.** DOMPurify is already in the client, does
  the job where the HTML is drawn, and a second sanitiser on the server would
  be a second definition of what is safe.
- **aioimaplib and aiosmtplib.** An asynchronous client would save the thread
  hop and add two dependencies whose maintenance is thinner than the standard
  library's; the thread pool is how ZooKeeper and Kafka are already reached.
- **Listing by `UID SEARCH ALL` and fetching whole messages for the list.**
  A list needs headings only; on an inbox of fifty thousand letters the
  search returns fifty thousand UIDs for every page, and whole bodies bring
  every attachment along with them.
- **Delete as `\Deleted` and a plain EXPUNGE.** It is not recoverable, and a
  plain EXPUNGE also removes whatever other clients had marked deleted in the
  same folder.
- **A short cache of listings** to spare the server repeated requests. A list
  read again a second after a delete would show the deleted letter.
- **Opening a message without marking it read.** Every client marks it; one
  that does not leaves the inbox's count wrong in every other client.

## Left for later

- Being told of a new letter: polling or IDLE, a count in the header, a
  notification (D113). Where it has got to is a UID kept with the folder's
  UIDVALIDITY: a UID alone means nothing once UIDVALIDITY changes.
  Consecutive failures are counted, and polling stops after a few.
- Presets for Gmail, Outlook, Yandex and Mail.ru as cards (D264).
- Attaching a file from the person's own folder.
- Drafts kept on the server, threads, moving to a chosen folder, flags beyond
  read, signatures.
- OAuth2 sign-in (XOAUTH2) for Gmail and Microsoft 365, and Exchange without
  IMAP.
- A session kept between requests, through the resource store (D101).
- Reaching the server through an SSH tunnel (D282).
