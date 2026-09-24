"""The Selenium contract, against the real patched Firefox.

One browser for the whole module - launching is the expensive part - and a
local HTTP server for the pages, so nothing here touches the network. Every
assertion is on what a PAGE observes or on what Selenium's contract returns:
a click that reports success but whose event the page never saw would pass a
test that only watched the return value.
"""
from __future__ import annotations

import http.server
import os
import threading

import pytest

pytestmark = pytest.mark.e2e

PAGES = {
    "/": """<!doctype html><html><head><title>Home page</title></head><body>
<h1 id="head" class="big title">Hello   world</h1>
<a id="next" href="/second">Go to second</a>
<a href="/second" target="_blank" id="blank">Open in new tab</a>
<input id="name" name="username" value="">
<input id="agree" type="checkbox" checked>
<input id="off" type="checkbox" disabled>
<textarea id="notes"></textarea>
<button id="btn" onclick="window.clicks = (window.clicks||0)+1">Press</button>
<select id="pick"><option value="a">Alpha</option><option value="b">Beta</option>
<option value="c">Gamma</option></select>
<select id="many" multiple><option value="1">One</option><option value="2">Two</option></select>
<div id="hidden" style="display:none">secret</div>
<form id="f" action="/second" method="get"><input id="q" name="q">
<button type="submit" id="go">Search</button></form>
<iframe id="frm" name="frm" src="/frame"></iframe>
<div id="late"></div>
<div id="drag" draggable="true" style="width:60px;height:60px;background:#c00">drag</div>
<div id="drop" style="width:120px;height:120px;background:#0c0;margin-top:20px">drop</div>
<div style="height:2400px"></div><p id="far">far away</p>
<script>
window.events = [];
window.moves = 0;
document.addEventListener('mousemove', () => { window.moves++; }, true);
for (const t of ['mousedown','mouseup','click','keydown','keyup','input','change'])
  document.addEventListener(t, e => window.events.push(t + ':' + e.isTrusted), true);
setTimeout(() => { const s = document.createElement('span');
  s.id = 'appeared'; s.textContent = 'here'; document.getElementById('late').appendChild(s); }, 1200);
document.getElementById('drop').addEventListener('drop', e => { e.preventDefault(); window.dropped = true; });
document.getElementById('drop').addEventListener('dragover', e => e.preventDefault());
</script></body></html>""",
    "/second": """<!doctype html><html><head><title>Second page</title></head>
<body><p id="where">second</p></body></html>""",
    "/frame": """<!doctype html><html><body><p id="inner">inside the frame</p>
<button id="fbtn" onclick="this.textContent='done'">frame button</button></body></html>""",
    "/alerts": """<!doctype html><html><head><title>Alerts</title></head><body>
<button id="a" onclick="alert('hello alert')">a</button>
<button id="c" onclick="window.answer = confirm('sure?')">c</button>
<button id="p" onclick="window.answer = prompt('name?', 'x')">p</button>
</body></html>""",
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        body = PAGES.get(path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()


@pytest.fixture(scope="module")
def driver(firefox_binary):
    from invisible_selenium import webdriver
    d = webdriver.Firefox(seed=42, binary_path=firefox_binary, headless=True,
                          locale="en-US", timezone="Europe/London")
    yield d
    d.quit()


@pytest.fixture
def home(driver, site):
    driver.switch_to.default_content()
    handles = driver.window_handles
    if driver._page is None or driver._page.target_id not in handles:
        driver.switch_to.window(handles[0])
    driver.get(site + "/")
    return driver


def test_navigation_title_url_and_no_webdriver_flag(home, site):
    d = home
    assert d.title == "Home page"
    assert d.current_url == site + "/"
    assert d.execute_script("return navigator.webdriver") is False
    d.get(site + "/second")
    assert d.title == "Second page"
    d.back()
    assert d.title == "Home page"
    d.forward()
    assert d.title == "Second page"
    d.refresh()
    assert d.title == "Second page"


def test_every_locator_strategy(home):
    from invisible_selenium.webdriver.common.by import By
    d = home
    assert d.find_element(By.ID, "head").tag_name == "h1"
    assert d.find_element(By.NAME, "username").get_attribute("id") == "name"
    assert d.find_element(By.CLASS_NAME, "title").get_attribute("id") == "head"
    assert d.find_element(By.CSS_SELECTOR, "#btn").text == "Press"
    assert d.find_element(By.XPATH, "//button[@id='btn']").text == "Press"
    assert d.find_element(By.LINK_TEXT, "Go to second").get_attribute("id") == "next"
    assert d.find_element(By.PARTIAL_LINK_TEXT, "new tab").get_attribute("id") == "blank"
    assert len(d.find_elements(By.TAG_NAME, "option")) == 5
    assert d.find_elements(By.ID, "nothing-here") == []


def test_missing_and_invalid_locators_raise_seleniums_exceptions(home):
    from invisible_selenium.common.exceptions import (InvalidSelectorException,
                                                      NoSuchElementException)
    from invisible_selenium.webdriver.common.by import By
    with pytest.raises(NoSuchElementException):
        home.find_element(By.ID, "nothing-here")
    with pytest.raises(InvalidSelectorException):
        home.find_element(By.CSS_SELECTOR, "[[[")
    with pytest.raises(InvalidSelectorException):
        home.find_element(By.XPATH, "//*[")


def test_find_below_an_element(home):
    from invisible_selenium.webdriver.common.by import By
    form = home.find_element(By.ID, "f")
    assert form.find_element(By.TAG_NAME, "button").get_attribute("id") == "go"
    assert [e.get_attribute("id") for e in form.find_elements(By.TAG_NAME, "input")] == ["q"]


def test_element_reads(home):
    from invisible_selenium.webdriver.common.by import By
    d = home
    head = d.find_element(By.ID, "head")
    assert head.text == "Hello world"
    assert head.get_attribute("class") == "big title"
    assert d.find_element(By.ID, "next").get_attribute("href").endswith("/second")
    assert d.find_element(By.ID, "next").get_dom_attribute("href") == "/second"
    assert d.find_element(By.ID, "agree").get_attribute("checked") == "true"
    assert d.find_element(By.ID, "agree").is_selected() is True
    assert d.find_element(By.ID, "off").is_enabled() is False
    assert d.find_element(By.ID, "hidden").is_displayed() is False
    assert head.is_displayed() is True
    assert head.get_property("id") == "head"
    rect = head.rect
    assert rect["width"] > 0 and rect["height"] > 0
    assert set(head.location) == {"x", "y"}
    assert head.value_of_css_property("display") == "block"
    assert head == d.find_element(By.CSS_SELECTOR, "h1")
    assert head != d.find_element(By.ID, "btn")


def test_click_is_a_trusted_pointer_that_travels(home):
    from invisible_selenium.webdriver.common.by import By
    d = home
    d.execute_script("window.events = []; window.moves = 0;")
    d.find_element(By.ID, "btn").click()
    assert d.execute_script("return window.clicks") == 1
    events = d.execute_script("return window.events")
    assert "mousedown:true" in events and "mouseup:true" in events
    assert "click:true" in events
    assert not any(e.endswith(":false") for e in events)
    # The pointer arrived along a path, not in one jump.
    assert d.execute_script("return window.moves") > 3


def test_send_keys_clear_and_keys(home):
    from invisible_selenium.webdriver.common.by import By
    from invisible_selenium.webdriver.common.keys import Keys
    d = home
    field = d.find_element(By.ID, "name")
    d.execute_script("window.events = []")
    field.send_keys("hello")
    assert field.get_attribute("value") == "hello"
    field.send_keys(Keys.BACKSPACE, Keys.BACKSPACE, "p!")
    assert field.get_attribute("value") == "help!"
    field.send_keys(Keys.CONTROL, "a", Keys.NULL, "X")
    assert field.get_attribute("value") == "X"
    events = d.execute_script("return window.events")
    assert "keydown:true" in events and "input:true" in events
    assert not any(e.endswith(":false") for e in events)
    field.clear()
    assert field.get_attribute("value") == ""


def test_file_input_receives_the_path(home, tmp_path):
    from invisible_selenium.webdriver.common.by import By
    d = home
    d.execute_script("const i = document.createElement('input'); i.type = 'file';"
                     " i.id = 'up'; document.body.prepend(i);")
    f = tmp_path / "upload.txt"
    f.write_bytes(b"data")
    d.find_element(By.ID, "up").send_keys(str(f))
    assert d.execute_script("return document.getElementById('up').files[0].name") == "upload.txt"


def test_select_and_options(home):
    from invisible_selenium.webdriver.common.by import By
    from invisible_selenium.webdriver.support.select import Select
    d = home
    d.execute_script("window.events = []")
    pick = Select(d.find_element(By.ID, "pick"))
    pick.select_by_visible_text("Gamma")
    assert pick.first_selected_option.text == "Gamma"
    pick.select_by_value("b")
    assert d.find_element(By.ID, "pick").get_attribute("value") == "b"
    assert "change:true" in d.execute_script("return window.events")
    many = Select(d.find_element(By.ID, "many"))
    assert many.is_multiple
    many.select_by_index(0)
    many.select_by_index(1)
    assert [o.text for o in many.all_selected_options] == ["One", "Two"]
    many.deselect_all()
    assert many.all_selected_options == []


def test_submit_clicks_the_forms_button(home, site):
    from invisible_selenium.webdriver.common.by import By
    d = home
    d.find_element(By.ID, "q").send_keys("abc")
    d.find_element(By.ID, "q").submit()
    from invisible_selenium.webdriver.support import expected_conditions as EC
    from invisible_selenium.webdriver.support.ui import WebDriverWait
    WebDriverWait(d, 10).until(EC.title_is("Second page"))
    assert "q=abc" in d.current_url


def test_execute_script_values_and_elements(home):
    from invisible_selenium.webdriver.common.by import By
    from invisible_selenium.webdriver.remote.webelement import WebElement
    d = home
    assert d.execute_script("return 1 + 2") == 3
    assert d.execute_script("return 'x' + arguments[0]", "y") == "xy"
    assert d.execute_script("return [1, 'a', null, true]") == [1, "a", None, True]
    assert d.execute_script("return {a: 1, b: [2, 3], c: {d: 'e'}}") == {
        "a": 1, "b": [2, 3], "c": {"d": "e"}}
    assert d.execute_script("return undefined") is None
    btn = d.find_element(By.ID, "btn")
    assert d.execute_script("return arguments[0].id", btn) == "btn"
    assert d.execute_script("return arguments[0][1].id", [1, btn]) == "btn"
    returned = d.execute_script("return document.getElementById('head')")
    assert isinstance(returned, WebElement) and returned.text == "Hello world"
    many = d.execute_script("return document.querySelectorAll('option')")
    assert [e.text for e in many][:3] == ["Alpha", "Beta", "Gamma"]
    assert d.execute_script("return Promise.resolve(41).then(x => x + 1)") == 42


def test_script_errors_and_async_scripts(home):
    from invisible_selenium.common.exceptions import (JavascriptException,
                                                      TimeoutException)
    d = home
    with pytest.raises(JavascriptException):
        d.execute_script("throw new Error('boom')")
    assert d.execute_async_script(
        "const done = arguments[arguments.length - 1];"
        " setTimeout(() => done(arguments[0] * 2), 50);", 21) == 42
    d.set_script_timeout(1)
    try:
        with pytest.raises(TimeoutException):
            d.execute_async_script("/* never calls back */")
    finally:
        d.set_script_timeout(30)


def test_implicit_and_explicit_waits(home):
    from invisible_selenium.webdriver.common.by import By
    from invisible_selenium.webdriver.support import expected_conditions as EC
    from invisible_selenium.webdriver.support.ui import WebDriverWait
    d = home
    el = WebDriverWait(d, 5).until(EC.presence_of_element_located((By.ID, "appeared")))
    assert el.text == "here"
    d.get(d.current_url)
    d.implicitly_wait(5)
    try:
        assert d.find_element(By.ID, "appeared").text == "here"
    finally:
        d.implicitly_wait(0)


def test_frames(home):
    from invisible_selenium.webdriver.common.by import By
    d = home
    d.switch_to.frame("frm")
    assert d.find_element(By.ID, "inner").text == "inside the frame"
    btn = d.find_element(By.ID, "fbtn")
    btn.click()
    assert btn.text == "done"
    d.switch_to.default_content()
    assert d.find_element(By.ID, "head").tag_name == "h1"
    d.switch_to.frame(0)
    assert d.find_element(By.ID, "inner")
    d.switch_to.parent_frame()
    d.switch_to.frame(d.find_element(By.ID, "frm"))
    assert d.find_element(By.ID, "inner")
    d.switch_to.default_content()


def test_windows_opened_by_us_and_by_the_site(home, site):
    from invisible_selenium.webdriver.common.by import By
    from invisible_selenium.webdriver.support import expected_conditions as EC
    from invisible_selenium.webdriver.support.ui import WebDriverWait
    d = home
    first = d.current_window_handle
    before = len(d.window_handles)
    d.find_element(By.ID, "blank").click()
    WebDriverWait(d, 10).until(EC.number_of_windows_to_be(before + 1))
    popup = [h for h in d.window_handles if h != first][-1]
    d.switch_to.window(popup)
    WebDriverWait(d, 10).until(EC.title_is("Second page"))
    d.close()
    d.switch_to.window(first)
    d.switch_to.new_window("tab")
    assert len(d.window_handles) == before + 1
    d.get(site + "/second")
    assert d.title == "Second page"
    d.close()
    d.switch_to.window(first)
    assert d.title == "Home page"


def test_alerts(driver, site):
    from invisible_selenium.common.exceptions import (NoAlertPresentException,
                                                      UnexpectedAlertPresentException)
    from invisible_selenium.webdriver.common.by import By
    from invisible_selenium.webdriver.support import expected_conditions as EC
    from invisible_selenium.webdriver.support.ui import WebDriverWait
    d = driver
    d.switch_to.window(d.window_handles[0])
    d.get(site + "/alerts")
    with pytest.raises(NoAlertPresentException):
        d.switch_to.alert.text
    d.find_element(By.ID, "a").click()
    alert = WebDriverWait(d, 5).until(EC.alert_is_present())
    assert alert.text == "hello alert"
    alert.accept()
    d.find_element(By.ID, "c").click()
    WebDriverWait(d, 5).until(EC.alert_is_present()).dismiss()
    assert d.execute_script("return window.answer") is False
    d.find_element(By.ID, "p").click()
    prompt = WebDriverWait(d, 5).until(EC.alert_is_present())
    prompt.send_keys("Ada")
    prompt.accept()
    assert d.execute_script("return window.answer") == "Ada"
    d.find_element(By.ID, "a").click()
    WebDriverWait(d, 5).until(EC.alert_is_present())
    with pytest.raises(UnexpectedAlertPresentException):
        d.title


def test_cookies(home):
    d = home
    d.delete_all_cookies()
    d.add_cookie({"name": "k", "value": "v"})
    got = d.get_cookie("k")
    assert got["value"] == "v" and got["path"] == "/"
    assert any(c["name"] == "k" for c in d.get_cookies())
    assert d.execute_script("return document.cookie").find("k=v") >= 0
    d.delete_cookie("k")
    assert d.get_cookie("k") is None


def test_action_chains(home):
    from invisible_selenium.webdriver.common.action_chains import ActionChains
    from invisible_selenium.webdriver.common.by import By
    from invisible_selenium.webdriver.common.keys import Keys
    d = home
    d.execute_script("window.clicks = 0; window.moves = 0; window.events = [];")
    btn = d.find_element(By.ID, "btn")
    ActionChains(d).move_to_element(btn).click().perform()
    assert d.execute_script("return window.clicks") == 1
    assert d.execute_script("return window.moves") > 3
    ActionChains(d).double_click(btn).perform()
    assert d.execute_script("return window.clicks") == 3
    field = d.find_element(By.ID, "notes")
    ActionChains(d).send_keys_to_element(field, "ab").key_down(Keys.SHIFT) \
        .send_keys("c").key_up(Keys.SHIFT).perform()
    assert field.get_attribute("value") == "abC"
    ActionChains(d).drag_and_drop(d.find_element(By.ID, "drag"),
                                  d.find_element(By.ID, "drop")).perform()
    assert d.execute_script("return window.dropped === true")
    ActionChains(d).scroll_to_element(d.find_element(By.ID, "far")).perform()
    assert d.execute_script("return window.scrollY") > 1000


def test_screenshots(home, tmp_path):
    from invisible_selenium.webdriver.common.by import By
    d = home
    png = d.get_screenshot_as_png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert d.find_element(By.ID, "btn").screenshot_as_png[:4] == b"\x89PNG"
    target = tmp_path / "shot.png"
    assert d.save_screenshot(str(target)) and target.stat().st_size > 0


def test_stale_element_after_navigation(home, site):
    from invisible_selenium.common.exceptions import StaleElementReferenceException
    from invisible_selenium.webdriver.common.by import By
    d = home
    head = d.find_element(By.ID, "head")
    d.get(site + "/second")
    with pytest.raises(StaleElementReferenceException):
        head.text


def test_the_profile_reaches_the_page(driver, site):
    d = driver
    d.switch_to.window(d.window_handles[0])
    d.get(site + "/second")
    assert d.execute_script("return navigator.language") == "en-US"
    assert d.execute_script(
        "return Intl.DateTimeFormat().resolvedOptions().timeZone") == "Europe/London"
    screen_w = d.execute_script("return screen.width")
    inner_w = d.execute_script("return window.innerWidth")
    assert screen_w >= inner_w > 0
