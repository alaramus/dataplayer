/**
 * What jsdom leaves out.
 *
 * jsdom has no layout at all, so it implements no method that would move the
 * viewport: `Element.prototype.scrollIntoView` is simply absent. A component
 * that calls it is then correct in a browser and throws here — and because
 * the call sits behind an `await`, the throw escapes as an unhandled
 * rejection, which Vitest reports beside a suite of green tests and fails the
 * run on. Giving jsdom a no-op is what makes the environment resemble the
 * browser; guarding the call in the component would only hide the gap and
 * leave the scrolling untested.
 */
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}

if (!navigator.clipboard) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: async () => undefined },
  })
}
