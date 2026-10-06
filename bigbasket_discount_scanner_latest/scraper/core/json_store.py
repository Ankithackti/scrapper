import json
import os


class JsonStore:
    """Incremental JSON store. Data is loaded once and saved atomically."""

    def __init__(self, file_path="output/discount_products.json"):
        self.file_path = file_path
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.products = self.load()

    def load(self):
        if not os.path.exists(self.file_path):
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            result = {}
            if isinstance(data, list):
                for product in data:
                    if isinstance(product, dict) and product.get("product_id"):
                        result[str(product["product_id"])] = product
            return result
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def save(self):
        data = list(self.products.values())
        data.sort(
            key=lambda item: float(item.get("discount_percent") or 0),
            reverse=True,
        )

        temp_file = self.file_path + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        os.replace(temp_file, self.file_path)

    def add_products(self, products):
        changed = 0
        for product in products:
            product_id = product.get("product_id")
            if not product_id:
                continue
            key = str(product_id)
            old = self.products.get(key)
            if old != product:
                self.products[key] = product
                changed += 1

        if changed:
            self.save()

        return len(self.products), changed
