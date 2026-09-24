"""`Timeouts`: the three session timeouts, in seconds, like Selenium's."""
from __future__ import annotations


class Timeouts:
    def __init__(self, implicit_wait: float = 0, page_load: float = 0,
                 script: float = 0) -> None:
        self._implicit_wait = float(implicit_wait)
        self._page_load = float(page_load)
        self._script = float(script)

    @property
    def implicit_wait(self) -> float:
        return self._implicit_wait

    @implicit_wait.setter
    def implicit_wait(self, value: float) -> None:
        self._implicit_wait = float(value)

    @property
    def page_load(self) -> float:
        return self._page_load

    @page_load.setter
    def page_load(self, value: float) -> None:
        self._page_load = float(value)

    @property
    def script(self) -> float:
        return self._script

    @script.setter
    def script(self, value: float) -> None:
        self._script = float(value)

    def _to_json(self) -> dict:
        return {"implicit": int(self._implicit_wait * 1000),
                "pageLoad": int(self._page_load * 1000),
                "script": int(self._script * 1000)}


__all__ = ["Timeouts"]
