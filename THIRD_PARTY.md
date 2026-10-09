# Third-party code in invisible_selenium

None is redistributed since 0.3.0. Until then this package carried its own copy
of the Juggler client, and with it two files extracted from Microsoft
Playwright's driver bundle under the Apache License 2.0: the injected script
(selector engines and actionability checks) and the US keyboard layout. The
client moved to invisible-core, the one copy every invisible_ wrapper shares,
and the two files moved with it; invisible-core declares them in its own
`THIRD_PARTY.md` and ships `LICENSE-APACHE`.

## Selenium

No Selenium code is included. The public API - module paths, class and method
names, signatures, exception classes, and the W3C key code points in `Keys` -
is re-implemented so that scripts written for Selenium run unchanged. Selenium
is Apache-2.0; names and interfaces are what is shared, not code.
