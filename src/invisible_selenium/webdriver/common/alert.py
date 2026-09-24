"""`Alert`: a JavaScript alert, confirm, prompt or beforeunload dialog."""
from __future__ import annotations

from ...common import exceptions as exc


class Alert:
    """Same methods as Selenium's Alert.

    The dialog is answered with Juggler's `Page.handleDialog`, the engine's
    own reply to the dialog it is holding open - nothing is clicked, as in
    Selenium, because a native dialog is not part of the page.
    """

    def __init__(self, driver) -> None:
        self.driver = driver
        self._page = driver._current_page()
        self._dialog = driver._pending_dialog(self._page)
        if self._dialog is None:
            raise exc.NoAlertPresentException("No dialog is present")
        self._prompt_text = None

    @property
    def text(self) -> str:
        """Gets the text of the Alert."""
        return self._dialog.get("message") or ""

    def _answer(self, accept: bool) -> None:
        if self.driver._pending_dialog(self._page) is not self._dialog:
            raise exc.NoAlertPresentException("The dialog is no longer open")
        params = {"dialogId": self._dialog["dialogId"], "accept": accept}
        if accept and self._prompt_text is not None:
            params["promptText"] = self._prompt_text
        self.driver._dialog_answered(self._page)
        self._page.send("Page.handleDialog", params, timeout=10)

    def dismiss(self) -> None:
        """Dismisses the alert available."""
        self._answer(False)

    def accept(self) -> None:
        """Accepts the alert available."""
        self._answer(True)

    def send_keys(self, keysToSend: str) -> None:
        """Send keys to the prompt; they are submitted when it is accepted."""
        if (self._dialog.get("type") or "") != "prompt":
            raise exc.ElementNotInteractableException(
                "User prompt of type %s is not a prompt"
                % (self._dialog.get("type") or "alert"))
        self._prompt_text = str(keysToSend)


__all__ = ["Alert"]
