"""`Service`: accepted so `webdriver.Firefox(service=...)` keeps working.

There is no geckodriver here. The browser is started by `webdriver.Firefox`
itself and driven over the Juggler pipe, so this object only carries its
arguments; passing an executable path produces a warning saying it is unused.
"""
from __future__ import annotations

from typing import List, Optional


class Service:
    def __init__(self, executable_path: Optional[str] = None, port: int = 0,
                 service_args: Optional[List[str]] = None, log_output=None,
                 env=None, **kwargs) -> None:
        self.path = executable_path
        self.port = port
        self.service_args = list(service_args or [])
        self.log_output = log_output
        self.env = env


__all__ = ["Service"]
