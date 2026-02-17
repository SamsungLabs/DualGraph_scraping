import asyncio
import json
from argparse import ArgumentParser
from datetime import datetime
from hashlib import md5
from pathlib import Path

import pandas
import tqdm.asyncio
from selenium.common.exceptions import (
    InvalidArgumentException,
    InvalidSelectorException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from tenacity import retry, retry_if_exception_type, stop_after_attempt
from urllib3.exceptions import ReadTimeoutError

from .utils import get_link, start_drivers, wait_and_click

layout_c_categories = ["computer-accessories", "mobile-accessories"]
PRODUCT_CARD_COLUMNNS = ["link", "product_range", "model_code", "features", "price"]

NUM_DRIVERS = 8

DEFAULT_SLEEP = 3


price_mapping = {}  # type: ignore
feature_mapping = {}  # type: ignore


async def load_A(driver: WebDriver, link: str, output_dir: Path, url_data: dict):
    await wait_and_click(driver, (By.ID, "anchor_pd-g-product-specs"))
    try:
        await wait_and_click(driver, (By.CLASS_NAME, "pdd32-product-spec__expand-cta"))
    except NoSuchElementException:
        await wait_and_click(driver, (By.CLASS_NAME, "spec-highlight__button"))

    product_range = url_data["product_range"]
    variant_features = url_data["variant_features"]
    variant_name = "<SEP>".join([product_range] + variant_features)
    try:
        source = driver.page_source
    except InvalidArgumentException:
        source = ""

    result = {"html": source, "variant_name": variant_name}
    result.update(url_data)

    text_file_name = md5(str(link).encode("utf-8")).hexdigest()[:16] + ".html"
    with open(output_dir / text_file_name, "w", encoding="utf-8") as f:
        f.write(source)

    spec_file_name = md5(str(result).encode("utf-8")).hexdigest()[:16] + ".json"
    with open(output_dir / spec_file_name, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


async def load_B(driver: WebDriver, link: str, output_dir: Path, url_data: dict):
    # pylint: disable=too-many-locals,too-many-statements
    url_data = url_data.copy()
    _ = url_data.pop("price")
    _ = url_data.pop("model_code")
    _ = url_data.pop("variant_features")
    _ = url_data.pop("product_range")

    try:
        source = driver.page_source
    except InvalidArgumentException:
        source = ""

    text_file_name = md5(str(link).encode("utf-8")).hexdigest()[:16] + ".html"
    with open(output_dir / text_file_name, "w", encoding="utf-8") as f:
        f.write(source)

    results = []
    try:
        await wait_and_click(driver, (By.LINK_TEXT, "SPECIFICATIONS"))
    except (NoSuchElementException, InvalidSelectorException):
        try:
            await wait_and_click(driver, (By.LINK_TEXT, "SPECS"))
        except NoSuchElementException:
            print("Unable to scrape ", link)
            return

    await asyncio.sleep(DEFAULT_SLEEP)
    prod_range_tab = driver.find_elements(By.CLASS_NAME, "specification-tab")[0]
    prod_range_buttons = prod_range_tab.find_elements(
        By.CLASS_NAME, "specification-tab__button"
    )
    prod_range_to_colors = {}
    for i, prod_range_button in enumerate(prod_range_buttons):
        await wait_and_click(driver, (By.ID, prod_range_button.get_attribute("id")))  # type: ignore
        prod_range_name = prod_range_button.text.strip()
        prod_range_colors_tab = driver.find_elements(
            By.CLASS_NAME, "specification__color-list"
        )[i]
        colors = [
            color.text
            for color in prod_range_colors_tab.find_elements(By.TAG_NAME, "figcaption")
        ]
        prod_range_to_colors[prod_range_name] = colors

    prod_variant_tab = driver.find_elements(By.CLASS_NAME, "specification-tab")[1]
    prod_range_rows = prod_variant_tab.find_elements(
        By.CLASS_NAME, "specification-tab__list"
    )

    for i, prod_range_row in enumerate(prod_range_rows):
        for prod_variant in prod_range_row.find_elements(By.TAG_NAME, "button"):
            model_code = prod_variant.get_attribute("data-model-code")
            price = price_mapping.get(model_code, "")
            features = feature_mapping.get(model_code, [])

            await wait_and_click(driver, (By.ID, prod_variant.get_attribute("id")))  # type: ignore
            prod_range_buttons = prod_range_tab.find_elements(
                        By.CLASS_NAME, "specification-tab__button"
                        )
            try:
                active_button = [but for but in prod_range_buttons if but.get_attribute("aria-selected") == "true"][0]
            except IndexError:
                active_button = prod_range_buttons[0]

            prod_range_name = active_button.text.strip()
            colors = prod_range_to_colors[prod_range_name]
            try:
                table_source = driver.page_source
            except InvalidArgumentException:
                table_source = ""

            for color in colors:
                variant_name = f"{prod_variant.text.strip()}<SEP>{color}"
                result = {
                    "variant_name": variant_name,
                    "html": table_source,
                    "price": price,
                    "model_code": model_code,
                    "variant_features": features,
                    "product_range": prod_range_name,
                }
                results.append(result)

    for result in results:
        result.update(url_data)
        spec_file_name = md5(str(result).encode("utf-8")).hexdigest()[:16] + ".json"
        with open(output_dir / spec_file_name, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)


async def load_C(driver: WebDriver, link: str, output_dir: Path, url_data: dict):
    await asyncio.sleep(DEFAULT_SLEEP)
    product_range = url_data["product_range"]
    variant_features = url_data["variant_features"]
    variant_name = "<SEP>".join([product_range] + variant_features)
    try:
        source = driver.page_source
    except InvalidArgumentException:
        source = ""

    result = {"html": source, "variant_name": variant_name}
    result.update(url_data)
    text_file_name = md5(str(link).encode("utf-8")).hexdigest()[:16] + ".html"
    with open(output_dir / text_file_name, "w", encoding="utf-8") as f:
        f.write(source)

    spec_file_name = md5(str(result).encode("utf-8")).hexdigest()[:16] + ".json"
    with open(output_dir / spec_file_name, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


async def detect_layout_type(driver: WebDriver) -> str:
    # pylint: disable=too-many-return-statements
    await asyncio.sleep(DEFAULT_SLEEP)
    try:
        spec_tab = driver.find_element(By.ID, "anchor_pd-g-product-specs")
        if spec_tab.is_displayed():
            return "A"
        if driver.current_url.split("/")[4] in layout_c_categories:
            return "C"
        return "_"
    except NoSuchElementException:
        try:
            _ = driver.find_element(By.LINK_TEXT, "SPECIFICATIONS")
            return "B"
        except NoSuchElementException:
            try:
                _ = driver.find_element(By.LINK_TEXT, "SPECS")
                return "B"
            except NoSuchElementException:
                if driver.current_url.split("/")[4] == layout_c_categories:
                    return "C"
                return "_"


@retry(
    stop=stop_after_attempt(10),
    retry=retry_if_exception_type((ReadTimeoutError, TimeoutException)),
)
async def scrape_link(
    link: str,
    driver: WebDriver,
    output_dir: Path,
    card: pandas.Series,
):
    driver.get(link)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    url_hash = md5(link.encode("utf-8")).hexdigest()[:16]
    access_time = datetime.isoformat(datetime.utcnow())

    layout_type = await detect_layout_type(driver)

    url_data = {
        "layout_type": layout_type,
        "url": link,
        "access": access_time,
        "url_hash": url_hash,
        "variant_features": card["features"],
        "model_code": card["model_code"],
        "product_range": card["product_range"],
        "price": card["price"],
    }
    match layout_type:
        case "A":
            await load_A(driver, link, output_dir, url_data)

        case "B":
            await load_B(driver, link, output_dir, url_data)

        case "C":
            await load_C(driver, link, output_dir, url_data)

        case _:
            print(f"Unrecognized layout type, skipping {link}")


async def scrape(product_cards: pandas.DataFrame, output_dir: Path):
    drivers, semaphore = await start_drivers(NUM_DRIVERS)
    tasks = [
        get_link(
            scrape_link,
            card["link"],
            semaphore,
            drivers,
            output_dir=output_dir,
            card=card,
        )
        for _, card in product_cards.iterrows()
    ]
    await tqdm.asyncio.tqdm.gather(*tasks)


def load_price_mapping(product_cards: pandas.DataFrame):
    nonempty_prices = product_cards[product_cards["price"].str.len() > 0]
    global price_mapping
    price_mapping = nonempty_prices.set_index("model_code")["price"].to_dict()


def load_feature_mapping(product_cards: pandas.DataFrame):
    nonempty_features = product_cards[product_cards["features"].apply(len) > 0]
    global feature_mapping
    feature_mapping = nonempty_features.set_index("model_code")["features"].to_dict()


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "--links_file", type=Path, help="JSON file with individual product links"
    )
    parser.add_argument(
        "--output_dir", type=Path, help="Directory where htmls will be saved"
    )
    args = parser.parse_args()

    args.output_dir.mkdir(exist_ok=True)
    with open(args.links_file, "r", encoding="utf-8") as f:
        product_cards = pandas.read_json(f)

    product_cards.columns = PRODUCT_CARD_COLUMNNS
    load_price_mapping(product_cards)

    asyncio.run(scrape(product_cards, args.output_dir))


if __name__ == "__main__":
    main()
