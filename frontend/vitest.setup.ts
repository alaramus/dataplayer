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

// The same for what Quasar 2.35 reaches for: a scroll container's own
// `scrollTo`, a size watched through `ResizeObserver`, and an element animated
// through `animate`, which here finishes at once.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = function scrollTo() {}
}

if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
}

if (!Element.prototype.animate) {
  Element.prototype.animate = function animate() {
    const animation: Record<string, unknown> = {
      onfinish: null,
      cancel() {},
      finish() {},
      play() {},
      pause() {},
      reverse() {},
      addEventListener() {},
      removeEventListener() {},
    }
    animation.finished = Promise.resolve(animation)
    queueMicrotask(() => {
      const done = animation.onfinish
      if (typeof done === "function") done()
    })
    return animation as unknown as Animation
  }
}

if (!navigator.clipboard) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: async () => undefined },
  })
}
