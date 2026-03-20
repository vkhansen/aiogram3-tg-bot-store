"""Tests for database models structure."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Base, Banner, Category, Product, User, Cart


class TestModelsExist:
    def test_all_models_have_tablenames(self):
        assert Banner.__tablename__ == "banner"
        assert Category.__tablename__ == "category"
        assert Product.__tablename__ == "product"
        assert User.__tablename__ == "user"
        assert Cart.__tablename__ == "cart"

    def test_product_has_options_field(self):
        columns = {c.name for c in Product.__table__.columns}
        assert "options" in columns, "Product model missing 'options' JSON column"

    def test_user_has_lang_field(self):
        columns = {c.name for c in User.__table__.columns}
        assert "lang" in columns, "User model missing 'lang' column"

    def test_product_required_columns(self):
        columns = {c.name for c in Product.__table__.columns}
        required = {"id", "name", "description", "price", "image", "category_id", "options"}
        missing = required - columns
        assert not missing, f"Product missing columns: {missing}"

    def test_user_required_columns(self):
        columns = {c.name for c in User.__table__.columns}
        required = {"id", "user_id", "first_name", "last_name", "phone", "lang"}
        missing = required - columns
        assert not missing, f"User missing columns: {missing}"

    def test_base_has_timestamps(self):
        for model in [Banner, Category, Product, User, Cart]:
            columns = {c.name for c in model.__table__.columns}
            assert "created" in columns, f"{model.__name__} missing 'created'"
            assert "updated" in columns, f"{model.__name__} missing 'updated'"
