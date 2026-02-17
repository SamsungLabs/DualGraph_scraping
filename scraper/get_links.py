import asyncio
import json
from argparse import ArgumentParser
from itertools import chain
from itertools import product as cartesian_product
from pathlib import Path

import tqdm.asyncio
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
from urllib3.exceptions import ReadTimeoutError

from .utils import get_attribute, get_link, start_drivers, wait_and_click

BIG_CATEGORY_LINKS = (
    "https://www.samsung.com/uk/smartphones/all-smartphones/",
    "https://www.samsung.com/uk/refrigerators/all-refrigerators/",
    "https://www.samsung.com/uk/tvs/all-tvs/",
    "https://www.samsung.com/uk/computers/all-computers/",
    "https://www.samsung.com/uk/watches/all-watches/",
)

NUM_DRIVERS = 4

SMALL_CATEGORY_CLASS = "nv19-pd-category-main__item-inner"
PRICE_CLASS = "price-ux__wrap"


@retry(
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((ReadTimeoutError, ElementNotInteractableException)),
)
async def get_small_categories(link: str, driver) -> set[str]:
    small_categories_links = []
    driver.get(link)
    await asyncio.sleep(1)
    category_links = driver.find_elements(By.CLASS_NAME, SMALL_CATEGORY_CLASS)
    small_categories_links.extend(
        [link] + [cl.get_attribute("href") for cl in category_links][1:]
    )
    return set(small_categories_links)


@retry(
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((ValueError, StaleElementReferenceException)),
    wait=wait_fixed(2),
)
async def get_price(prod: WebElement) -> str:
    await asyncio.sleep(2)
    price_element = prod.find_element(By.CLASS_NAME, PRICE_CLASS)
    price = price_element.text
    return price


def get_product_options(driver: WebDriver, prod_index: int):
    prods = driver.find_elements(By.CLASS_NAME, "js-pfv2-product-card")
    prod = prods[prod_index]
    option_selector = prod.find_element(
        By.CLASS_NAME, "pd21-product-card__options-wrap"
    )
    option_parameters = option_selector.find_elements(
        By.CLASS_NAME, "option-selector-v2"
    )
    option_parameters = [op for op in option_parameters if op.is_displayed()]
    value_domains = []
    for option_parameter in option_parameters:
        parameter_values = option_parameter.find_elements(By.TAG_NAME, "button")
        value_domains.append(len(parameter_values))
    parameter_combinations = list(
        cartesian_product(*[range(nvals) for nvals in value_domains])
    )
    return parameter_combinations


@retry(
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((IndexError)),
)
def get_product_card(driver: WebDriver, prod_index: int) -> WebElement:
    prod = driver.find_elements(By.CLASS_NAME, "js-pfv2-product-card")[prod_index]
    return prod


@retry(
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((ElementNotInteractableException, RetryError)),
)
async def load_product_variants(driver, prod_index: int):
    variant_links = []
    parameter_combinations = get_product_options(driver, prod_index)
    prod = get_product_card(driver, prod_index)
    prod_top = prod.location["y"]
    driver.execute_script(f"window.scrollTo(0, {prod_top});")
    for value_comb in parameter_combinations:
        variant_values = []
        for option_i, value_i in enumerate(value_comb):
            await asyncio.sleep(1)
            prod = get_product_card(driver, prod_index)
            option_selector = prod.find_element(
                By.CLASS_NAME, "pd21-product-card__options-wrap"
            )
            option_parameters = option_selector.find_elements(
                By.CLASS_NAME, "option-selector-v2"
            )
            option_parameters = [op for op in option_parameters if op.is_displayed()]
            option_parameter = option_parameters[option_i]
            parameter_button = option_parameter.find_elements(By.TAG_NAME, "button")[
                value_i
            ]
            parameter_value_name = parameter_button.get_attribute("an-la")
            variant_values.append(parameter_value_name)
            try:
                await wait_and_click(driver, parameter_button)
            except RetryError as exc:
                print(
                    f"Too many retries: {driver.current_url}, {prod}, {value_comb}, {exc}."
                )
                break

        prod = get_product_card(driver, prod_index)
        prod_link = get_attribute(
            prod.find_element(By.CLASS_NAME, "pd21-product-card__name"), "href"
        )
        prod_range = get_attribute(
            prod.find_element(By.CLASS_NAME, "pd21-product-card__name"),
            "data-modelname",
        )
        variant_name = get_attribute(
            prod.find_element(By.CLASS_NAME, "pd21-product-card__name"),
            "data-modelcode",
        )
        try:
            price = await get_price(prod)
        except ElementNotInteractableException:
            print(driver.current_url)
            price = None

        variant_links.append(
            (prod_link, prod_range, variant_name, tuple(variant_values), price)
        )
    return variant_links


@retry(
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((ValueError)),
    wait=wait_fixed(2),
)
def get_num_prods(driver: WebDriver) -> int:
    num_prods = int(driver.find_element(By.CLASS_NAME, "pd21-top__result-count").text)
    return num_prods


@retry(
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((ReadTimeoutError, RetryError)),
)
async def get_product_cards(small_category_link: str, driver: WebDriver) -> list[tuple]:
    driver.get(small_category_link)
    await asyncio.sleep(3)
    num_prods = get_num_prods(driver)
    prod_counter = 0
    product_cards = []
    while prod_counter < num_prods:
        await asyncio.sleep(1)
        product_cards.extend(await load_product_variants(driver, prod_counter))
        await asyncio.sleep(1)
        prod_counter += 1

    return product_cards


async def scrape(big_category_links: tuple[str, ...]) -> list[tuple]:
    drivers, semaphore = await start_drivers(NUM_DRIVERS)
    tasks = [
        get_link(get_small_categories, link, semaphore, drivers)
        for link in big_category_links
    ]
    small_categories = await tqdm.asyncio.tqdm.gather(*tasks)
    small_category_links = {
        link
        for link_set in small_categories
        for link in link_set
        if link is not None and len(link.split("/")) == 7
    }

    tasks = [
        get_link(get_product_cards, link, semaphore, drivers)
        for link in small_category_links
    ]
    product_cards_by_categories = await tqdm.asyncio.tqdm.gather(*tasks)
    unique_product_cards = list(set(chain(*product_cards_by_categories)))
    return unique_product_cards


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "--output_file", type=Path, help="file where links will be saved"
    )
    args = parser.parse_args()

    product_cards = asyncio.run(scrape(BIG_CATEGORY_LINKS))
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(product_cards, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
