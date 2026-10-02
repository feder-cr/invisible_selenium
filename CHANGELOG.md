# Changelog

## [Unreleased]

### Changed
- **Values a user picks are committed by Firefox itself.** `Select`, a click
  on an `<option>`, `send_keys` on a file input and `clear()` on a date or time
  field hand the choice to the engine's native input commands
  (`Page.selectOptions`, `Page.setUserInput`, `Page.setFileInputFiles`), which
  take the same paths as the dropdown, the date box and the file picker. The
  page gets `input` and `change` with the shape a user's pick gives, inside
  shadow roots too, and nothing when the choice did not change. The command
  this used to call, `Page.dispatchTrustedInputEvents`, is gone from the
  engine, so this needs the engine that ships the new commands and lands with
  the core pin that seals it.

## [0.1.1] - 2026-10-02

### Fixed
- **`clear()` leaves the field, and `change` comes from Firefox, once.** It
  deleted the text and then asked the engine for a `change` while the field
  still had focus: cancelable and composed, followed by Firefox's own at the
  next blur, and sent even to a contenteditable, which never fires one. Inside
  a shadow root that request failed and `clear()` raised after emptying the
  field. It now runs Selenium's unfocusing step after the Delete, so `change`
  comes from the blur, as it does for a user.
- **On Linux, a headless session starts on its own virtual display.** The
  display counted as ready as soon as its lockfile existed, which Xvfb writes
  before it opens its sockets, so sessions started together could land on
  each other's display and the browser failed with `cannot open display`.
  The display is also no longer reachable over TCP.

### Requires
- `invisible-core` 34.32.0, which carries the display fix. Same engine
  (firefox-34).

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
