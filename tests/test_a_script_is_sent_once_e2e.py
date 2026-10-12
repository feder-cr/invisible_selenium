"""A script is sent once, whatever happens to its document.

Juggler's channel sends every message still waiting for an answer AGAIN to the
document that replaces the one it went to (`SimpleChannel._markAsReady`). A
script that ran and was waiting on a promise when its page navigated comes
back refused by the new document, in the same words as a script that never
ran. 0.3.6 sent such a script again into the new page, which ran it twice;
Marionette never sends `executeScript` again and answers null
(`NO_RETRY_METHODS` in `MarionetteCommandsParent.sys.mjs`).
"""
from __future__ import annotations

import http.server
import threading
import time

import pytest

pytestmark = pytest.mark.e2e

FIRST = b"<!doctype html><html><head><title>first</title></head><body>first</body></html>"
NEXT = b"<!doctype html><html><head><title>next</title></head><body>next</body></html>"


@pytest.fixture(scope="module")
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = NEXT if self.path.startswith("/next") else FIRST
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
    d = webdriver.Firefox(seed=4246, binary_path=firefox_binary, headless=True)
    yield d
    d.quit()


def test_a_script_whose_page_navigates_while_it_waits_runs_once(driver, site):
    driver.get(site)
    driver.execute_script("localStorage.clear()")
    result = driver.execute_script(
        "localStorage.runs = String(Number(localStorage.runs || 0) + 1);"
        " setTimeout(() => { location.href = '/next'; }, 100);"
        " return new Promise(() => {});")
    assert result is None
    deadline = time.monotonic() + 20
    while driver.execute_script("return document.title") != "next":
        assert time.monotonic() < deadline, "the page never reached /next"
        time.sleep(0.05)
    time.sleep(0.5)  # a second run would have navigated and counted again
    assert driver.execute_script("return localStorage.runs") == "1"
