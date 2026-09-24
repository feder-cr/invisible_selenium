"""`Select`: a `<select>` element, driven like Selenium's.

⛔ AN OPTION IS CHOSEN THROUGH `option.click()`, never by setting `selected`
from a script. `WebElement.click()` on an option goes through the engine's
`select_option`, which fires `input` and `change` as TRUSTED events; a value
assigned by script would reach the page with no events or with untrusted ones.
Selenium's own Select clicks the options too, so the contract is the same.
"""
from __future__ import annotations

from typing import List

from ...common.exceptions import (NoSuchElementException,
                                  UnexpectedTagNameException)
from ..common.by import By


class Select:
    def __init__(self, webelement) -> None:
        if webelement.tag_name.lower() != "select":
            raise UnexpectedTagNameException(
                f"Select only works on <select> elements, not on "
                f"{webelement.tag_name}")
        self._el = webelement
        multi = self._el.get_dom_attribute("multiple")
        self.is_multiple = multi and multi != "false"

    @property
    def options(self) -> List:
        """All options belonging to this select tag."""
        return self._el.find_elements(By.TAG_NAME, "option")

    @property
    def all_selected_options(self) -> List:
        """All selected options belonging to this select tag."""
        return [opt for opt in self.options if opt.is_selected()]

    @property
    def first_selected_option(self):
        """The first selected option (or the one currently selected)."""
        for opt in self.options:
            if opt.is_selected():
                return opt
        raise NoSuchElementException("No options are selected")

    def select_by_value(self, value: str) -> None:
        css = f"option[value ={self._escape_string(value)}]"
        opts = self._el.find_elements(By.CSS_SELECTOR, css)
        matched = False
        for opt in opts:
            self._set_selected(opt)
            if not self.is_multiple:
                return
            matched = True
        if not matched:
            raise NoSuchElementException(f"Cannot locate option with value: {value}")

    def select_by_index(self, index: int) -> None:
        match = str(index)
        for opt in self.options:
            if opt.get_attribute("index") == match:
                self._set_selected(opt)
                return
        raise NoSuchElementException(f"Could not locate element with index {index}")

    def select_by_visible_text(self, text: str) -> None:
        matched = False
        for opt in self.options:
            if opt.text.strip() == " ".join(text.split()):
                self._set_selected(opt)
                if not self.is_multiple:
                    return
                matched = True
        if not matched:
            raise NoSuchElementException(f"Could not locate element with visible text: {text}")

    def deselect_all(self) -> None:
        if not self.is_multiple:
            raise NotImplementedError("You may only deselect all options of a multi-select")
        for opt in self.options:
            self._unset_selected(opt)

    def deselect_by_value(self, value: str) -> None:
        if not self.is_multiple:
            raise NotImplementedError("You may only deselect options of a multi-select")
        matched = False
        css = f"option[value = {self._escape_string(value)}]"
        for opt in self._el.find_elements(By.CSS_SELECTOR, css):
            self._unset_selected(opt)
            matched = True
        if not matched:
            raise NoSuchElementException(f"Could not locate element with value: {value}")

    def deselect_by_index(self, index: int) -> None:
        if not self.is_multiple:
            raise NotImplementedError("You may only deselect options of a multi-select")
        for opt in self.options:
            if opt.get_attribute("index") == str(index):
                self._unset_selected(opt)
                return
        raise NoSuchElementException(f"Could not locate element with index {index}")

    def deselect_by_visible_text(self, text: str) -> None:
        if not self.is_multiple:
            raise NotImplementedError("You may only deselect options of a multi-select")
        matched = False
        for opt in self.options:
            if opt.text.strip() == " ".join(text.split()):
                self._unset_selected(opt)
                matched = True
        if not matched:
            raise NoSuchElementException(f"Could not locate element with visible text: {text}")

    def _set_selected(self, option) -> None:
        if not option.is_enabled():
            raise NotImplementedError("You may not select a disabled option")
        if not option.is_selected():
            option.click()

    def _unset_selected(self, option) -> None:
        if option.is_selected():
            option.click()

    @staticmethod
    def _escape_string(value: str) -> str:
        if '"' in value and "'" in value:
            parts = value.split('"')
            return "concat(" + ", '\"', ".join(f'"{p}"' for p in parts) + ")"
        if '"' in value:
            return f"'{value}'"
        return f'"{value}"'


__all__ = ["Select"]
