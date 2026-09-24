# Third-party code in invisible_selenium

Two files were extracted from Microsoft Playwright's driver bundle and are
redistributed under the Apache License 2.0 (`LICENSE-APACHE`). Everything else
is MIT (`LICENSE`).

| file | what it is |
|---|---|
| `src/invisible_selenium/_juggler/injected.js` | the selector engines and the actionability checks that run inside the page's utility world, with the stealth fixes invisible_playwright made to them |
| `src/invisible_selenium/_juggler/keylayout.py` | the US keyboard layout (key, code, keyCode, location) |

Both came with the rest of invisible_playwright's engine when this package was
created as its replica. The history of the changes made to them is in
invisible_playwright's `THIRD_PARTY_FORK.md`.

## Selenium

No Selenium code is included. The public API - module paths, class and method
names, signatures, exception classes, and the W3C key code points in `Keys` -
is re-implemented so that scripts written for Selenium run unchanged. Selenium
is Apache-2.0; names and interfaces are what is shared, not code.
