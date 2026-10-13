"""`Alert`: a JavaScript alert, confirm, prompt or beforeunload dialog."""
from __future__ import annotations

from ...common import exceptions as exc


class Alert:
    """Same methods as Selenium's Alert.

    The dialog is answered with Juggler's `Page.handleDialog`, the engine's
    own reply to the dialog it is holding open - nothing is clicked, as in
    Selenium, because a native dialog is not part of the page.

    ⛔ AN ALERT IS NOT BOUND TO A DIALOG, as Selenium's is not: every call
    asks for the dialog open NOW, as each of Selenium's is a command to the
    browser. Until 0.5.0 it held the dialog it was made for, so a second
    `switch_to.alert` did not see the text the first had sent to a prompt
    (the page got the default), and an alert already answered still read its
    old text. No dialog is NoAlertPresentException with no message, as
    Marionette's "no such alert" reaches the client.
    """

    def __init__(self, driver) -> None:
        self.driver = driver
        # Selenium's `switch_to.alert` reads the text, so it is here that no
        # dialog raises.
        self._current()

    def _current(self):
        page = self.driver._current_page()
        dialog = self.driver._pending_dialog(page)
        if dialog is None:
            raise exc.NoAlertPresentException("")
        return page, dialog

    @property
    def text(self) -> str:
        """Gets the text of the Alert."""
        return self._current()[1].get("message") or ""

    def _answer(self, accept: bool) -> None:
        page, dialog = self._current()
        params = {"dialogId": dialog["dialogId"], "accept": accept}
        if accept and dialog.get("promptText") is not None:
            params["promptText"] = dialog["promptText"]
        self.driver._dialog_answered(page)
        page.send("Page.handleDialog", params, timeout=10)

    def dismiss(self) -> None:
        """Dismisses the alert available."""
        self._answer(False)

    def accept(self) -> None:
        """Accepts the alert available."""
        self._answer(True)

    def send_keys(self, keysToSend: str) -> None:
        """Send keys to the prompt; they are submitted when it is accepted,
        through this alert or another one."""
        page, dialog = self._current()
        kind = dialog.get("type") or "alert"
        if kind != "prompt":
            # Marionette's words (`sendAlertText`); until 0.5.0 "is not a
            # prompt".
            raise exc.ElementNotInteractableException(
                "User prompt of type %s is not interactable" % kind)
        self.driver._prompt_text(page, str(keysToSend))


__all__ = ["Alert"]
