# DualGraph - Scraper for SpecsQA Dataset

## Overview

This repository contains tools used to scrape __SpecsQA__ dataset for __DualGraph__ project from the Samsung UK store webpage.

## Installation

Install dependencies with:
```bash
poetry install --with dev
```

## Usage

### Step 1: Get product links

The first step, is to obtain links to all the product categories. Given the links, the task is then to obtain all the links to individual product variants. This involves iterating over all the product cards (corresponding to product ranges) shown in a given category, and obtaining all possible parameter combinations (corresponding to products). All of this is done with the `get_links.py` script, which outputs a JSON file containing the product links along with metadata.
```bash
poetry run python -m scraper.get_links --output_file links.json
```

### Step 2: Scrape product pages

Having the product links, the corresponding htmls have to be scraped, according to their respective layouts (we distinguish three types: A, B and C).
```bash
poetry run python -m scraper.async_scrape --links_file links.json --output_dir htmls
```

The scraping code is asynchronous, and uses multiple drivers (multiple instances of the internet browser). The number of these can be manipulated using the `NUM_DRIVERS` constant in the code. Theoretically using more drivers will yield faster scraping, although care must be taken to ensure that the browsers do not fall into the idle state, in which case they will fail to load all the required dynamic content. The best way to do so, seems to be to have all the windows actually visible on the screen. RAM is the other obvious limiting factor.

## Limitations

It should be noted that the scraping code is quite fragile with respect to page layout changes. The version in this repository has been used to obtain data about around 3k products in mid-November 2025. The general logic: 
1. asyncio scraping of categories,
2. then product cards within the categories
3. then product variants within product cards
4. then product specification tables within product variant pages

should be fairly robust, but minor CSS changes might require tweaking the relevant constants.

## Related Repositories

- **DualGraph_dataset**: Raw scraped data for SpecsQA dataset - https://github.com/SamsungLabs/DualGraph_dataset
- **DualGraph**: Main project including raw data preprocessing and evaluation code - https://github.com/SamsungLabs/DualGraph
