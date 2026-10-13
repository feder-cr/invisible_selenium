# Changelog

## [Unreleased]

## [0.5.0] - 2026-10-13

The pin moves to invisible-core 44.39.0, which seals the firefox-44 engine.
Every behaviour below was read from the original - Selenium 4.51, geckodriver
0.37.1 and Firefox 151 - by asking it the same questions the tests ask.

### Changed
- **`element.text` and `is_displayed()` are Selenium's own atoms**:
  getVisibleText and isDisplayed, the copies Firefox ships, run by the engine
  in the page's process without calling any of the page's functions. On a
  bench of 24 elements the answers are the original's, 48 of 48. Until 0.4.0
  `text` was `innerText` trimmed (runs of spaces were kept) and
  `is_displayed()` was "has a box with width and height" (an element with
  opacity 0 or moved off screen was displayed, one with no height and some
  text was not).
- **`current_url` and `title` are read in the browser**, as Marionette reads
  them, so a page busy in a script answers at once; `current_url` is never
  "".
- **`is_enabled()` is Marionette's**: the element's own `:disabled`, an option
  through its group, and False for anything in an XML document; a label or
  `aria-disabled` no longer counts.
- **A dialog ends the command it opened in**, as Marionette's: a script, a
  page load, a history step or a click that opens an `alert` returns at once
  and leaves the dialog for the next command, which dismisses it and raises
  `UnexpectedAlertPresentException` 'Unexpected alert dialog detected.
  Performed handler "dismiss"' (confirm and prompt named as such). A dialog
  during an implicit wait ends `find_element` with "Failed to convert data
  to an object". `close`, `new_window`, the window rect, `maximize_window`,
  `default_content`, `frame` and `submit` meet an open dialog first; the
  window handles, `switch_to.window`, `parent_frame` and the timeouts do not.
- **`beforeunload` is accepted at once**, so it no longer holds a navigation,
  and **`close()` runs it**, as Firefox's own tab close does.
- **The cookies are the current frame's**, as Marionette reads them: a
  cookie's path counts when the document's path contains it, `secure` filters
  nothing, `sameSite` is always there ("None" when unset), `get_cookie`
  answers the last cookie of that name, an expiry is capped at 400 days, and
  `add_cookie` refuses in Marionette's words ("Document is cookie-averse",
  "Cookies may only be set for the current domain (...)"). `delete_cookie("")`
  is the client's `ValueError`.
- **`switch_to.frame(N)` counts the current frame's child browsing
  contexts** in the order they were created, an iframe in a shadow root
  included, with no implicit wait; `frame(None)` is the top document; an
  element that does not embed a child of the current frame, an element of
  another frame and a frame that went away answer Marionette's errors.
- **A body geckodriver refuses is refused in its words**, with the place in
  the JSON Selenium sends: "invalid type: integer `1`, expected a string at
  line 1 column 21" for a cookie, "data did not match any variant of
  untagged enum FrameId" for a frame index out of range. `new_window` takes
  any string as its type.
- **`Select.select_by_visible_text`** matches `normalize-space` of the
  option's text and refuses an option hidden by its style ("Invisible option
  with text: ..."); a disabled option already selected is left alone.
- **`shadow_root`** answers a closed root too, and an element without one is
  `NoSuchShadowRootException` with no message.

- **An `Alert` asks for the dialog open now at every call**, as Selenium's:
  no dialog, or one already answered, is `NoAlertPresentException` with no
  message (it was "No dialog is present", "The dialog is no longer open", or
  the old text), and `send_keys` on an alert or a confirm says "User prompt
  of type alert is not interactable".
- **`switch_to.window(name)` finds a window by its `window.name`** when no
  handle matches, as the Selenium client does. The name is read in an
  isolated world, so no script of the page sees the read.
- **An unknown locator strategy is refused in geckodriver's words**:
  "unknown variant `foo`, expected one of `css selector`, `link text`,
  `partial link text`, `tag name`, `xpath` at line 1 column 15".

### Fixed
- **`send_keys` of text with a character the US layout has no key for
  presses the keys that exist** and inserts that character in its place: it
  inserted the whole text, so a page saw "café" arrive with no keystroke.
- **The text sent to a prompt is kept until the prompt is accepted**, also
  through another `switch_to.alert`, the usual way to write it:
  `switch_to.alert.send_keys("x")` then `switch_to.alert.accept()` gave the
  page the prompt's default value.
- **On Linux, the line endings a page reads are Windows'**: a `Blob` or a
  `File` made with `endings: "native"` turns `\n` into `\r\n`, and the text
  of a selection across two blocks is joined by `\r\n`, as on Windows.
- **`speechSynthesis.getVoices()` is Windows' list**: David, Mark, Zira and
  the two Desktop voices, in that order, and none of them is the default.

### Not yet as the original
- `new_window("tab")` opens a window: every page of the engine is its own
  window, and the tab Selenium opens hides the page it came from.
- `ActionChains` moves like a person (a path, a pause) where Selenium moves
  in straight 250 ms lines, and `submit()` presses the form's control where
  Selenium fires an untrusted submit event; both are the original's shape
  and an automation signal.

## [0.4.0] - 2026-10-13

The pin moves to invisible-core 41.39.0.

### Changed
- **`click` tries once, with Marionette's checks and no others**, as
  geckodriver's element click (`webdriverClickElement`). An
  `<input type=file>` raises `InvalidArgumentException`; an element out of
  view is scrolled with `block: end` and raises
  `ElementNotInteractableException` ("could not be scrolled into view") when
  it still is not; a covered element raises `ElementClickInterceptedException`
  at once, with Marionette's message; a disabled element is clicked. Until
  0.3.7 a click waited for the element to be visible, enabled, stable and the
  topmost one at the point, and tried again until a timeout.
- **`clear` checks as Marionette's `clearElement` does, once**: a disabled,
  read-only or non-editable element raises `InvalidElementStateException` at
  once, and an element already empty is left alone, not even focused.
- **Timeouts are Selenium's `Timeouts`.** A 0 is a 0 (a page load or an
  asynchronous script then times out at once, where a 0 used to mean the
  default); `driver.timeouts = ...` sets only the fields that are not 0 and
  leaves the others; `driver.timeouts` hands back a copy; anything but a number
  is a `TypeError`. A page load past its timeout says "Navigation timed out
  after N ms".
- The implicit wait looks every 10 ms, as Marionette's.
- `switch_to.frame` does not wait for the frame's document.
- `ActionChains.key_down`, `key_up` and `send_keys_to_element` with an
  element click it with the pointer and no check, as Selenium's
  `self.click(element)`.

### Fixed
- **`back()` and `forward()` to a same-document entry (a hash, a
  `pushState`) return at once**, as `hashchange` and `popstate` end
  Marionette's wait; they gave half a second of grace first.

## [0.3.7] - 2026-10-12

The pin moves to invisible-core 41.38.0.

### Fixed
- **A script is sent once, whatever happens to its document.** 0.3.6 sent
  a script refused because its document had gone again into the document
  there was now, but the refusal does not say whether the script ran: one
  waiting on a promise when its page navigated is refused in the same words,
  and ran twice. `execute_script` now returns `None` when the document goes
  under the script, as Marionette does, and never sends it again; a script
  carrying an element of that document still raises
  `StaleElementReferenceException`.

## [0.3.6] - 2026-10-12

The pin moves to invisible-core 41.37.0.

### Fixed
- **`send_keys` types where geckodriver types.** It put the caret at the start
  of a field it focused, so a pre-filled field got the text in front of its
  value; it now focuses only an element that does not have the focus and moves
  the caret to the end, as Marionette does. An element that cannot take the
  focus raises `ElementNotInteractableException` ("is not reachable by
  keyboard") instead of the keys going wherever the focus was.
- **A click that unloads the page waits for the new one**, as geckodriver's
  does: 50 ms for the page to start unloading, 5 s for the unload, then the
  page load strategy's state within the page load timeout. A click that
  unloads nothing returns at once.
- **The page load strategy is honoured.** `Options.page_load_strategy` was
  ignored: every navigation waited for `load` and the capabilities said
  "normal". `get`, `back`, `forward`, `refresh` and a click now wait for
  `load` (normal), `DOMContentLoaded` (eager) or only for the navigation to
  start (none), and an unknown strategy raises `ValueError` as it is assigned.
- **A script sent while the page is between two documents runs in the new
  one**, as geckodriver sends it to the frame's current window; it raised
  `StaleElementReferenceException`, which with the "none" strategy was every
  script sent while a page loaded. A script carrying an element still raises
  it: the element belonged to the document that went.
- **No time limit of the engine's own.** Making a context, opening a page,
  closing one and applying a context option each had a fixed limit (30, 20 and
  10 s) that Selenium does not have, so a loaded host failed where the original
  waits. They now wait as long as the original does; the limits the API
  declares stay.
- **A browser that dies ends every wait at once.** A wait for an event - a
  page's load state, its main frame, a navigation - had nothing to wake it when
  the browser closed or crashed, so it ran to its timeout. It now raises at
  once that the target closed.

## [0.3.5] - 2026-10-12

The pin moves to invisible-core 41.36.0.

### Fixed
- **A page that replaces itself right after it loads no longer breaks the
  next call.** A read made while the page was moving on failed with the
  engine's raw "Failed to find execution context"; the core now makes such a
  read again on the page that took its place, and says so with its own error
  type when it cannot (an element of the page that is gone).
- **Frames follow the documents.** After a navigation that moved the page to
  another browser process, the old document's iframes stayed listed.
- **A `get` the browser abandons answers at once.** Called while the previous
  page's own redirect was in flight, `get` could lose to it: Firefox loads the
  redirect and drops ours without a word, and the call waited for the whole
  page-load timeout. It now raises a WebDriverException at once, `Navigation
  to "X" is interrupted by another navigation to "Y"`, as Firefox's own
  WebDriver fails it, and not as "Reached error page": nothing failed to load.

## [0.3.4] - 2026-10-11

The pin moves to invisible-core 41.35.0, which seals the firefox-41 engine.

### Fixed
- **On Linux a window covered by another one is not reported as hidden**, the
  same as on Windows: pages in a visible session covered by a second session's
  window read `document.visibilityState === "hidden"` and had their timers and
  animation frames throttled.
- **A launch gets the whole timeout it was given.** Only the wait for the
  browser to start had it; the proxy command and the last startup step after
  it had 10 and 30 seconds of their own. On a loaded machine the proxy command
  could go unanswered for 10 seconds and the launch failed with "the engine
  refused the proxy" while it still had time. One deadline now covers the
  whole startup, and running past it raises a `TimeoutError` instead of
  claiming a refusal. A launch that fails after the browser started now closes
  it and removes the session's files.

## [0.3.3] - 2026-10-11

### Fixed
- **The shutdown pings leave by the session's proxy.** At the end of a session
  longer than a minute, Firefox posts its shutdown telemetry from a separate
  process. That process took its network settings from the machine, so a
  session behind a SOCKS5 or HTTP proxy sent those pings from the machine's own
  address. With the firefox-40 engine (invisible-core 40.35.0) they go through
  the same proxy as the session, or directly when the session has none, and the
  session waits for them to finish before it removes its files: closing a long
  session takes about a second more.

## [0.3.2] - 2026-10-10

### Fixed
- **A session no longer leaves its temporary profile behind.** On Windows a
  session longer than a minute left an `invisible_profile_*` directory in
  `%TEMP%`, holding an empty `saved-telemetry-pings`: the profile was removed
  right after the browser, while the `pingsender.exe` it starts at exit still
  held a file in it. The session's directories (the core's `SessionFiles`)
  are now removed after every process of the session has ended, and a new
  session sweeps what a killed one left.
- **The browser's temporary files go with the session.** Firefox wrote into
  the system temporary directory, and a short session cut off its cleanup: a
  70 s session left a 4 MB certificate bundle in `%TEMP%`. The browser now
  gets a temporary directory of its own, removed with the profile.
- **Characters that need Shift are typed with Shift.** `@`, `!` and capital
  letters reached the page with `shiftKey` false and no Shift keydown, a
  combination no keyboard produces; with Shift held by hand, pressing `2` wrote
  `2`. They are typed with Shift down now, timed by the session's hand
  (invisible-core 39.35.0).
- **A pause before every click.** The press came one protocol round trip after
  the pointer arrived, where a hand waits a moment. The session's hand now
  pauses at the end of the approach, before the button goes down.

## [0.3.1] - 2026-10-10

### Fixed
- **Pointer actions answer once the page has handled the event.** With the
  firefox-39 engine, a press, a move or a release returns after the page's
  listeners have run. Before, the next call could reach the page first: under
  load a short drag-and-drop lost its drop, and a script read right after a
  double click could count one click short.

### Changed
- **A click that opens `alert()` is handled by the engine.** The engine ends
  its own wait when a dialog opens, so this package no longer carries a hook
  for it.

## [0.3.0] - 2026-10-09

### Changed
- **The Juggler client comes from `invisible-core`** (38.34.0,
  `invisible_core.juggler`), the one copy every invisible_ wrapper shares.
  This package carried its own, taken from invisible-playwright on
  2026-09-24, and it now has the fixes made there since:
  - typing into a field waits the moment a person takes after focusing it,
    and longer while the field is still changing, so a page that writes into
    the field when it gets the focus no longer overwrites what is typed;
  - a picked file reaches the input after the hesitation a person takes to
    choose it;
  - an action that needs no point on the screen (setting the files of a
    hidden `<input type=file>` behind a styled button, focusing or
    dispatching an event on a hidden element) no longer waits for the element
    to become visible until it times out;
  - every page of a session numbers its own clicks, fields and typed strings,
    so two tabs never draw the same movement.
- **A preference value that is not a bool, an int, a float or a string is
  refused** with a `TypeError` naming it, instead of being written as its
  text.
- **The license is MIT only.** The two files taken from Playwright's driver
  (Apache-2.0) moved to invisible-core with the client.

## [0.2.2] - 2026-10-09

### Changed
- **The window a page reads is the one Windows Firefox draws.** Through
  `invisible-core` 38.33.0 and the firefox-38 engine. A maximized window
  answers `screenX` -8 and an `outerWidth` 16 wider than `screen.availWidth`
  at 100%, as Windows Firefox does, where it answered 0 and the work area; its
  content starts where retail's does at every display scale; a popup answers
  its own size, frame and position, and one opened without a position is
  placed where Windows Firefox places it.

### Removed
- **The pins `screen.chrome_w`, `screen.chrome_h`, `screen.window_x` and
  `screen.window_y`.** The window follows `screen.dpr`, which takes 1, 1.25,
  1.5 or 2.

## [0.2.1] - 2026-10-09

### Changed
- **The screen a page reads is in CSS pixels.** Through `invisible-core`
  37.33.0 and the firefox-37 engine. A 1920x1080 panel at 125% reports
  `screen.width` 1536 and `screen.height` 864, as Firefox on that monitor
  does. Before, it reported the panel's device pixels. The default
  viewport is derived the same way.

### Fixed
- **On Linux the virtual display keeps X access control on.** The Xvfb
  display opened for a headed session without a screen used to run with
  access control off (`-ac`), so any local process could connect to it and
  read or drive the browser window. It now gets a private session cookie,
  handed only to the browser, and removed when the session stops.

## [0.2.0] - 2026-10-06

### Changed
- **The language of `locale="auto"` is the real Firefox of the egress
  country, by share.** Through `invisible-core` 36.33.0 (the required version
  is exact, as before). A country used to map to one country tag (`de-DE`)
  that no Firefox build has, so a German egress sent `de-DE,de;q=0.9,...`
  where a German Firefox sends `de,en-US;q=0.9,en;q=0.8`, and every session
  of a country spoke the same language. Now each country carries the Firefox
  builds people there run and their share, from Mozilla's Firefox Public
  Data Report (Belgium: French 40%, Dutch 31%, US English 22%), and the egress
  IP picks one: the same address always gets the same language, and the
  addresses of a country spread over its builds as measured.
- **An explicit `locale` is `navigator.language`.** `locale="en-AU"` reports
  `en-AU, en-US, en` (it reported `en-US, en`), and `"fr-FR"` reports
  `fr-FR, fr, en-US, en` (it reported `fr` first): the requested tag goes
  first and Firefox's own table gives the tail.

## [0.1.3] - 2026-10-05

### Changed
- **A session reports one language in every value.** `locale="auto"` and an
  explicit tag both go through `invisible_core.prepare_session_geo`, the same
  call that resolves the timezone, and the session keeps its result: the
  language list Firefox's own table gives that tag. `navigator.language`,
  `navigator.languages`, the locale prefs, the default context's locale, the
  `Accept-Language` header and the Google CONSENT cookie all read it. A region
  that has no Firefox build of its own used to report two languages: an
  Australian egress resolved `en-AU` for the locale prefs and `en-US, en` for
  the language list, so `navigator.language` said `en-US` while the requested
  locale said `en-AU`. It now reports `en-US` everywhere, as an English
  Firefox installed in Australia does, and the same holds for the other
  regions in that position (New Zealand, Ireland, India and more).
- **The session's default context carries the decided language**, the first
  entry of the list (`fr` for a French session, whose list is
  `fr, fr-FR, en-US, en`), not the tag that was passed.
- **The persona cookies (`prep_recaptcha=True`) come from the core**
  (`invisible_core.persona_cookies`). Same cookies for the same seed; the
  CONSENT cookie's language reads the decided language instead of the raw
  tag. The private `_recaptcha_seed` module is gone.

### Fixed
- **A context's locale reaches the engine as the language list it stands
  for.** `Browser.setLocaleOverride` carried the bare tag, so on firefox-36,
  which applies a context's locale, a context asking for `de-DE` would report
  `navigator.languages == ["de-DE"]` where a German Firefox reports
  `de-DE, de, en-US, en`, and the default context would drop from the
  profile's four entries to one. The list is the core's decision for the tag
  (`decide_session_locale(tag).accept_languages`).

### Requires
- `invisible-core` 36.32.0, which seals the firefox-36 engine and makes the
  language decision. This version does not run on an earlier core.

## [0.1.2] - 2026-10-03

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

### Fixed
- **A click lands where it was asked on a page with a saved zoom**, and on
  Linux behind a SOCKS proxy real sites see WebRTC working: both are fixes in
  the firefox-35 engine.

### Requires
- `invisible-core` 35.32.0, which seals the firefox-35 engine. This version
  does not run on firefox-34, and earlier versions do not run on firefox-35.

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
