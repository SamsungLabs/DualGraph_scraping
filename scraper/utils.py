import asyncio
from typing import Callable

from selenium import webdriver
from selenium.common.exceptions import (
    ElementNotInteractableException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)


@retry(
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((StaleElementReferenceException)),
    wait=wait_fixed(2),
)
def get_attribute(element: WebElement, key: str):
    return element.get_attribute(key)


@retry(
    stop=stop_after_attempt(10),
    retry=retry_if_exception_type((ElementNotInteractableException)),
    wait=wait_fixed(3),
)
async def wait_and_click(driver: WebDriver, selector: tuple[str, str] | WebElement):
    await asyncio.sleep(1)
    if isinstance(selector, tuple):
        element = driver.find_element(*selector)
    else:
        element = selector
    element.click()


async def start_driver() -> WebDriver:
    driver = webdriver.Firefox()
    driver.get("https://www.samsung.com/uk/")
    await asyncio.sleep(1)
    await wait_and_click(driver, (By.ID, "truste-consent-required"))
    return driver


async def start_drivers(
    num_drivers: int,
) -> tuple[list[WebDriver], asyncio.Semaphore]:
    driver_starters = [start_driver() for i in range(num_drivers)]
    drivers = await asyncio.gather(*driver_starters)
    semaphore = asyncio.Semaphore(num_drivers)
    return drivers, semaphore


async def get_link(
    scraping_function: Callable,
    link: str,
    semaphore: asyncio.Semaphore,
    drivers: list[WebDriver],
    **kwargs,
) -> dict:
    # thin wrapper for semaphore and retry catching
    async with semaphore:
        driver = drivers.pop()
        try:
            result = await scraping_function(link, driver, **kwargs)
            drivers.append(driver)
            return result
        except RetryError as exc:
            print(f"Too many retries: {link}, {exc}.")
            drivers.append(driver)
            return {}
