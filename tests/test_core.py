import os, sys
from datetime import datetime
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core import Store, CheckoutError, receipt_text


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "t.db"))


def item(p, qty, spice="Pedas Sedang", mayo="Mayo Normal"):
    return {"pid": p["id"], "code": p["code"], "name": p["name"], "size": p["size"],
            "price": p["price"], "cost": p["cost"], "qty": qty, "spice": spice, "mayo": mayo}


def test_seed_8_menus_stock_zero(store):
    ps = store.products()
    assert len(ps) == 8 and all(p["stock"] == 0 for p in ps)
    assert len(store.products("Size L", "MC CC")) == 1


def test_checkout_cuts_stock_and_records(store):
    p = store.products()[0]
    store.set_stock(p["id"], 5)
    r = store.checkout([item(p, 2)], "Tunai", 50000)
    assert r["total"] == 20000 and r["change"] == 30000 and r["profit"] == 10000
    assert store.products()[0]["stock"] == 3
    assert store.stats()["count"] == 1
    assert "KEMBALI  : Rp 30.000" in receipt_text(r)


def test_insufficient_stock_rolls_back_everything(store):
    a, b = store.products()[:2]
    store.set_stock(a["id"], 5)
    store.set_stock(b["id"], 1)
    with pytest.raises(CheckoutError):
        store.checkout([item(a, 2), item(b, 2)], "Tunai", 100000)
    assert [p["stock"] for p in store.products()[:2]] == [5, 1]
    assert store.stats()["count"] == 0


def test_same_item_split_by_sauce_counts_combined_stock(store):
    p = store.products()[0]
    store.set_stock(p["id"], 3)
    with pytest.raises(CheckoutError):
        store.checkout([item(p, 2), item(p, 2, spice="Extra Pedas")], "QRIS", 0)


def test_cash_short_and_nontunai_autofill(store):
    p = store.products()[0]
    store.set_stock(p["id"], 5)
    with pytest.raises(CheckoutError):
        store.checkout([item(p, 1)], "Tunai", 5000)
    r = store.checkout([item(p, 1)], "QRIS", 0)
    assert r["cash"] == 10000 and r["change"] == 0


def test_unique_codes_same_second(store):
    p = store.products()[0]
    store.set_stock(p["id"], 5)
    now = datetime(2026, 11, 26, 10, 0, 0)
    c1 = store.checkout([item(p, 1)], "Tunai", 10000, now=now)["trx_code"]
    c2 = store.checkout([item(p, 1)], "Tunai", 10000, now=now)["trx_code"]
    assert c1 != c2 and c1 == "MH-20261126-001"


def test_csv_export(store):
    p = store.products()[0]
    store.set_stock(p["id"], 1)
    store.checkout([item(p, 1)], "Transfer", 0)
    out = store.export_csv()
    assert out.startswith("\ufeffNo Struk") and "Transfer" in out


def test_add_edit_delete_menu(store):
    pid = store.add_product(" mc x ", "Macaroni Spesial", "Size L", 25000, 12000)
    p = [x for x in store.products() if x["id"] == pid][0]
    assert p["code"] == "MC X" and p["stock"] == 0
    assert "MC X" in store.codes()

    store.update_product(pid, "MC X", "Macaroni Super", "Size M", 22000, 11000)
    p = [x for x in store.products() if x["id"] == pid][0]
    assert (p["name"], p["size"], p["price"]) == ("Macaroni Super", "Size M", 22000)

    store.delete_product(pid)
    assert all(x["id"] != pid for x in store.products())
    assert "MC X" not in store.codes()


def test_menu_validation(store):
    with pytest.raises(ValueError):
        store.add_product("", "Tanpa kode", "Size M", 10000, 5000)
    with pytest.raises(ValueError):
        store.add_product("MC", "Gratis", "Size M", 0, 0)


def test_checkout_deleted_menu_is_rejected(store):
    p = store.products()[0]
    store.set_stock(p["id"], 5)
    store.delete_product(p["id"])
    with pytest.raises(CheckoutError, match="dihapus"):
        store.checkout([item(p, 1)], "Tunai", 10000)


def test_delete_menu_keeps_history(store):
    p = store.products()[0]
    store.set_stock(p["id"], 1)
    store.checkout([item(p, 1)], "Tunai", 10000)
    store.delete_product(p["id"])
    assert store.stats()["count"] == 1
