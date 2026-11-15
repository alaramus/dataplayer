# Mail, the second step

Decisions D372–D376. What the first slice of mail (D366–D371) left for later
and the user asked for next: being told of new letters, a card for Gmail,
attaching a file from one's own folder, drafts, and moving letters
between folders.

## D372. New letters are watched while their owner is in the application

- **A topic, `mail.arrivals`, per user and alive while somebody watches**,
  built as `connector.health` is (D19): the first subscriber of a user starts
  a monitor, the last one to leave stops it after the same grace.
- **A round asks each of the user's own switched-on mailboxes** for its
  inbox's `UIDVALIDITY`, `UIDNEXT` and unread count with one `STATUS`, every
  `MAIL_ARRIVALS_INTERVAL_SECONDS` (60). Only when `UIDNEXT` has moved are
  the new UIDs searched and the newest three headings read. A grantee's
  mailboxes are not watched: they cannot open them (D367).
- **Where the inbox was is a `UIDVALIDITY` and a `UIDNEXT`.** The first round
  only learns it; a changed `UIDVALIDITY` learns it again rather than calling
  the whole inbox new.
- **What is announced**: the connection, the inbox's unread count, how many
  letters arrived, and the newest three's sender and subject. The browser
  records it in the notifications (D114) with **Open**, and reads the open
  Mail tab's lists again.
- **A mailbox that fails waits longer**, doubling to the health monitor's cap,
  as a dead host does there.

Rejected: IDLE. It holds a connection per mailbox for as long as somebody is
signed in, in a server that is one process (D124), and an IMAP server limits
how many a login may hold. A minute is soon enough for a letter.

## D373. Gmail is a card of the mail type with its servers filled in

- `CatalogFace` gains `options`: what a card fills into a new connection's
  form. The mail type shows two cards — **Email** (any server) and **Gmail**
  — one type, one form (D264).
- **Gmail**: `imap.gmail.com` 993 and `smtp.gmail.com` 465, both TLS, and
  **Keep a copy in Sent** off, because Gmail keeps one itself. It needs an
  app password.
- The filled values stay editable; nothing about a card is stored but its key.

Rejected: an **Outlook** card. It was made and taken out the same day:
Microsoft 365 and Outlook.com refuse a password over IMAP, so the card
filled in servers nobody could sign in to. It comes back with OAuth.

## D374. A file from one's own folder is attached by its path, read by the server

- The letter window offers **From my folder**: a list of the owner's storage,
  folder by folder, with files ticked.
- The letter names them as paths; the server resolves each with the one
  containment rule (D8), refuses a folder and a link out, and counts them in
  the 25 MB with the uploads and the carried attachments.
- The listing route is a mail route and so `own` (D367): it lists the
  storage of the person who owns the mailbox, who is the person asking.

## D375. A draft is a letter appended to Drafts, and replaced when saved again

- **Save draft** appends the letter to the folder whose role is `drafts`,
  made as `Drafts` when there is none, flagged `\Draft` and `\Seen`, with its
  Bcc kept as a header — a draft is read back by whoever finishes it.
- **A letter in Drafts opens with Edit**, in a letter window filled from it.
  Saving it again appends the new one and deletes the old for good; sending
  it deletes it.
- **Attachments carried from a letter** — a forward's, an edited draft's —
  are listed in the window and can be dropped one by one: the letter names
  the parts it keeps.
- A draft may have no recipient; sending one may not.

## D376. A letter moves to a folder chosen from the mailbox's own

**Move to** lists the selectable folders but the one the letter is in; the
target is checked against LIST, as every folder a client names is. UID MOVE
where the server has it, otherwise COPY, `\Deleted` and EXPUNGE of those UIDs,
as delete does (D370).

## Left for later

Being told of new letters in folders other than the inbox, or by the
browser's own notifications; dragging a letter onto a folder; OAuth for
Gmail and Microsoft 365.
