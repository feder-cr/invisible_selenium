# Changelog

## [0.1.1] - 2026-10-02

### Fixed
- **`clear()` leaves the field, and `change` comes from Firefox, once.** It
  deleted the text and then asked the engine for a `change` while the field
  still had focus: cancelable and composed, followed by Firefox's own at the
  next blur, and sent even to a contenteditable, which never fires one. Inside
  a shadow root that request failed and `clear()` raised after emptying the
  field. It now runs Selenium's unfocusing step after the Delete, so `change`
  comes from the blur, as it does for a user.

## [0.1.0] - 2026-09-25

First version: a replica of invisible_playwright 0.25.7 with Selenium's contract.

- `webdriver.Firefox` launches the same patched Firefox with the same profile,
  proxy, geography and hidden-surface handling as `InvisiblePlaywright`, and
  drives it over Juggler: no geckodriver, no Marionette, `navigator.webdriver`
  stays false.
- Selenium's public API: `WebDriver`, `WebElement`, `ShadowRoot`, `SwitchTo`,
  `Alert`, `ActionChains`, `ScrollOrigin`, `By`, `Keys`, `WebDriverWait`,
  `expected_conditions`, `Select`, `Timeouts` and the exception hierarchy.
- Every click, hover and drag travels along a path drawn from the session seed;
  keys carry the session's typing rhythm; input events are trusted.
- `execute_script` runs in the page's world and reads its result back through
  the engine's Debugger, without running a serializer the page can observe.
