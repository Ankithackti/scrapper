import re
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

BASE_URL = "https://www.bigbasket.com"


def normalize_url(url):
    if not url:
        return None
    url = urljoin(BASE_URL, url)
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    # Tracking parameter seen on public BigBasket offer links.
    query.pop("nc", None)
    clean_query = urlencode(query, doseq=True)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, "")
    )


def is_public_offer_url(url):
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc not in {"www.bigbasket.com", "bigbasket.com"}:
        return False

    path = parsed.path.rstrip("/") + "/"
    if not path.startswith("/all-offers/"):
        return False

    # These paths are known to redirect to normal category URLs or fail.
    if "/pc/" in path or "/cl/" in path or "/all-offers/d/more-than-25/c/" in path:
        return False

    return True


def product_id_from_url(url):
    match = re.search(r"/pd/(\d+)(?:/|$)", url or "")
    return match.group(1) if match else None


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def explicit_discount(text):
    patterns = (
        r"(?:get\s*)?(\d+(?:\.\d+)?)\s*%\s*off",
        r"(\d+(?:\.\d+)?)\s*%\s*discount",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            return float(match.group(1))
    return None


def money_values(text):
    values = []
    for value in re.findall(
        r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        text or "",
        re.I,
    ):
        try:
            values.append(float(value.replace(",", "")))
        except ValueError:
            pass
    return values


def calculate_discount(price, mrp):
    if price is None or mrp is None or mrp <= 0 or price >= mrp:
        return 0.0 if price is not None and mrp is not None and price >= mrp else None
    return round(((mrp - price) / mrp) * 100, 2)


def parse_product_card(anchor):
    href = anchor.get("href")

    if not href or "/pd/" not in href:
        return None

    url = normalize_url(href)

    pid = product_id_from_url(url)

    if not pid:
        return None

    # ---------------------------------------------------------
    # Find the closest useful product-card container
    # ---------------------------------------------------------

    candidates = []

    parent = anchor

    for _ in range(8):

        if parent is None:
            break

        text = clean_text(
            " ".join(parent.stripped_strings)
        )

        if text:
            candidates.append(
                (parent, text)
            )

        parent = parent.parent

    # ---------------------------------------------------------
    # Select the smallest container that contains
    # price/MRP/discount information
    # ---------------------------------------------------------

    text = ""

    for _, candidate_text in candidates:

        lower_text = candidate_text.lower()

        has_price = "₹" in candidate_text

        has_mrp = (
            "mrp" in lower_text
            or "m.r.p" in lower_text
        )

        has_discount = (
            "%" in candidate_text
        )

        if (
            has_price
            and has_mrp
            and has_discount
            and len(candidate_text) <= 1200
        ):

            text = candidate_text

            break

    # Fallback
    if not text and candidates:

        text = min(
            candidates,
            key=lambda item: len(item[1])
        )[1]

    text = clean_text(text)

    # ---------------------------------------------------------
    # PRODUCT NAME
    # ---------------------------------------------------------

    name = clean_text(
        anchor.get("title")
        or anchor.get("aria-label")
        or " ".join(anchor.stripped_strings)
    )

    if not name:

        name = text[:250]

    # ---------------------------------------------------------
    # EXPLICIT BIGBASKET DISCOUNT
    # ---------------------------------------------------------

    explicit = explicit_discount(text)

    # ---------------------------------------------------------
    # MRP
    #
    # IMPORTANT:
    # Do NOT use max(values)
    # because the card can contain multiple pack sizes.
    # ---------------------------------------------------------

    mrp = None

    mrp_match = re.search(
        r"(?:mrp|m\.r\.p\.|mp)"
        r"\s*[:\-]?\s*"
        r"(?:₹|Rs\.?|INR)"
        r"\s*"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)",
        text,
        re.I,
    )

    if mrp_match:

        try:

            mrp = float(
                mrp_match.group(1)
                .replace(",", "")
            )

        except ValueError:

            mrp = None

    # ---------------------------------------------------------
    # PRICE
    #
    # Look specifically for "Price:"
    # instead of taking the last price from the card.
    # ---------------------------------------------------------

    price = None

    price_match = re.search(
        r"(?:price)"
        r"\s*[:\-]?\s*"
        r"(?:₹|Rs\.?|INR)"
        r"\s*"
        r"([0-9][0-9,]*(?:\.[0-9]+)?)",
        text,
        re.I,
    )

    if price_match:

        try:

            price = float(
                price_match.group(1)
                .replace(",", "")
            )

        except ValueError:

            price = None

    # ---------------------------------------------------------
    # FALLBACK PRICE
    # ---------------------------------------------------------

    if price is None and mrp is not None:

        # Only inspect text AFTER MRP.
        after_mrp = text[
            mrp_match.end():
        ] if mrp_match else ""

        # Look for the first currency value after MRP.
        after_values = money_values(
            after_mrp
        )

        if after_values:

            possible_price = after_values[0]

            if possible_price < mrp:

                price = possible_price

    # ---------------------------------------------------------
    # CALCULATED DISCOUNT
    # ---------------------------------------------------------

    calculated = calculate_discount(
        price,
        mrp
    )

    # ---------------------------------------------------------
    # IMPORTANT VALIDATION
    #
    # If BigBasket explicitly says 21% OFF
    # and our calculated value says 86.67%,
    # reject the bad calculation.
    # ---------------------------------------------------------

    final_discount = None

    if explicit is not None:

        # BigBasket's displayed discount is preferred.
        final_discount = explicit

        # If prices exist, validate them.
        if calculated is not None:

            difference = abs(
                explicit - calculated
            )

            if difference > 5:

                # Price/MRP extraction is probably
                # mixing different pack sizes.
                #
                # Keep the explicit BigBasket
                # discount instead of using the
                # incorrect calculated value.

                final_discount = explicit

    elif calculated is not None:

        final_discount = calculated

    # ---------------------------------------------------------
    # Reject products where no reliable discount exists
    # ---------------------------------------------------------

    if final_discount is None:

        return None

    return {

        "product_id": pid,

        "name": name or text[:250],

        "product_url": url,

        "price": price,

        "mrp": mrp,

        "discount": round(
            float(final_discount),
            2
        ),

        "explicit_discount": explicit,

        "calculated_discount": calculated,

        "raw_text": text,
    }


def extract_product_links(soup):
    links = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if "/pd/" not in href:
            continue
        normalized = normalize_url(href)
        pid = product_id_from_url(normalized)
        if pid:
            links.setdefault(pid, anchor)
    return links


def extract_public_offer_links(soup):
    result = set()
    for anchor in soup.find_all("a", href=True):
        url = normalize_url(anchor.get("href"))
        if is_public_offer_url(url):
            result.add(url)
    return result
