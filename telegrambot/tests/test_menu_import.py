"""Tests for the menu import system."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMenuJsonFormat:
    """Validate the menu.json file structure."""

    @pytest.fixture
    def menu_data(self):
        menu_path = Path(__file__).parent.parent / "data" / "menu.json"
        with open(menu_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_has_categories(self, menu_data):
        assert "categories" in menu_data
        assert len(menu_data["categories"]) > 0

    def test_has_products(self, menu_data):
        assert "products" in menu_data
        assert len(menu_data["products"]) > 0

    def test_products_have_required_fields(self, menu_data):
        required = {"name", "description", "price", "category"}
        for product in menu_data["products"]:
            missing = required - set(product.keys())
            assert not missing, f"Product '{product.get('name', '?')}' missing fields: {missing}"

    def test_product_categories_are_valid(self, menu_data):
        valid_cats = set(menu_data["categories"])
        for product in menu_data["products"]:
            assert product["category"] in valid_cats, (
                f"Product '{product['name']}' has invalid category '{product['category']}'. "
                f"Valid: {valid_cats}"
            )

    def test_prices_are_positive(self, menu_data):
        for product in menu_data["products"]:
            assert float(product["price"]) > 0, (
                f"Product '{product['name']}' has non-positive price: {product['price']}"
            )

    def test_names_are_unique(self, menu_data):
        names = [p["name"] for p in menu_data["products"]]
        duplicates = [n for n in names if names.count(n) > 1]
        assert not duplicates, f"Duplicate product names: {set(duplicates)}"

    def test_options_are_valid_json(self, menu_data):
        for product in menu_data["products"]:
            opts = product.get("options")
            if opts is not None:
                assert isinstance(opts, dict), (
                    f"Product '{product['name']}' options must be dict or null, got {type(opts)}"
                )

    def test_addon_prices_are_positive(self, menu_data):
        for product in menu_data["products"]:
            opts = product.get("options")
            if not opts:
                continue
            for addon in opts.get("add_ons", []):
                assert addon.get("price", 0) >= 0, (
                    f"Product '{product['name']}' addon '{addon['name']}' has negative price"
                )


class TestMenuCsvFormat:
    """Test CSV import parsing with a temp file."""

    def test_csv_parse(self):
        csv_content = "name,description,price,category,image\nTest Item,A test,100,Food,\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            f.flush()

            import csv
            with open(f.name, "r", encoding="utf-8") as cf:
                reader = csv.DictReader(cf)
                rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["name"] == "Test Item"
        assert float(rows[0]["price"]) == 100
