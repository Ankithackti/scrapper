import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup

from scraper.adapters.bigbasket import (
    BASE_URL,
    normalize_url,
    is_public_offer_url,
    parse_product_card,
)
from scraper.core.http_client import AsyncHttpClient
from scraper.core.json_store import JsonStore


LOG = logging.getLogger(__name__)
START_URL = "https://www.bigbasket.com/all-offers/d/more-than-25/"


class BigBasketDiscountMonitor:
    """Fast public-offer scanner with bounded concurrency and incremental JSON output."""

    def __init__(
        self,
        threshold=60,
        pages_per_category=2,
        delay=0.5,
        concurrency=8,
        max_discovery_pages=5000,
        pincode=None,
        location=None,
    ):
        self.threshold = float(threshold)
        self.pages_per_category = max(1, int(pages_per_category))
        self.max_discovery_pages = max(1, int(max_discovery_pages))
        self.pincode = pincode
        self.location = location
        self.client = AsyncHttpClient(
            delay=delay,
            concurrency=concurrency,
        )
        self.store = JsonStore("output/discount_products.json")
        self.visited_categories = set()
        self.visited_pages = set()
        self.visited_products = set(self.store.products.keys())
        self.stats = {
            "pages_ok": 0,
            "pages_failed": 0,
            "products_seen": 0,
            "matching_products": 0,
            "new_products": 0,
        }

    def build_page_url(self, base_url, page_number):
        parsed = urlparse(normalize_url(base_url))
        query = parse_qs(parsed.query, keep_blank_values=True)
        query.pop("nc", None)
        query["page"] = [str(page_number)] if page_number > 1 else []
        query = {k: v for k, v in query.items() if v}
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                urlencode(query, doseq=True),
                "",
            )
        )

    def extract_child_categories(self, html):
        soup = BeautifulSoup(html, "lxml")
        urls = set()
        for anchor in soup.find_all("a", href=True):
            url = normalize_url(anchor.get("href"))
            if is_public_offer_url(url):
                urls.add(url)
        return urls

    def extract_products(self, html, source_url, category_url):
        soup = BeautifulSoup(html, "lxml")
        products = {}

        for anchor in soup.find_all("a", href=True):
            if "/pd/" not in anchor.get("href", ""):
                continue

            parsed = parse_product_card(anchor)
            if not parsed or not parsed.get("product_id"):
                continue

            pid = parsed["product_id"]
            if pid in products:
                continue

            discount = parsed.get("discount")
            if discount is None or discount < self.threshold:
                continue

            products[pid] = {
                "product_id": pid,
                "name": parsed.get("name") or "",
                "url": parsed.get("product_url") or "",
                "mrp": parsed.get("mrp"),
                "price": parsed.get("price"),
                "discount_percent": round(float(discount), 2),
                "category_url": category_url,
                "source_page": source_url,
                "pincode": self.pincode,
                "location": self.location,
                "scanned_at": datetime.now().isoformat(timespec="seconds"),
            }

        return list(products.values())

    async def fetch_page(self, page_url):
        if page_url in self.visited_pages:
            return None

        self.visited_pages.add(page_url)
        response = await self.client.get(page_url)

        if response is None:
            self.stats["pages_failed"] += 1
            LOG.warning("Request failed: %s", page_url)
            return None

        if response.status_code != 200:
            self.stats["pages_failed"] += 1
            LOG.warning("HTTP %s; skipping: %s", response.status_code, page_url)
            return None

        self.stats["pages_ok"] += 1
        return response.text

    async def scan_category(self, category_url):
        category_url = normalize_url(category_url)
        if not category_url or category_url in self.visited_categories:
            return set()

        self.visited_categories.add(category_url)
        LOG.info("Scanning public offer: %s", category_url)

        page_urls = [
            self.build_page_url(category_url, page)
            for page in range(1, self.pages_per_category + 1)
        ]

        # Fetch all requested pages for this category concurrently.
        results = await asyncio.gather(
            *(self.fetch_page(url) for url in page_urls),
            return_exceptions=True,
        )

        discovered = set()
        seen_on_category = set()

        for page_url, result in zip(page_urls, results):
            if isinstance(result, Exception):
                LOG.warning("Page error: %s -> %s", page_url, result)
                continue
            if not result:
                continue

            children = self.extract_child_categories(result)
            discovered.update(children)

            products = self.extract_products(
                result,
                source_url=page_url,
                category_url=category_url,
            )

            self.stats["products_seen"] += len(products)

            new_products = []
            for product in products:
                pid = product["product_id"]
                if pid in seen_on_category:
                    continue
                seen_on_category.add(pid)
                new_products.append(product)

            self.stats["matching_products"] += len(new_products)

            if new_products:
                _, changed = self.store.add_products(new_products)
                self.stats["new_products"] += changed
                self.visited_products.update(p["product_id"] for p in new_products)
                LOG.info(
                    "page=%s matching=%s new_or_updated=%s json_total=%s",
                    page_url,
                    len(new_products),
                    changed,
                    len(self.store.products),
                )

        return discovered

    async def run_once_async(self):
        queue = [START_URL]
        queued = {START_URL}

        LOG.info(
            "Starting BigBasket scan | threshold=%s%% | pages/category=%s | concurrency=%s",
            self.threshold,
            self.pages_per_category,
            self.client.semaphore._value,
        )

        while queue and len(self.visited_categories) < self.max_discovery_pages:
            category_url = queue.pop(0)

            try:
                children = await self.scan_category(category_url)
            except Exception:
                LOG.exception("Unexpected error while scanning: %s", category_url)
                continue

            for child in children:
                if child in queued or child in self.visited_categories:
                    continue
                queued.add(child)
                queue.append(child)

            LOG.info(
                "Progress | categories=%s queued=%s pages_ok=%s products=%s matches=%s json_total=%s",
                len(self.visited_categories),
                len(queue),
                self.stats["pages_ok"],
                self.stats["products_seen"],
                self.stats["matching_products"],
                len(self.store.products),
            )

        self.store.save()
        LOG.info(
            "Scan completed | categories=%s pages_ok=%s pages_failed=%s matches=%s new_or_updated=%s json=%s",
            len(self.visited_categories),
            self.stats["pages_ok"],
            self.stats["pages_failed"],
            self.stats["matching_products"],
            self.stats["new_products"],
            self.store.file_path,
        )

    def run_once(self):
        asyncio.run(self.run_once_async())

    def close(self):
        # Kept for CLI compatibility. run_once owns the asyncio loop.
        return None
