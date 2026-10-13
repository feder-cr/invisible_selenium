"""`WebDriver`: Selenium's session API, answered by the engine directly.

⛔ THERE IS NO DRIVER PROCESS AND NO WIRE PROTOCOL. Selenium's WebDriver sends
W3C commands over HTTP to geckodriver, which drives Firefox through Marionette
- and Marionette is what turns `navigator.webdriver` on. None of that exists
here: every method below calls the engine that invisible_playwright drives
Firefox with, over the Juggler pipe, and only the CONTRACT - names, signatures,
return values, exceptions - is Selenium's.

The browser, its contexts and its pages are `invisible_core.juggler.instance`.
This class owns the Selenium-shaped state on top of them: which window and
which frame commands go to, the three timeouts, and the dialogs waiting for an
answer.
"""
from __future__ import annotations

import base64
import threading
import time
import uuid
import warnings
from typing import Any, Dict, List, Optional

from ... import _bridge
from invisible_core.juggler import domain_matches, host_of
from invisible_core.juggler.injected import ContextDestroyed
from invisible_core.juggler.lifecycle import NavigationError, NavigationInterrupted
from ...common import exceptions as exc
from ..common.by import By
from ..common.timeouts import Timeouts
from .switch_to import SwitchTo
from .webelement import WebElement


#: The load state each page load strategy waits for; "none" waits for nothing.
#: Selenium's three, as Marionette reads them (navigate.sys.mjs).
_LOAD_STATE = {"normal": "load", "eager": "domcontentloaded", "none": None}

#: How long after a click Marionette looks for the page to start unloading,
#: and how long it then gives the unload (`navigate.sys.mjs`, the unload timer
#: of `waitForNavigationCompleted`; `marionette.navigate-after-click.timeout`).
_CLICK_UNLOAD_WINDOW = 0.05
_CLICK_UNLOAD_TIMEOUT = 5.0


class WebDriver:
    """Same methods and properties as `selenium.webdriver.remote.webdriver.WebDriver`.

    Not constructed directly: `webdriver.Firefox(...)` launches the patched
    browser and hands its engine objects to `_attach`.
    """

    _web_element_cls = WebElement
    #: Selenium's page load strategy, a key of `_LOAD_STATE`: the constructor
    #: takes it from `Options.page_load_strategy`, which refuses any other.
    _page_load_strategy = "normal"

    def _attach(self, browser, context) -> None:
        self._browser = browser
        self._engine_context = context
        self.session_id = uuid.uuid4().hex
        self._page = None
        self._frame: Optional[str] = None
        self._timeouts = Timeouts(implicit_wait=0, page_load=300, script=30)
        self._dialogs: Dict[str, dict] = {}
        self._dialogs_lock = threading.Lock()
        self._watched: set = set()
        self._switch_to = SwitchTo(self)
        self._quit = False
        self.caps = {"browserName": "firefox",
                     "browserVersion": (browser.version or "").split("/")[-1],
                     "platformName": _platform_name(),
                     "acceptInsecureCerts": False,
                     "pageLoadStrategy": self._page_load_strategy,
                     # Every field, as geckodriver answers it: `_to_json`
                     # leaves out the zero ones, which is for SETTING.
                     "timeouts": {"implicit": 0, "pageLoad": 300000,
                                  "script": 30000},
                     "unhandledPromptBehavior": "dismiss and notify"}

    # ── session ─────────────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        """The name of the underlying browser for this instance."""
        return "firefox"

    @property
    def capabilities(self) -> dict:
        """The capabilities of this session."""
        return dict(self.caps)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.quit()

    def __repr__(self) -> str:
        return '<%s.%s (session="%s")>' % (type(self).__module__,
                                          type(self).__name__, self.session_id)

    def quit(self) -> None:
        """Closes the browser and ends the session."""
        if self._quit:
            return
        self._quit = True
        self._teardown()

    def _teardown(self) -> None:
        try:
            self._browser.close()
        except Exception:
            pass

    # ── windows and pages ───────────────────────────────────────────────────
    def _watch(self, page) -> None:
        """Wire one page into the session, once."""
        if page.target_id in self._watched:
            return
        self._watched.add(page.target_id)

        def on_event(method, params, page=page):
            if method == "Page.dialogOpened":
                with self._dialogs_lock:
                    self._dialogs[page.target_id] = dict(params)

        page.on_event(on_event)
        self._prepare_page(page)

    def _prepare_page(self, page) -> None:
        """A hook for the launcher: per-page engine settings."""

    def _current_page(self):
        if self._quit:
            raise exc.InvalidSessionIdException("the session has been quit")
        page = self._page
        if page is None or page not in self._engine_context.pages \
                or page.target_id not in self._engine_context.live_targets():
            raise exc.NoSuchWindowException(
                "Browsing context has been discarded")
        return page

    def _pending_dialog(self, page) -> Optional[dict]:
        with self._dialogs_lock:
            return self._dialogs.get(page.target_id)

    def _dialog_answered(self, page) -> None:
        with self._dialogs_lock:
            self._dialogs.pop(page.target_id, None)

    def _check_alert(self) -> None:
        """W3C's default for an unhandled prompt: dismiss it, and say so.

        ⛔ A command must not run under an open dialog: the page's script is
        suspended inside `alert()`, so an evaluation would wait for an answer
        nobody is going to give. Selenium's default behaviour is "dismiss and
        notify", and it is what this does.
        """
        page = self._current_page()
        dialog = self._pending_dialog(page)
        if dialog is None:
            return
        self._dialog_answered(page)
        accept = (dialog.get("type") or "") == "beforeunload"
        try:
            page.send("Page.handleDialog",
                      {"dialogId": dialog["dialogId"], "accept": accept},
                      timeout=10)
        except Exception:
            pass
        raise exc.UnexpectedAlertPresentException(
            alert_text=dialog.get("message") or "",
            msg="Dismissed user prompt dialog: %s" % (dialog.get("message") or ""))

    def _frame_id(self) -> str:
        return self._frame or self._current_page().main_frame_id

    def _select_page(self, page) -> None:
        self._watch(page)
        self._page = page
        self._frame = None

    @property
    def current_window_handle(self) -> str:
        """The handle of the current window."""
        return self._current_page().target_id

    @property
    def window_handles(self) -> List[str]:
        """The handles of every window of this session, in opening order."""
        return list(self._engine_context.live_targets())

    def _switch_window(self, handle: str) -> None:
        if handle not in self._engine_context.live_targets():
            raise exc.NoSuchWindowException("Unable to locate window: %s" % handle)
        try:
            page = self._engine_context.adopt(handle)
        except Exception as e:
            raise exc.NoSuchWindowException(str(e)) from None
        self._select_page(page)
        try:
            page.send("Page.bringToFront", {}, timeout=10)
        except Exception:
            pass

    def _new_window(self) -> None:
        self._before_new_page()
        page = self._engine_context.new_page()
        self._select_page(page)

    def _before_new_page(self) -> None:
        """A hook for the launcher: the egress check before every new tab."""

    def close(self) -> None:
        """Closes the current window. Closing the last one ends the session,
        as it does with geckodriver."""
        page = self._current_page()
        self._dialog_answered(page)
        page.close()
        deadline = time.monotonic() + 5
        while page.target_id in self._engine_context.live_targets():
            if not _bridge.poll(deadline, 0.05):
                break
        self._page = None
        if not self._engine_context.live_targets():
            self.quit()

    @property
    def switch_to(self) -> SwitchTo:
        return self._switch_to

    # ── frames ──────────────────────────────────────────────────────────────
    def _switch_frame(self, frame_id: Optional[str]) -> None:
        self._current_page()
        self._frame = frame_id

    def _enter_frame(self, element: WebElement) -> None:
        element._check_alive()
        page = element._page
        try:
            described = page.send("Page.describeNode",
                                  {"frameId": element._frame_id,
                                   "objectId": element._oid}) or {}
        except Exception as e:
            raise _bridge.translate(e) from None
        inner = described.get("contentFrameId")
        if not inner:
            raise exc.NoSuchFrameException("the element is not a frame")
        # ⛔ NOT WAITING FOR THE FRAME'S DOCUMENT, as Marionette does not
        # (`switchToFrame` takes the child browsing context and returns). Until
        # 0.3.7 this waited up to 10 s for the frame's utility world and raised
        # NoSuchFrameException when it did not come; the command that next asks
        # something of the frame waits for its world itself.
        self._frame = inner

    def _parent_frame(self) -> None:
        page = self._current_page()
        if self._frame is None:
            return
        frame = page.lifecycle.frame(self._frame)
        parent = getattr(frame, "parent", None)
        self._frame = None if parent in (None, page.main_frame_id) else parent

    # ── navigation ──────────────────────────────────────────────────────────
    def get(self, url: str) -> None:
        """Loads a web page in the current window, and waits for the state of
        the page load strategy: `load` (normal), `DOMContentLoaded` (eager),
        or only for the navigation to start (none)."""
        self._check_alert()
        page = self._current_page()
        try:
            page.lifecycle.goto(url, frame_id=page.main_frame_id,
                                until=_LOAD_STATE[self._page_load_strategy],
                                timeout=self._timeouts.page_load)
        except NavigationInterrupted as e:
            # Another document took the page before ours committed - the
            # previous page's own redirect, say. Nothing failed to load, so
            # not "Reached error page"; Firefox's own WebDriver fails it too
            # ("A new navigation interrupted an unfinished navigation").
            raise exc.WebDriverException(str(e)) from None
        except NavigationError as e:
            raise exc.WebDriverException("Reached error page: %s" % e) from None
        except TimeoutError:
            raise self._navigation_timed_out() from None
        except Exception as e:
            raise _bridge.translate(e) from None
        self._frame = None

    def _navigation_timed_out(self) -> exc.TimeoutException:
        """Marionette's words for a page load past the page load timeout
        (navigate.sys.mjs, a `TimedPromise` "Navigation timed out")."""
        return exc.TimeoutException(
            "Navigation timed out after %d ms" % self._timeouts._page_load)

    def _await_click_navigation(self, page, frame_id: str,
                                previous: Optional[str]) -> None:
        """What Marionette does after an element click: if the click starts to
        unload the page, wait for the page it unloads into.

        ⛔ UNTIL 0.3.6 A CLICK RETURNED AT ONCE, and the next line of a test -
        `find_element` with no implicit wait, `title`, `current_url` - read the
        page being left or one half loaded. Selenium's click waits (Marionette,
        `clickElement` in driver.sys.mjs, `waitForNavigationCompleted` in
        navigate.sys.mjs): 50 ms for the page to start unloading, then 5 s for
        the unload, then the page load strategy's state within the page load
        timeout. A click that unloads nothing (a button, a link with
        `target=_blank`, a hash) waits for nothing, and neither does the
        "none" strategy.
        """
        state = _LOAD_STATE.get(self._page_load_strategy)
        if state is None:
            return
        life = page.lifecycle
        navigation = life.wait_for_navigation_start(
            frame_id, previous, timeout=_CLICK_UNLOAD_WINDOW)
        if navigation is None:
            return
        limit = self._timeouts.page_load
        began = time.monotonic()
        try:
            life.wait_for_state(frame_id, "commit", navigation=navigation,
                                timeout=_CLICK_UNLOAD_TIMEOUT)
        except TimeoutError:
            return  # it started, and did not unload: Marionette stops waiting
        except NavigationInterrupted:
            pass  # another document took its place: wait for that one below
        except NavigationError as e:
            raise exc.WebDriverException("Reached error page: %s" % e) from None
        try:
            life.wait_for_state(frame_id, state,
                                timeout=max(0.0, limit - (time.monotonic() - began)))
        except TimeoutError:
            raise self._navigation_timed_out() from None

    def _history(self, command: str) -> None:
        """Back, forward, reload - and wait for the document to change, then
        for the state of the page load strategy (none: for nothing more).

        ⛔ THE MARK IS TAKEN BEFORE THE COMMAND. History gives back no
        navigationId, so the only thing to anchor the wait on is that the
        frame's navigation has moved; `Page.goBack` answers the moment the
        browser accepts the request, and waiting for `load` then returns at
        once, on the document being left.

        ⛔ A SAME-DOCUMENT ENTRY ENDS THE WAIT AT ONCE, as `hashchange` and
        `popstate` end Marionette's (navigate.sys.mjs): the core's
        `wait_for_new_navigation` answers None for it ([B290]). Until 0.3.7
        this waited for an address that moved and gave it half a second of
        grace before believing it.
        """
        self._check_alert()
        page = self._current_page()
        frame_id = page.main_frame_id
        since = page.lifecycle.mark(frame_id)
        result = page.send(command, {"frameId": frame_id}
                           if command != "Page.reload" else {}) or {}
        if command != "Page.reload" and not result.get("success"):
            return  # nothing behind or ahead: Selenium does nothing either
        state = _LOAD_STATE[self._page_load_strategy]
        try:
            navigation = page.lifecycle.wait_for_new_navigation(
                frame_id, since, state, timeout=self._timeouts.page_load)
        except TimeoutError:
            raise self._navigation_timed_out() from None
        except NavigationError as e:
            raise exc.WebDriverException(str(e)) from None
        self._frame = None
        # A new document under "normal" or "eager": its utility world is the
        # next thing asked of it. "none" waits for nothing more, and a
        # same-document entry has kept its world.
        if navigation is not None and state is not None:
            self._await_utility_world(page, frame_id)

    def _await_utility_world(self, page, frame_id: str) -> None:
        """Wait until the frame's utility world answers again.

        After a document change the old context's id can linger in the registry
        for the moment it takes the destruction event to arrive; a read in that
        moment fails with "Failed to find execution context". One trivial
        evaluation that succeeds says the world is the live one."""
        deadline = time.monotonic() + 10
        while True:
            try:
                page.injected.evaluate(frame_id, "1", timeout=5)
                return
            except Exception:
                if not _bridge.poll(deadline, 0.05):
                    return

    def back(self) -> None:
        """Goes one step backward in the browser history."""
        self._history("Page.goBack")

    def forward(self) -> None:
        """Goes one step forward in the browser history."""
        self._history("Page.goForward")

    def refresh(self) -> None:
        """Refreshes the current page."""
        self._history("Page.reload")

    def _location(self, page) -> str:
        try:
            return page.injected.evaluate(page.main_frame_id, "location.href",
                                          timeout=10) or ""
        except Exception:
            return ""

    @property
    def current_url(self) -> str:
        """The URL of the current page (the top-level document)."""
        self._check_alert()
        return self._location(self._current_page())

    @property
    def title(self) -> str:
        """The title of the current page."""
        self._check_alert()
        page = self._current_page()
        try:
            return page.injected.title(page.main_frame_id) or ""
        except Exception as e:
            raise _bridge.translate(e) from None

    @property
    def page_source(self) -> str:
        """The source of the current document (of the current frame)."""
        self._check_alert()
        page = self._current_page()
        try:
            return page.injected.content(self._frame_id())
        except Exception as e:
            raise _bridge.translate(e) from None

    # ── finding ─────────────────────────────────────────────────────────────
    def _find(self, page, frame_id: str, root, by, value, *, single: bool):
        if isinstance(by, str) and by not in _STRATEGIES:
            custom = By.get_finder(by) if hasattr(By, "get_finder") else None
            if custom is None:
                raise exc.InvalidArgumentException("unknown locator strategy %r" % by)
            by = custom
        if value is None:
            value = ""
        if root is not None:
            root._check_alive()
            root_oid = root._oid
        else:
            self._check_alert()
            root_oid = None
        deadline = time.monotonic() + self._timeouts.implicit_wait
        while True:
            try:
                if root_oid is None:
                    found = page.injected.in_current_world(
                        lambda _: _bridge.query(page, frame_id, None, by, str(value)),
                        timeout=30)
                else:
                    found = _bridge.query(page, frame_id, root_oid, by, str(value))
            except exc.WebDriverException:
                raise
            except Exception as e:
                raise _bridge.translate(e) from None
            # Every 10 ms, as Marionette's `PollPromise` (sync.sys.mjs).
            if found or not _bridge.poll(deadline, 0.01):
                break
        elements = [self._web_element_cls(self, page, frame_id, oid)
                    for oid in found]
        if not single:
            return elements
        if not elements:
            raise exc.NoSuchElementException(
                "Unable to locate element: %s" % value)
        for extra in found[1:]:
            page.injected.release(page.injected.context_id(frame_id), extra)
        return elements[0]

    def find_element(self, by=By.ID, value: Optional[str] = None) -> WebElement:
        """Find an element given a By strategy and locator."""
        page = self._current_page()
        return self._find(page, self._frame_id(), None, by, value, single=True)

    def find_elements(self, by=By.ID, value: Optional[str] = None) -> List[WebElement]:
        """Find elements given a By strategy and locator."""
        page = self._current_page()
        return self._find(page, self._frame_id(), None, by, value, single=False)

    def _active_element(self) -> WebElement:
        self._check_alert()
        page = self._current_page()
        frame_id = self._frame_id()
        ctx = page.injected.context_id(frame_id)
        remote = page.injected.call_raw(
            ctx, "() => document.activeElement || document.body", [])
        if "objectId" not in remote:
            raise exc.NoSuchElementException("no element has focus")
        return self._web_element_cls(self, page, frame_id, remote["objectId"])

    # ── scripts ─────────────────────────────────────────────────────────────
    def execute_script(self, script, *args):
        """Runs JavaScript in the current window or frame, as the page does.

        `arguments` inside the script are the values passed here, elements
        included; the result comes back as Python values, with elements as
        WebElements. A returned promise is awaited, as W3C specifies.
        """
        return self._run_script(script, args, is_async=False)

    def execute_async_script(self, script: str, *args):
        """Runs asynchronous JavaScript: the last argument is a callback the
        script calls with its result."""
        return self._run_script(script, args, is_async=True)

    def _run_script(self, script, args, *, is_async: bool):
        self._check_alert()
        page = self._current_page()
        frame_id = self._frame_id()
        if not isinstance(script, str):
            script = getattr(script, "script", None) or str(script)
        timeout = self._timeouts.script
        # ⛔ A SCRIPT IS SENT ONCE, WHATEVER HAPPENS TO ITS DOCUMENT. A world
        # that went under it does not say whether it ran: Juggler sends a
        # message still waiting for its answer again to the document that
        # replaces the one it went to, so a script waiting on a promise when
        # its page navigated is refused by the new page in the same words as
        # one that never ran. 0.3.6 sent it again into the new page, which ran
        # it twice ([B285]). Marionette never sends `executeScript` again and
        # answers null (`NO_RETRY_METHODS`, `MarionetteCommandsParent.sys.mjs`);
        # so does this. A script carrying an element is stale: the element
        # belonged to the document that went.
        marshal = _bridge.Marshal(self, page, frame_id)
        try:
            try:
                protocol_args, nested = marshal.arguments(args)
            except ContextDestroyed as e:
                raise _bridge.translate(e) from None
            declaration = _bridge.script_declaration(script, nested,
                                                     is_async=is_async)
            try:
                remote = page.injected.call_raw(marshal.ctx, declaration,
                                                protocol_args,
                                                timeout=timeout + 1)
            except ContextDestroyed as e:
                if any("objectId" in a for a in protocol_args):
                    raise _bridge.translate(e) from None
                return None
            try:
                return marshal.result(remote)
            except ContextDestroyed:
                return None  # it ran, and its document went before the answer
        except TimeoutError:
            raise exc.TimeoutException(
                "Timed out after %s ms" % int(timeout * 1000)) from None
        except exc.WebDriverException:
            raise
        except Exception as e:
            error = _bridge.translate(e)
            if isinstance(error, exc.TimeoutException):
                raise exc.TimeoutException(
                    "Timed out after %s ms" % int(timeout * 1000)) from None
            raise error from None
        finally:
            marshal.release()

    # ── cookies ─────────────────────────────────────────────────────────────
    def _document_cookies(self) -> List[dict]:
        url = self.current_url
        host = host_of(url)
        path = _path_of(url)
        secure = url.startswith("https:")
        out = []
        for c in self._engine_context.cookies():
            if not domain_matches(c.get("domain") or "", host):
                continue
            cpath = c.get("path") or "/"
            if not path.startswith(cpath):
                continue
            if c.get("secure") and not secure:
                continue
            out.append(c)
        return out

    def get_cookies(self) -> List[dict]:
        """The cookies visible to the current document."""
        return [_to_selenium_cookie(c) for c in self._document_cookies()]

    def get_cookie(self, name) -> Optional[Dict]:
        """A single cookie by name, or None."""
        if not name or not str(name).strip():
            raise ValueError("Cookie name cannot be empty")
        for c in self.get_cookies():
            if c["name"] == name:
                return c
        return None

    def add_cookie(self, cookie_dict) -> None:
        """Adds a cookie to the current document's domain."""
        if "sameSite" in cookie_dict and cookie_dict["sameSite"] not in (
                "Strict", "Lax", "None"):
            raise AssertionError("Invalid sameSite value")
        if "name" not in cookie_dict or "value" not in cookie_dict:
            raise exc.InvalidArgumentException("a cookie needs a name and a value")
        url = self.current_url
        if not url.startswith(("http:", "https:")):
            raise exc.InvalidCookieDomainException(
                "cookies can only be set on an http(s) document, not %s" % url)
        host = host_of(url)
        domain = cookie_dict.get("domain") or host
        if not domain_matches(domain, host):
            raise exc.InvalidCookieDomainException(
                "Cookie domain %r does not match the current document" % domain)
        cookie = {"name": str(cookie_dict["name"]),
                  "value": str(cookie_dict["value"]),
                  "domain": domain,
                  "path": cookie_dict.get("path") or "/",
                  "secure": bool(cookie_dict.get("secure", False)),
                  "httpOnly": bool(cookie_dict.get("httpOnly", False))}
        # ⛔ A SESSION COOKIE IS SENT WITHOUT `expires`, never with -1. Juggler
        # reads -1 as "session" and ALSO passes `-1 * 1000` ms as the expiry,
        # a moment in 1969, so the cookie service drops the cookie without an
        # error (`TargetRegistry.js`, `setCookies`). Omitted, the engine gives
        # it a far expiry and still marks it as a session cookie.
        if cookie_dict.get("expiry") is not None:
            cookie["expires"] = int(cookie_dict["expiry"])
        if cookie_dict.get("sameSite"):
            cookie["sameSite"] = cookie_dict["sameSite"]
        try:
            self._engine_context.set_cookies([cookie])
        except Exception as e:
            raise exc.UnableToSetCookieException(str(e)) from None

    def delete_cookie(self, name) -> None:
        """Deletes the cookie with this name, visible to the current document.

        ⛔ BY EXPIRING IT, because Juggler has no command to delete one cookie:
        `Browser.clearCookies` empties the whole context, which is more than
        Selenium's contract allows.
        """
        doomed = [c for c in self._document_cookies() if c.get("name") == name]
        self._expire(doomed)

    def delete_all_cookies(self) -> None:
        """Deletes every cookie visible to the current document - and only
        those, which is Selenium's contract; other sites keep theirs."""
        self._expire(self._document_cookies())

    def _expire(self, cookies: List[dict]) -> None:
        if not cookies:
            return
        gone = []
        for c in cookies:
            entry = {k: c[k] for k in ("name", "domain", "path", "secure",
                                       "httpOnly", "sameSite") if k in c}
            entry["value"] = ""
            entry["expires"] = 1
            gone.append(entry)
        self._engine_context.set_cookies(gone)

    # ── timeouts ────────────────────────────────────────────────────────────
    # ⛔ THE THREE SETTERS TAKE WHAT `float()` TAKES, AS SELENIUM'S DO
    # (`int(float(time_to_wait) * 1000)`): a string of digits is accepted and
    # None is a TypeError. A 0 is a 0: the page load and an asynchronous
    # script then time out at once, where until 0.3.7 a 0 meant the default.
    def implicitly_wait(self, time_to_wait: float) -> None:
        """How long `find_element` keeps looking before giving up."""
        self._timeouts.implicit_wait = float(time_to_wait)

    def set_script_timeout(self, time_to_wait: float) -> None:
        """How long a script may run before a TimeoutException."""
        self._timeouts.script = float(time_to_wait)

    def set_page_load_timeout(self, time_to_wait: float) -> None:
        """How long a page load may take before a TimeoutException."""
        self._timeouts.page_load = float(time_to_wait)

    @property
    def timeouts(self) -> Timeouts:
        """The session's timeouts, as a new object: setting a value on it does
        not change the session, as in Selenium."""
        return Timeouts(self._timeouts.implicit_wait, self._timeouts.page_load,
                        self._timeouts.script)

    @timeouts.setter
    def timeouts(self, timeouts: Timeouts) -> None:
        """Sets the fields of `timeouts` that are not 0, and leaves the others
        as they are: Selenium sends `timeouts._to_json()`, which names only
        those."""
        sent = timeouts._to_json()
        if "implicit" in sent:
            self._timeouts.implicit_wait = sent["implicit"] / 1000
        if "pageLoad" in sent:
            self._timeouts.page_load = sent["pageLoad"] / 1000
        if "script" in sent:
            self._timeouts.script = sent["script"] / 1000

    def _action_timeout(self) -> float:
        """How long an element action may spend on the engine's own waits.

        ⛔ NOT HOW LONG IT RETRIES: `click` and `clear` try once, with
        Marionette's checks, as geckodriver does. What this bounds is what the
        engine adds on top of the original and the original does not have: the
        typing persona's pause before the first key, which starts again from
        every change the field shows, and the remaining engine actions that
        still go through its loop (`submit`'s Enter, a file input's files).
        Bounded by the implicit wait, and never shorter than a few seconds."""
        return max(5.0, self._timeouts.implicit_wait)

    # ── screenshots ─────────────────────────────────────────────────────────
    def _screenshot_clip(self, page, clip: dict) -> str:
        try:
            result = page.send("Page.screenshot", {
                "mimeType": "image/png", "clip": clip,
                "omitDeviceScaleFactor": False}) or {}
        except Exception as e:
            raise exc.ScreenshotException(str(e)) from None
        return result.get("data") or ""

    def get_screenshot_as_base64(self) -> str:
        """A screenshot of the current viewport, as a base64 PNG.

        ⛔ THE CLIP IS IN DOCUMENT COORDINATES, so the viewport is placed where
        the page is scrolled to; a clip at (0, 0) would photograph the top of
        the document whatever the reader is looking at."""
        self._check_alert()
        page = self._current_page()
        box = page.injected.evaluate(
            page.main_frame_id,
            "({x: window.scrollX, y: window.scrollY,"
            " width: window.innerWidth, height: window.innerHeight})") or {
                "x": 0, "y": 0, "width": 1280, "height": 720}
        return self._screenshot_clip(page, box)

    def get_screenshot_as_png(self) -> bytes:
        return base64.b64decode(self.get_screenshot_as_base64().encode("ascii"))

    def get_screenshot_as_file(self, filename) -> bool:
        if not str(filename).lower().endswith(".png"):
            warnings.warn("name used for saved screenshot does not match file "
                          "type. It should end with a `.png` extension",
                          UserWarning, stacklevel=2)
        png = self.get_screenshot_as_png()
        try:
            with open(filename, "wb") as f:
                f.write(png)
        except OSError:
            return False
        return True

    def save_screenshot(self, filename) -> bool:
        return self.get_screenshot_as_file(filename)

    # ── the window ──────────────────────────────────────────────────────────
    def get_window_rect(self) -> dict:
        """The window's position and outer size."""
        page = self._current_page()
        return page.injected.evaluate(
            page.main_frame_id,
            "({x: window.screenX, y: window.screenY,"
            " width: window.outerWidth, height: window.outerHeight})")

    def get_window_size(self, windowHandle: str = "current") -> dict:
        r = self.get_window_rect()
        return {"width": r["width"], "height": r["height"]}

    def get_window_position(self, windowHandle="current") -> dict:
        r = self.get_window_rect()
        return {"x": r["x"], "y": r["y"]}

    def set_window_size(self, width, height, windowHandle: str = "current") -> None:
        """Resizes the window so its OUTER size is width x height."""
        page = self._current_page()
        chrome = page.injected.evaluate(
            page.main_frame_id,
            "({w: window.outerWidth - window.innerWidth,"
            " h: window.outerHeight - window.innerHeight})") or {"w": 0, "h": 0}
        page.send("Page.setViewportSize", {"viewportSize": {
            "width": max(1, int(width) - int(chrome["w"])),
            "height": max(1, int(height) - int(chrome["h"]))}})

    def set_window_rect(self, x=None, y=None, width=None, height=None) -> dict:
        if (x is not None or y is not None) and width is None and height is None:
            raise exc.WebDriverException(
                "moving the window is not supported: the window position is "
                "part of the screen geometry the profile declares")
        if width is not None and height is not None:
            self.set_window_size(width, height)
        return self.get_window_rect()

    def set_window_position(self, x, y, windowHandle: str = "current") -> dict:
        return self.set_window_rect(x=x, y=y)

    def maximize_window(self) -> None:
        """Brings the window back to the size the profile declares, which is
        already a maximized window on the declared screen."""
        page = self._current_page()
        viewport = (self._engine_context.options or {}).get("viewport")
        if viewport:
            page.send("Page.setViewportSize", {"viewportSize": dict(viewport)})

    def minimize_window(self) -> None:
        raise exc.WebDriverException(
            "minimize_window is not supported: a minimized window stops "
            "painting, and a page can tell")

    def fullscreen_window(self) -> None:
        raise exc.WebDriverException(
            "fullscreen_window is not supported: it changes the screen "
            "geometry the profile declares")

    # ── the rest of Selenium's surface, refused by name ─────────────────────
    def print_page(self, print_options=None) -> str:
        raise exc.UnknownMethodException("print_page is not supported")

    def get_log(self, log_type):
        raise exc.UnknownMethodException("get_log is not supported")

    @property
    def log_types(self):
        return []

    def start_client(self) -> None:
        """Called before starting a session. Nothing to do here."""

    def stop_client(self) -> None:
        """Called after ending a session. Nothing to do here."""


_STRATEGIES = {"id", "xpath", "link text", "partial link text", "name",
               "tag name", "class name", "css selector"}


def _path_of(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).path or "/"


def _to_selenium_cookie(c: dict) -> dict:
    out = {"name": c.get("name"), "value": c.get("value"),
           "path": c.get("path") or "/", "domain": c.get("domain"),
           "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly"))}
    expires = c.get("expires")
    if expires is not None and not c.get("session") and float(expires) > 0:
        out["expiry"] = int(expires)
    if c.get("sameSite"):
        out["sameSite"] = c["sameSite"]
    return out


def _platform_name() -> str:
    import sys
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


__all__ = ["WebDriver"]
