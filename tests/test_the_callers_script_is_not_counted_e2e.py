"""Your script runs in a world of its own, where a page that replaced a
standard API cannot count its calls [B322].

Until firefox-49 `execute_script` ran in the page's own realm, so a call to a
standard API went through whatever the page had put in its place. A Cloudflare
challenge wraps `Document.prototype.querySelector` in a Proxy, and one lookup
of its token field from a script got the clearance refused on the reload. The
script now runs in invisible-core's caller's world: a name the standard defines
is the native one, every other name is the page's. This test holds both halves
on a page that counts every call to the APIs it wrapped.
"""
from __future__ import annotations

import http.server
import threading

import pytest

from invisible_selenium.webdriver.common.by import By

pytestmark = pytest.mark.e2e

PAGE = b"""<!doctype html><html><head><script>
window.__calls = 0;
function wrap(owner, name) {
  const real = owner[name];
  Object.defineProperty(owner, name, {configurable: true, writable: true,
    value: new Proxy(real, {apply(t, self, args) {
      window.__calls++; return Reflect.apply(t, self, args); }})});
}
wrap(Document.prototype, 'querySelector');
wrap(Document.prototype, 'querySelectorAll');
wrap(Element.prototype, 'querySelector');
wrap(Document.prototype, 'getElementById');
wrap(Array.prototype, 'map');
wrap(JSON, 'stringify');
window.__APP = {ready: true};
const pageConst = 'c';
</script></head><body>
<input name="cf-turnstile-response" value="tok"><div id="x">here</div>
<script>document.getElementById('x').__vue__ = {msg: 'hi'}; window.__calls = 0;</script>
</body></html>"""


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

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
    d = webdriver.Firefox(seed=4251, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


def test_the_page_counts_none_of_your_calls_and_its_additions_stay_its_own(driver, site):
    driver.get(site)
    assert driver.execute_script(
        "return document.querySelector('input[name=\"cf-turnstile-response\"]').value") == "tok"
    assert driver.execute_script(
        "return [...document.querySelectorAll('input')].map(i => i.name)") == [
            "cf-turnstile-response"]
    assert driver.execute_script(
        "return JSON.stringify(document.getElementById('x').id)") == '"x"'
    element = driver.find_element(By.ID, "x")
    # an element argument crosses into the script's world, and what the page
    # put on it is still there
    assert driver.execute_script("return arguments[0].__vue__.msg", element) == "hi"
    assert driver.execute_async_script(
        "const done = arguments[arguments.length - 1];"
        " done(document.body.querySelector('#x').id)") == "x"
    assert driver.execute_script("return window.__APP.ready") is True
    assert driver.execute_script("return pageConst") == "c"
    # a data property of the page: reading it runs none of the page's code
    assert driver.execute_script("return window.__calls") == 0
