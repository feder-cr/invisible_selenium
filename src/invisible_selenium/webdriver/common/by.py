"""`By`: the locator strategies, with Selenium's values."""
from __future__ import annotations

from typing import Dict, Literal, Optional

ByType = Literal["id", "xpath", "link text", "partial link text", "name",
                 "tag name", "class name", "css selector"]


class By:
    """Set of supported locator strategies."""

    ID: ByType = "id"
    XPATH: ByType = "xpath"
    LINK_TEXT: ByType = "link text"
    PARTIAL_LINK_TEXT: ByType = "partial link text"
    NAME: ByType = "name"
    TAG_NAME: ByType = "tag name"
    CLASS_NAME: ByType = "class name"
    CSS_SELECTOR: ByType = "css selector"

    _custom_finders: Dict[str, str] = {}

    @classmethod
    def register_custom_finder(cls, name: str, strategy: str) -> None:
        cls._custom_finders[name] = strategy

    @classmethod
    def get_finder(cls, name: str) -> Optional[str]:
        return cls._custom_finders.get(name) or getattr(cls, name.upper(), None)

    @classmethod
    def clear_custom_finders(cls) -> None:
        cls._custom_finders.clear()


__all__ = ["By", "ByType"]
