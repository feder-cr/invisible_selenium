"""`is_enabled`, `Select` and `shadow_root` as the original answers them, on a
real engine.

Every expectation here was answered by the original - Selenium 4.51,
geckodriver 0.37.1 and retail Firefox 151 - on 2026-10-13. What 0.4.0 did
instead:

- `is_enabled` was the engine's Playwright idea of enabled, which follows a
  label to its control and reads `aria-disabled`; Marionette answers
  `dom.isDisabled` of the element itself, an option through its group, and
  False for any element of an XML document;
- `select_by_visible_text` compared the visible text and never looked at
  whether the option could be seen; Selenium matches `normalize-space` of the
  option's text content and refuses an option hidden by its style;
- a disabled option that was already selected was refused before Selenium
  looks at whether it needs selecting;
- an element with no shadow root said so in words of its own, where the
  original's NoSuchShadowRootException has no message.
"""
from __future__ import annotations

import http.server
import threading

import pytest

from invisible_selenium.common import exceptions as exc
from invisible_selenium.webdriver.common.by import By
from invisible_selenium.webdriver.support.select import Select

pytestmark = pytest.mark.e2e

ENABLED = b"""<!doctype html><body>
<button disabled><span id=span>in a disabled button</span></button>
<label id=label for=dis>label</label><input id=dis disabled>
<button id=aria aria-disabled=true>aria</button>
<select id=dsel disabled><option id=dopt>x</option></select>
<select><optgroup id=dgrp disabled><option id=gopt>y</option></optgroup></select>
<fieldset disabled><input id=infs></fieldset>
</body>"""
SELECT = b"""<!doctype html><body>
<select id=s>
<option value=a>  alpha   one </option>
<option value=h style="display:none">hidden</option>
<option value=v style="visibility:hidden">vis</option>
<option value=o style="opacity:0">opa</option>
<option value=b selected disabled>bee</option>
<option value=t>two  words</option>
</select>
<select id=m multiple>
<option value=x>ex</option><option value=y style="display:none">why</option>
</select>
</body>"""
SHADOW = b"""<!doctype html><body>
<div id=open></div><div id=closed></div><div id=none></div>
<input id=date type=date><video id=video controls></video>
<script>
document.getElementById('open').attachShadow({mode: 'open'}).innerHTML = '<p>o</p>';
document.getElementById('closed').attachShadow({mode: 'closed'}).innerHTML = '<p>c</p>';
</script></body>"""
XML = b"<?xml version='1.0'?><root><item>x</item></root>"


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ctype = "text/html; charset=utf-8"
            body = {"/enabled": ENABLED, "/select": SELECT,
                    "/shadow": SHADOW}.get(self.path, b"<p>x</p>")
            if self.path == "/doc.xml":
                body, ctype = XML, "application/xml"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % srv.server_address[1]
    srv.shutdown()


@pytest.fixture(scope="module")
def driver(firefox_binary):
    from invisible_selenium import webdriver
    d = webdriver.Firefox(seed=4272, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


@pytest.mark.parametrize("element, enabled", [
    ("span", True), ("label", True), ("aria", True), ("dis", False),
    ("dopt", False), ("gopt", False), ("dgrp", False), ("infs", False),
])
def test_is_enabled_is_the_elements_own(driver, site, element, enabled):
    driver.get(site + "enabled")
    assert driver.find_element(By.ID, element).is_enabled() is enabled


def test_nothing_in_an_xml_document_is_enabled(driver, site):
    driver.get(site + "doc.xml")
    assert driver.find_element(By.TAG_NAME, "item").is_enabled() is False
    assert driver.find_element(By.TAG_NAME, "root").is_enabled() is False


def test_select_by_visible_text_as_selenium(driver, site):
    driver.get(site + "select")
    s = Select(driver.find_element(By.ID, "s"))
    # Already selected and disabled: nothing to do, no refusal.
    s.select_by_visible_text("bee")
    assert s.first_selected_option.get_attribute("value") == "b"
    s.select_by_visible_text("alpha one")
    assert s.first_selected_option.get_attribute("value") == "a"
    for hidden in ("hidden", "vis", "opa"):
        with pytest.raises(exc.NoSuchElementException,
                           match="^Message: Invisible option with text: %s;" % hidden):
            s.select_by_visible_text(hidden)
    with pytest.raises(NotImplementedError, match="^You may not select a disabled option$"):
        s.select_by_visible_text("bee")
    s.select_by_visible_text("two words")
    assert s.first_selected_option.get_attribute("value") == "t"
    with pytest.raises(exc.NoSuchElementException,
                       match="^Message: Could not locate element with visible text: two  words;"):
        s.select_by_visible_text("two  words")
    m = Select(driver.find_element(By.ID, "m"))
    with pytest.raises(exc.NoSuchElementException,
                       match="^Message: Invisible option with text: why;"):
        m.deselect_by_visible_text("why")


@pytest.mark.parametrize("element", ["open", "closed"])
def test_an_open_or_closed_shadow_root_is_returned(driver, site, element):
    driver.get(site + "shadow")
    root = driver.find_element(By.ID, element).shadow_root
    assert root.find_element(By.CSS_SELECTOR, "p").text in ("o", "c")


@pytest.mark.parametrize("element", ["none", "date", "video"])
def test_no_shadow_root_is_an_exception_with_no_message(driver, site, element):
    driver.get(site + "shadow")
    with pytest.raises(exc.NoSuchShadowRootException) as caught:
        driver.find_element(By.ID, element).shadow_root
    assert caught.value.msg == ""
