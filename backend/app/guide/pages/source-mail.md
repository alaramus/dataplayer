# Email

Your mailbox, read and written from DataPlayer: folders, letters, answers and
attachments, in a tab of its own rather than a catalog. How connections work in
general is on the [Connections](connections.md) page.

## What you can see

- The mailbox's folders, with how many letters each holds and how many are unread
- The letters of a folder, newest first, fifty at a time
- Letters found by words in the sender, the subject or the text
- A letter: who it is from and to, its text, and its attachments
- Images in a letter from the web, once you ask for them

## What you can change

- New letters, answers, answers to everyone, and forwards with their files
- Letters marked read or unread
- Letters moved to Trash, and deleted for good from Trash
- Attachments saved to your computer or into your own folder

## Connecting

The **Connection** page of the window asks for:

- **Email address**: what your letters are from, and **Your name** beside it;
- **Login** and **Password**. Leave the login empty to sign in with the
  address. For Gmail, Yandex or Mail.ru use an app password made in the
  account's security settings;
- **IMAP server**, **IMAP port** and **IMAP security**: where letters are read.
  `tls` is 993, `starttls` is 143, `none` is for a server inside your network
  that offers neither;
- **SMTP server**, **SMTP port** and **SMTP security**: where letters are sent.
  `tls` is 465, `starttls` is 587;
- **SMTP sign-in**: **Same as IMAP**, or **Its own login** for a server that
  signs the two in apart;
- **Keep a copy in Sent**: switch it off for a server that keeps one itself,
  as Gmail does, or every letter is there twice.

**Check** says which step failed: reaching the IMAP server, signing in to it,
reaching the SMTP server or signing in to it. With `starttls`, a server that
will not encrypt the connection is refused rather than sent your password in
plain text.

## The Mail tab

Opening the connection opens a **Mail** tab: folders on the left, the letters
of the chosen folder in the middle, the open letter on the right.

- Inbox, Drafts, Sent, Junk and Trash come first, whatever the server calls
  them; then the rest by name.
- Opening a letter marks it read, as every mail client does. **Mark unread**
  puts it back.
- **Search** looks for the words in the sender, the subject and the text of
  the letters in the folder.
- **Refresh** reads the folder again. New letters are not announced yet.
- A letter larger than 32 MB is not opened here.

## A letter's text

A letter written as a web page is shown without its scripts, and images from
the web are not loaded until you press **Show images**: a sender can tell from
them that, and when, you read the letter. Links open in a new browser tab.

## Writing

**New letter**, **Reply**, **Reply all** and **Forward** open a window with
**To**, **Cc**, **Bcc**, **Subject** and the text. Addresses are separated by
commas. Files from your computer can be attached, 25 MB in all. A forward
takes the original's attachments along; an answer is threaded under the
letter it answers, which is marked answered.

## Deleting

**Delete** moves the selected letters to Trash; a mailbox without a Trash
gets one. In Trash, **Delete** removes them for good, after asking.

## Attachments

Each attachment of an open letter has **Download**, which saves it to your
computer, and **Save to my folder**, which puts it under `Mail/<address>/` in
your own storage, where the file explorer opens it. A name already there gets
` (2)` added rather than being written over. A file that would take your
storage past its limit is refused.

## Who can open it

Only you. A connection can be shared, and whoever it is shared with reads
through your sign-in; for a mailbox that would be reading your letters, so
somebody you shared it with sees the connection and cannot open the mailbox.
Mail is not searched from the search field above, and the agent does not read
it.

## What Email does not do here yet

- Tell you of new letters as they arrive
- Drafts kept on the server, moving letters between folders, flags, signatures
- Attaching a file from your own folder
- Signing in to Gmail or Microsoft 365 without an app password, and Exchange
  without IMAP
- Reaching the server through an SSH tunnel
