# Quick chat with the model Chrome runs on this computer

Date: 2026-10-11. Decision: D223.

Chrome ships Gemini Nano and lets a page call it through the Prompt API
(`LanguageModel`). It needs no key and nothing leaves the computer, which makes
it the easiest way to start: a person without any provider account can still
ask something. It is small, its context window is a few thousand tokens, and
officially it speaks English, Japanese, Spanish, German and French.

## Where it is offered

Only in the quick chat. The quick chat already calls a model directly with no
tools (D158); the agent needs tool calling and a long context, which Nano does
not offer. The model list in the quick chat gains a "This browser" group with
one row, Gemini Nano, described by Chrome's availability: unavailable rows are
shown but cannot be chosen, with the reason — no Prompt API in this browser, or
a computer below Chrome's requirements (22 GB free, a graphics card with more
than 4 GB or 16 GB of memory).

## Download

Chrome reports `downloadable` until the model is on disk. Choosing the row then
shows a line above the composer offering Download; Chrome only starts the
download from a press, so it is never started on the person's behalf. While it
downloads the line shows Chrome's progress, and sending stays off until the
model is `available`.

## History

Shared with every other quick chat, rejected alternative: chats kept only in the
browser, which would split the history by device and leave the AI history list
unable to show them. The server never calls the model. Two routes:

- `browser-turns` keeps the question exactly as a provider send does before the
  model is called, names a new chat by it, sets the chat's model to
  `browser:gemini-nano`, and returns the prompt and the trimmed history the
  server would give a provider — one computation, on the server.
- `browser-answers` keeps the answer the browser wrote, and only while a
  question waits for one.

When the history does not fit Nano's window, the browser drops the older half
of the turns and tries again, keeping the instructions. What was written before
a failure is kept, as for a provider (D158).

The browser's model is not a model the settings can name, so choosing it does
not change the default model (D140); the browser remembers that the quick chat
was last left on it.
