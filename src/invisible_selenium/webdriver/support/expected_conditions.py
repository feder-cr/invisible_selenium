"""The expected conditions, with Selenium's names and semantics.

Each returns a callable for `WebDriverWait.until`: it takes the driver (or an
element, for the locator ones) and answers something truthy when the condition
holds. They use nothing but the public driver and element API.
"""
from __future__ import annotations

import re
from typing import Any, Callable, List, Tuple, Union

from ...common.exceptions import (NoAlertPresentException,
                                  NoSuchElementException,
                                  NoSuchFrameException,
                                  StaleElementReferenceException,
                                  WebDriverException)

Locator = Tuple[str, str]


def _is_element(obj) -> bool:
    from ..remote.webelement import WebElement
    return isinstance(obj, WebElement)


def title_is(title: str) -> Callable[[Any], bool]:
    return lambda driver: driver.title == title


def title_contains(title: str) -> Callable[[Any], bool]:
    return lambda driver: title in driver.title


def presence_of_element_located(locator: Locator):
    return lambda driver: driver.find_element(*locator)


def url_contains(url: str) -> Callable[[Any], bool]:
    return lambda driver: url in driver.current_url


def url_matches(pattern: str) -> Callable[[Any], bool]:
    return lambda driver: re.search(pattern, driver.current_url) is not None


def url_to_be(url: str) -> Callable[[Any], bool]:
    return lambda driver: url == driver.current_url


def url_changes(url: str) -> Callable[[Any], bool]:
    return lambda driver: url != driver.current_url


def _element_if_visible(element, visibility: bool = True):
    return element if element.is_displayed() == visibility else False


def visibility_of_element_located(locator: Locator):
    def _predicate(driver):
        try:
            return _element_if_visible(driver.find_element(*locator))
        except StaleElementReferenceException:
            return False
    return _predicate


def visibility_of(element):
    return lambda _: _element_if_visible(element)


def presence_of_all_elements_located(locator: Locator):
    return lambda driver: driver.find_elements(*locator)


def visibility_of_any_elements_located(locator: Locator):
    return lambda driver: [e for e in driver.find_elements(*locator)
                           if _element_if_visible(e)]


def visibility_of_all_elements_located(locator: Locator):
    def _predicate(driver):
        try:
            elements = driver.find_elements(*locator)
            for element in elements:
                if _element_if_visible(element, visibility=False):
                    return False
            return elements
        except StaleElementReferenceException:
            return False
    return _predicate


def text_to_be_present_in_element(locator: Locator, text_: str):
    def _predicate(driver):
        try:
            return text_ in driver.find_element(*locator).text
        except StaleElementReferenceException:
            return False
    return _predicate


def text_to_be_present_in_element_value(locator: Locator, text_: str):
    def _predicate(driver):
        try:
            value = driver.find_element(*locator).get_attribute("value")
            return value is not None and text_ in value
        except StaleElementReferenceException:
            return False
    return _predicate


def text_to_be_present_in_element_attribute(locator: Locator, attribute_: str,
                                            text_: str):
    def _predicate(driver):
        try:
            value = driver.find_element(*locator).get_attribute(attribute_)
            return value is not None and text_ in value
        except StaleElementReferenceException:
            return False
    return _predicate


def frame_to_be_available_and_switch_to_it(locator: Union[Locator, str, Any]):
    def _predicate(driver):
        try:
            if isinstance(locator, (list, tuple)):
                driver.switch_to.frame(driver.find_element(*locator))
            else:
                driver.switch_to.frame(locator)
            return True
        except NoSuchFrameException:
            return False
    return _predicate


def invisibility_of_element_located(locator: Union[Locator, Any]):
    def _predicate(driver):
        try:
            target = locator
            if not _is_element(target):
                target = driver.find_element(*target)
            return _element_if_visible(target, visibility=False)
        except (NoSuchElementException, StaleElementReferenceException):
            # Gone from the DOM, or stale: either way it is not visible.
            return True
    return _predicate


def invisibility_of_element(element):
    return invisibility_of_element_located(element)


def element_to_be_clickable(mark: Union[Locator, Any]):
    def _predicate(driver):
        target = mark
        if not _is_element(target):
            target = driver.find_element(*target)
        element = visibility_of(target)(driver)
        if element and element.is_enabled():
            return element
        return False
    return _predicate


def staleness_of(element) -> Callable[[Any], bool]:
    def _predicate(_):
        try:
            element.is_enabled()
            return False
        except StaleElementReferenceException:
            return True
    return _predicate


def element_to_be_selected(element) -> Callable[[Any], bool]:
    return lambda _: element.is_selected()


def element_located_to_be_selected(locator: Locator) -> Callable[[Any], bool]:
    return lambda driver: driver.find_element(*locator).is_selected()


def element_selection_state_to_be(element, is_selected: bool):
    return lambda _: element.is_selected() == is_selected


def element_located_selection_state_to_be(locator: Locator, is_selected: bool):
    def _predicate(driver):
        try:
            return driver.find_element(*locator).is_selected() == is_selected
        except StaleElementReferenceException:
            return False
    return _predicate


def number_of_windows_to_be(num_windows: int) -> Callable[[Any], bool]:
    return lambda driver: len(driver.window_handles) == num_windows


def new_window_is_opened(current_handles: List[str]) -> Callable[[Any], bool]:
    return lambda driver: len(driver.window_handles) > len(current_handles)


def alert_is_present():
    def _predicate(driver):
        try:
            return driver.switch_to.alert
        except NoAlertPresentException:
            return False
    return _predicate


def element_attribute_to_include(locator: Locator, attribute_: str):
    def _predicate(driver):
        try:
            return driver.find_element(*locator).get_attribute(attribute_) is not None
        except StaleElementReferenceException:
            return False
    return _predicate


def any_of(*expected_conditions):
    def any_of_condition(driver):
        for condition in expected_conditions:
            try:
                result = condition(driver)
                if result:
                    return result
            except WebDriverException:
                pass
        return False
    return any_of_condition


def all_of(*expected_conditions):
    def all_of_condition(driver):
        results = []
        for condition in expected_conditions:
            try:
                result = condition(driver)
                if not result:
                    return False
                results.append(result)
            except WebDriverException:
                return False
        return results
    return all_of_condition


def none_of(*expected_conditions):
    def none_of_condition(driver):
        for condition in expected_conditions:
            try:
                if condition(driver):
                    return False
            except WebDriverException:
                pass
        return True
    return none_of_condition
