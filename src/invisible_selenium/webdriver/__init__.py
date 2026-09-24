"""`invisible_selenium.webdriver`: the names `selenium.webdriver` exposes.

Replace `from selenium import webdriver` with
`from invisible_selenium import webdriver` and the rest of the script stays as
it is. Only Firefox exists here, because the browser is the patched Firefox.
"""
from .common.action_chains import ActionChains
from .common.keys import Keys
from .firefox.options import Options as FirefoxOptions
from .firefox.service import Service as FirefoxService
from .firefox.webdriver import WebDriver as Firefox

__all__ = ["Firefox", "FirefoxOptions", "FirefoxService", "ActionChains", "Keys"]
