"""`webdriver.Firefox`: the patched Firefox, launched and driven over Juggler.

⛔ THIS IS invisible_playwright's LAUNCHER, ADAPTED. `launcher.py` there
resolves the session's geography and locale, the sealed executable, the hidden
surface, the fingerprint prefs, the proxy and the process token, then hands
them to Playwright's `firefox.launch()`. Here the same steps run in the same
order - through the same `CommonLaunch` - and the result goes to the engine's
`launch()` directly, with no Playwright client and no driver process. What the
caller gets back is Selenium's WebDriver.

The constructor keeps Selenium's first three parameters (`options`, `service`,
`keep_alive`), so `webdriver.Firefox()` and `webdriver.Firefox(options=opts)`
work unchanged, and adds invisible_playwright's keyword arguments after them.
"""
from __future__ import annotations

import secrets
import time
import warnings
from pathlib import Path
from typing import Any, Dict, Optional, Union

from invisible_core import configure_proxy as _configure_proxy_shared
from invisible_core import prepare_session_geo
from invisible_core._fpforge import Profile, generate_profile

from ... import _session
from ..._engine import assert_wire_version, resolve_executable
from ..._humanize import ENGINE_BINARY, resolve_cursor_engine
from ..._juggler.browser import launch as launch_engine
from ..._reaper import SessionToken, guard_for
from ...common import exceptions as exc
from ..remote.webdriver import WebDriver as RemoteWebDriver
from .options import Options
from .service import Service


def _motion_available() -> bool:
    """Whether the session's path generator can run in this process."""
    try:
        from ..._motion import CursorMotion  # noqa: F401
    except Exception:
        return False
    return True


class WebDriver(_session.CommonLaunch, RemoteWebDriver):
    """Launches the patched Firefox with a deterministic profile.

    Usage::

        from invisible_selenium import webdriver
        from invisible_selenium.webdriver.common.by import By

        driver = webdriver.Firefox(seed=42)
        driver.get("https://example.com")
        driver.find_element(By.CSS_SELECTOR, "a").click()
        driver.quit()

    Args:
        options: Selenium's `FirefoxOptions`. `-headless` among its arguments
            means ``headless=True``, its preferences are layered on the
            profile's prefs, `binary_location` is ``binary_path``, and every
            other argument reaches the browser's command line.
        service: accepted for signature parity and not used: there is no
            geckodriver.
        keep_alive: accepted for signature parity; there is no HTTP connection
            to keep alive.
        seed, pin, headless, proxy, extra_args, humanize, locale, timezone,
        extra_prefs, binary_path, profile_dir, prep_recaptcha, show_cursor:
            the same arguments, with the same meaning, as invisible_playwright's
            ``InvisiblePlaywright``.
    """

    def __init__(
        self,
        options: Optional[Options] = None,
        service: Optional[Service] = None,
        keep_alive: bool = True,
        *,
        seed: Optional[int] = None,
        pin: Optional[Dict[str, Any]] = None,
        headless: bool = False,
        proxy: Optional[Dict[str, str]] = None,
        extra_args: Optional[list[str]] = None,
        humanize: Union[bool, float] = True,
        locale: str = "auto",
        timezone: str = "",
        extra_prefs: Optional[Dict[str, Any]] = None,
        binary_path: Optional[str] = None,
        profile_dir: Optional[Union[str, Path]] = None,
        prep_recaptcha: bool = False,
        show_cursor: Optional[bool] = None,
    ) -> None:
        if service is not None and getattr(service, "path", None):
            warnings.warn(
                "invisible_selenium drives Firefox over its own pipe and starts "
                "no geckodriver: the Service's executable is not used",
                RuntimeWarning, stacklevel=2)
        extra_args = list(extra_args or [])
        extra_prefs = dict(extra_prefs or {})
        if options is not None:
            for arg in options.arguments:
                if arg in ("-headless", "--headless"):
                    headless = True
                else:
                    extra_args.append(arg)
            prefs_from_options = dict(options.preferences)
            prefs_from_options.update(extra_prefs)
            extra_prefs = prefs_from_options
            if options.binary_location and not binary_path:
                binary_path = options.binary_location

        # Everything below mirrors invisible_playwright's `launcher.py`
        # `__init__`, whose comments say why each field exists.
        # `zoom.stealth.fpp.hw_seed` is int32_t, so the seed stays in int31.
        self.seed: int = int(seed) if seed is not None else secrets.randbits(31)
        self._pin = pin
        self._headless = headless
        self._proxy = proxy
        self._extra_args = extra_args
        self._humanize = humanize
        self._cursor_engine = resolve_cursor_engine(humanize, _motion_available)
        self._show_cursor = (None if show_cursor is None
                             else bool(show_cursor))
        self._locale = locale
        self._timezone = timezone
        self._extra_prefs = extra_prefs or None
        self._binary_path = binary_path
        self._profile_dir: Optional[Path] = Path(profile_dir) if profile_dir else None
        self._prep_recaptcha = bool(prep_recaptcha) and self._profile_dir is None
        self._profile: Profile = generate_profile(self.seed, pin=self._pin)
        self._virtual_display: Any = None
        self._session_token = SessionToken()
        self._lifetime_guard = guard_for()
        self._webrtc_egress_ip: Optional[str] = None
        self._srflx_declared: Optional[str] = None
        self._ultimo_controllo_uscita: float = 0.0
        self._uscite_non_misurabili: int = 0
        self._engine_browser = None

        try:
            self._launch()
        except BaseException:
            self._teardown()
            raise

    # ── the launch ──────────────────────────────────────────────────────────
    def _launch(self) -> None:
        """invisible_playwright's `__enter__`, with the engine at the end.

        ⛔ THE ORDER IS THE ORIGINAL'S AND IT IS NOT COSMETIC. The geography
        comes first because the timezone and the WebRTC declaration feed the
        prefs; the hidden surface is created before the prefs because B172's
        sandbox workarounds depend on whether it really exists; the token is
        minted before the environment because the environment carries it.
        """
        geo = prepare_session_geo(self._timezone, self._proxy)
        self._timezone = geo.timezone
        self._webrtc_egress_ip = geo.egress_ip
        self._srflx_declared = geo.srflx_to_declare()
        if (self._locale or "").strip().lower() == "auto":
            from invisible_core import resolve_session_locale
            self._locale = resolve_session_locale(geo.egress_ip, self._proxy)
        executable = resolve_executable(self._binary_path)
        true_headless = self._resolve_headless()
        prefs = self._build_prefs()
        engine_proxy = _configure_proxy_shared(self._proxy, prefs)
        self._session_token = SessionToken.mint()
        env = self._build_env(prefs)

        if self._profile_dir is not None:
            self._profile_dir.mkdir(parents=True, exist_ok=True)
        browser = launch_engine(
            str(executable), prefs=prefs,
            profile_dir=str(self._profile_dir) if self._profile_dir else None,
            env=env, args=self._extra_args, headless=true_headless,
            proxy=engine_proxy)
        self._engine_browser = browser
        # Free post-launch wire check: the version comes from the engine
        # itself, so a hand-edited application.ini cannot pass it.
        assert_wire_version(browser)
        self._bind_process_tree()

        options = self._default_context_options()
        if self._profile_dir is not None:
            # The profile's own context: its cookies and storage persist.
            context = browser.default_context(options)
        else:
            context = browser.new_context(options)
        if self._prep_recaptcha:
            from ..._recaptcha_seed import seed_recaptcha_cookies
            seed_recaptcha_cookies(context, self._profile, locale=self._locale)
        self._attach(browser, context)

        # A persistent profile opens with a window of its own; reuse it rather
        # than leaving a blank tab beside the one the caller drives.
        existing = context.live_targets()
        if existing:
            page = context.adopt(existing[0])
        else:
            self._before_new_page()
            page = context.new_page()
        self._select_page(page)

    def _prepare_page(self, page) -> None:
        """⛔ WITH `INVPW_CURSOR_ENGINE=binary` THE BROWSER DRAWS THE PATH, so
        the engine must not draw one too: every waypoint it sent would be
        expanded again into a path of its own. The approach then goes out as
        one event, which the browser's own motion turns into a movement."""
        if self._cursor_engine == ENGINE_BINARY:
            page.actions.motion = None

    def _before_new_page(self) -> None:
        self._assert_uscita_invariata()

    # ── the egress guard, from invisible_playwright's launcher ──────────────
    #: At most how often the egress is rechecked: the check costs one request
    #: THROUGH the proxy, i.e. the user's bandwidth.
    _INTERVALLO_CONTROLLO_USCITA_S = 120.0

    #: How many silent probes in a row before the session is refused.
    _MAX_USCITE_NON_MISURABILI = 3

    def _assert_uscita_invariata(self) -> None:
        """Refuses if the egress IP has changed since launch.

        The IP declared to the engine for the WebRTC srflx candidate was
        photographed at launch; if the egress moves, the page exits from one
        address and WebRTC announces another - the disagreement detectors look
        for. The full reasoning is on the original in invisible_playwright's
        `launcher.py`.
        """
        if not self._proxy or not self._webrtc_egress_ip:
            return
        now = time.monotonic()
        if now - self._ultimo_controllo_uscita < self._INTERVALLO_CONTROLLO_USCITA_S:
            return
        self._ultimo_controllo_uscita = now
        outcome, current = _session.egress_ancora_valido(
            self._proxy, self._webrtc_egress_ip)
        if outcome == _session.USCITA_DERIVATA:
            raise _session.ProxyEgressDrifted(
                "the proxy's egress IP changed during the session: it was %s "
                "at launch, now it is %s. The WebRTC srflx candidate still "
                "declares the first one, so from this moment the page exits "
                "from one address and WebRTC announces another. Use a proxy "
                "that holds the session sticky, or shorten the session."
                % (self._webrtc_egress_ip, current))
        if outcome == _session.USCITA_NON_MISURABILE:
            self._uscite_non_misurabili += 1
            if self._uscite_non_misurabili >= self._MAX_USCITE_NON_MISURABILI:
                raise _session.ProxyEgressNonVerificabile(
                    "the egress IP was not verifiable for %d checks in a row: "
                    "the engine would keep declaring an address nobody "
                    "confirms. Check that the proxy is reachable, then "
                    "relaunch the session." % self._uscite_non_misurabili)
            return
        self._uscite_non_misurabili = 0

    # ── the end ─────────────────────────────────────────────────────────────
    def _teardown(self) -> None:
        """Close the browser, the hidden surface, and anything left of the
        process tree - in that order, each step on its own.

        ⛔ LAST, AND UNCONDITIONALLY: nothing carrying this session's token may
        outlive it. Each step is wrapped, so a browser that refused to close
        would otherwise be swallowed and leak in silence; only processes
        positively identified as ours are touched."""
        if self._engine_browser is not None:
            try:
                self._engine_browser.close()
            except Exception:
                pass
            self._engine_browser = None
        if self._virtual_display is not None:
            try:
                self._virtual_display.stop()
            except Exception:
                pass
            self._virtual_display = None
        if self._session_token:
            try:
                self._lifetime_guard.reap(self._session_token)
            except Exception:
                pass
            self._session_token = SessionToken()


__all__ = ["WebDriver"]
