"""`ShadowRoot`: an element's open shadow root, searchable like Selenium's."""
from __future__ import annotations

from typing import List

from ...common import exceptions as exc
from ...webdriver.common.by import By


class ShadowRoot:
    def __init__(self, session, page, frame_id: str, oid: str) -> None:
        self.session = session
        self._page = page
        self._frame_id = frame_id
        self._oid = oid
        import uuid
        self._id = str(uuid.uuid4())

    @property
    def id(self) -> str:
        return self._id

    def __repr__(self) -> str:
        return '<%s.%s (session="%s", element="%s")>' % (
            type(self).__module__, type(self).__name__,
            self.session.session_id, self._id)

    def _check_alive(self) -> None:
        self.session._check_alert()

    def _by(self, by: str) -> str:
        # Selenium's shadow roots accept CSS only; the other strategies are
        # rewritten to CSS by the client, and XPath is refused by the driver.
        if by == By.XPATH:
            raise exc.InvalidArgumentException(
                "XPath is not supported inside a shadow root")
        return by

    def find_element(self, by: str = By.ID, value: str = None):
        return self.session._find(self._page, self._frame_id, self,
                                  self._by(by), value, single=True)

    def find_elements(self, by: str = By.ID, value: str = None) -> List:
        return self.session._find(self._page, self._frame_id, self,
                                  self._by(by), value, single=False)


__all__ = ["ShadowRoot"]
