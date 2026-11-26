import os
import sqlite3
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core import CheckoutError, Store, receipt_text  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    for p in s.products():
        s.set_stock(p["id"], 10)
    return s


def item(p, qty, spice="Pedas Sedang", mayo="Mayo Normal"):
    return {"pid": p["id"], "code": p["code"], "name": p["name"], "size": p["size"],
            "price": p["price"], "cost": p["cost"], "qty": qty, "spice": spice, "mayo": mayo}


def stock(store, pid):
    return [p for p in store.products() if p["id"] == pid][0]["stock"]


def test_checkout_saves_items_and_receipt(store):
    a = store.products()[0]
    r = store.checkout([item(a, 2)], "Tunai", 20000)
    items = store.transaction_items(r["id"])
    assert len(items) == 1 and items[0]["qty"] == 2
    assert receipt_text(store.receipt(r["id"])) == receipt_text(r)


def test_edit_qty_adjusts_stock_and_totals(store):
    a, b = store.products()[:2]
    r = store.checkout([item(a, 2)], "Tunai", 20000)
    assert stock(store, a["id"]) == 8

    # 2 porsi A jadi 1, tambah 3 porsi B
    store.update_transaction(r["id"], [item(a, 1), item(b, 3)], "QRIS", 0)
    assert stock(store, a["id"]) == 9
    assert stock(store, b["id"]) == 7
    t = store.transactions()[0]
    assert t["total"] == 10000 + 3 * 15000
    assert t["payment_method"] == "QRIS" and t["change_amount"] == 0
    assert t["edited_at"]
    assert "x3" in t["items_summary"]


def test_edit_fails_when_stock_short_and_rolls_back(store):
    a = store.products()[0]
    r = store.checkout([item(a, 2)], "Tunai", 20000)
    with pytest.raises(CheckoutError):
        store.update_transaction(r["id"], [item(a, 50)], "Tunai", 1_000_000)
    assert stock(store, a["id"]) == 8
    assert store.transaction_items(r["id"])[0]["qty"] == 2


def test_edit_cash_too_low(store):
    a = store.products()[0]
    r = store.checkout([item(a, 1)], "Tunai", 10000)
    with pytest.raises(CheckoutError):
        store.update_transaction(r["id"], [item(a, 2)], "Tunai", 10000)


def test_delete_restores_stock(store):
    a = store.products()[0]
    r = store.checkout([item(a, 3)], "Tunai", 30000)
    store.delete_transaction(r["id"])
    assert stock(store, a["id"]) == 10
    assert store.stats()["count"] == 0
    assert store.transaction_items(r["id"]) == []


def test_delete_without_restore(store):
    a = store.products()[0]
    r = store.checkout([item(a, 3)], "Tunai", 30000)
    store.delete_transaction(r["id"], restore_stock=False)
    assert stock(store, a["id"]) == 7


def test_code_stays_unique_after_delete(store):
    a = store.products()[0]
    now = datetime(2026, 11, 26, 9, 0, 0)
    r1 = store.checkout([item(a, 1)], "Tunai", 10000, now=now)
    r2 = store.checkout([item(a, 1)], "Tunai", 10000, now=now)
    store.delete_transaction(r1["id"])
    r3 = store.checkout([item(a, 1)], "Tunai", 10000, now=now)
    assert r3["trx_code"] not in (r1["trx_code"], r2["trx_code"])


def test_legacy_transaction_only_payment_editable(tmp_path):
    """Database dari versi desktop: transaksi tanpa detail item."""
    path = str(tmp_path / "legacy.db")
    Store(path)  # buat skema
    con = sqlite3.connect(path)
    con.execute("""INSERT INTO transactions (trx_code, created_at, total, profit, payment_method,
                   cash_paid, change_amount, items_summary)
                   VALUES ('MH-20261120-101010', '2026-11-20 10:10:10', 15000, 7000, 'Tunai', 20000, 5000,
                           '[MC] Size L x1 (Pedas Sedang, Mayo Normal)')""")
    con.commit()
    con.close()

    s = Store(path)
    t = s.transactions()[0]
    assert s.receipt(t["id"]) is None
    s.update_transaction(t["id"], None, "Transfer", 0)
    t = s.transactions()[0]
    assert t["payment_method"] == "Transfer" and t["cash_paid"] == 15000 and t["change_amount"] == 0
    with pytest.raises(CheckoutError):
        s.update_transaction(t["id"], [item(s.products()[0], 1)], "Tunai", 50000)
