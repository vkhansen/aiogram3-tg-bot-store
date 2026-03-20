"""
Import menu items from a JSON file into the database.

Supports both JSON and CSV formats.
- JSON: data/menu.json (recommended — supports options field)
- CSV:  data/menu.csv  (flat format — options not supported)

Usage:
    Called automatically on startup from engine.py.
    Only imports if the products table is empty (won't duplicate on restart).
"""

import csv
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Category, Product

DATA_DIR = Path(__file__).parent.parent / "data"


async def _get_or_create_category(session: AsyncSession, name: str) -> int:
    """Get category ID by name, creating it if it doesn't exist."""
    query = select(Category).where(Category.name == name)
    result = await session.execute(query)
    cat = result.scalar()
    if cat:
        return cat.id

    new_cat = Category(name=name)
    session.add(new_cat)
    await session.flush()
    return new_cat.id


async def import_from_json(session: AsyncSession, file_path: str | Path) -> int:
    """
    Import menu from a JSON file. Returns number of products imported.

    Expected JSON format:
    {
      "categories": ["Food", "Drinks"],
      "products": [
        {
          "name": "Kabuli Pulao",
          "description": "Traditional Afghan rice...",
          "price": 180,
          "category": "Food",
          "image": "",
          "options": { ... }       // optional, for future use
        }
      ]
    }
    """
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    # Create categories first
    for cat_name in data.get("categories", []):
        await _get_or_create_category(session, cat_name)

    # Import products
    count = 0
    for item in data.get("products", []):
        cat_id = await _get_or_create_category(session, item["category"])
        product = Product(
            name=item["name"],
            description=item.get("description", ""),
            price=float(item["price"]),
            image=item.get("image") or None,
            category_id=cat_id,
            options=item.get("options"),
        )
        session.add(product)
        count += 1

    await session.commit()
    return count


async def import_from_csv(session: AsyncSession, file_path: str | Path) -> int:
    """
    Import menu from a CSV file. Returns number of products imported.

    Expected CSV columns: name, description, price, category, image
    (options not supported in CSV — use JSON for that)
    """
    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            cat_id = await _get_or_create_category(session, row["category"])
            product = Product(
                name=row["name"],
                description=row.get("description", ""),
                price=float(row["price"]),
                image=row.get("image") or None,
                category_id=cat_id,
                options=None,
            )
            session.add(product)
            count += 1

    await session.commit()
    return count


async def import_menu(session: AsyncSession) -> int:
    """
    Auto-import menu from data/menu.json or data/menu.csv.
    Only runs if the products table is empty.
    Returns number of products imported (0 if skipped).
    """
    # Skip if products already exist
    query = select(Product)
    result = await session.execute(query)
    if result.first():
        return 0

    # Try JSON first, then CSV
    json_path = DATA_DIR / "menu.json"
    csv_path = DATA_DIR / "menu.csv"

    if json_path.exists():
        count = await import_from_json(session, json_path)
        print(f"Imported {count} products from {json_path}")
        return count
    elif csv_path.exists():
        count = await import_from_csv(session, csv_path)
        print(f"Imported {count} products from {csv_path}")
        return count
    else:
        print("No menu file found in data/ directory. Add products via admin panel.")
        return 0
