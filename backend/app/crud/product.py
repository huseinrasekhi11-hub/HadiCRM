"""CRUD کاتالوگ محصولات"""
from sqlalchemy.orm import Session

from app.models.product import Product


def get_active_products(db: Session):
    return (
        db.query(Product)
        .filter(Product.is_active == True)
        .order_by(Product.id.asc())
        .all()
    )


def get_product(db: Session, product_id: int):
    return (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )


def get_product_by_name(db: Session, name: str):
    return (
        db.query(Product)
        .filter(Product.name == name)
        .first()
    )


def create_product(db: Session, name: str) -> Product:
    product = Product(name=name.strip(), is_active=True)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
