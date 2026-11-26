"""Logika toko Macaroni Holic (database, stok, checkout, struk, laporan).

Tidak bergantung pada UI, jadi bisa diuji tanpa Flet. Skema tabel sama persis
dengan versi desktop (Tkinter), jadi file macaroni_holic.db dari desktop bisa
dipakai di sini.
"""

import csv
import io
import sqlite3
from datetime import datetime

SIZES = ["Size M", "Size L"]
CODES = ["MC", "MC B", "MC CC", "MC B CC"]
SPICE_LEVELS = ["Tidak Pedas", "Pedas Sedang", "Extra Pedas"]
MAYO_OPTIONS = ["Mayo Normal", "Extra Mayo", "Tanpa Mayo"]
PAYMENT_METHODS = ["Tunai", "QRIS", "Transfer"]

INITIAL_MENUS = [
    ("MC", "Macaroni Cheese", "Size M", 10000, 5000, 0),
    ("MC", "Macaroni Cheese", "Size L", 15000, 7500, 0),
    ("MC B", "Macaroni Cheese Bolognese", "Size M", 10000, 5500, 0),
    ("MC B", "Macaroni Cheese Bolognese", "Size L", 15000, 8000, 0),
    ("MC CC", "Macaroni Cheese Chicken Crispy", "Size M", 15000, 8000, 0),
    ("MC CC", "Macaroni Cheese Chicken Crispy", "Size L", 20000, 10500, 0),
    ("MC B CC", "Macaroni Cheese Bolognese Chicken Crispy", "Size M", 15000, 8500, 0),
    ("MC B CC", "Macaroni Cheese Bolognese Chicken Crispy", "Size L", 20000, 11000, 0),
]


class CheckoutError(Exception):
    """Transaksi ditolak (keranjang kosong, uang kurang, atau stok tidak cukup)."""


def format_rp(amount):
    return f"Rp {amount:,.0f}".replace(",", ".")


def item_label(item):
    return f"[{item['code']}] {item['size']} x{item['qty']} ({item['spice']}, {item['mayo']})"


class Store:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    size TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    cost INTEGER NOT NULL,
                    stock INTEGER NOT NULL DEFAULT 0
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trx_code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    total INTEGER NOT NULL,
                    profit INTEGER NOT NULL,
                    payment_method TEXT NOT NULL,
                    cash_paid INTEGER NOT NULL,
                    change_amount INTEGER NOT NULL,
                    items_summary TEXT NOT NULL
                )
            """)
            if self.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
                self.conn.executemany(
                    "INSERT INTO products (code, name, size, price, cost, stock) VALUES (?, ?, ?, ?, ?, ?)",
                    INITIAL_MENUS,
                )

    # ---------- Produk & stok ----------
    def products(self, size="ALL", code="ALL"):
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        if size != "ALL":
            query += " AND size = ?"
            params.append(size)
        if code != "ALL":
            query += " AND code = ?"
            params.append(code)
        query += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(query, params)]

    def set_stock(self, pid, value):
        with self.conn:
            self.conn.execute("UPDATE products SET stock = ? WHERE id = ?", (max(0, int(value)), pid))

    def add_stock(self, pid, amount):
        with self.conn:
            self.conn.execute("UPDATE products SET stock = MAX(0, stock + ?) WHERE id = ?", (amount, pid))

    def reset_all_stocks(self):
        with self.conn:
            self.conn.execute("UPDATE products SET stock = 0")

    # ---------- Checkout ----------
    def checkout(self, cart, method, cash, now=None):
        """Simpan transaksi dan potong stok dalam satu transaksi database.

        Kalau stok salah satu menu ternyata tidak cukup, semua dibatalkan.
        Mengembalikan dict data struk.
        """
        if not cart:
            raise CheckoutError("Keranjang masih kosong.")
        total = sum(i["price"] * i["qty"] for i in cart)
        if method != "Tunai" and not cash:
            cash = total
        if cash < total:
            raise CheckoutError(f"Uang diterima kurang {format_rp(total - cash)}.")

        now = now or datetime.now()
        change = cash - total
        profit = sum((i["price"] - i["cost"]) * i["qty"] for i in cart)
        created_at = now.strftime("%Y-%m-%d %H:%M:%S")
        items_summary = "; ".join(item_label(i) for i in cart)

        need = {}
        for i in cart:
            need[i["pid"]] = need.get(i["pid"], 0) + i["qty"]

        try:
            with self.conn:  # BEGIN ... COMMIT, atau ROLLBACK kalau ada error
                for pid, qty in need.items():
                    cur = self.conn.execute(
                        "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                        (qty, pid, qty),
                    )
                    if cur.rowcount == 0:
                        row = self.conn.execute("SELECT code, size, stock FROM products WHERE id = ?", (pid,)).fetchone()
                        raise CheckoutError(
                            f"Stok [{row['code']}] {row['size']} tinggal {row['stock']} porsi."
                        )
                # Nomor urut harian menjamin nomor struk tidak dobel walau dalam detik yang sama.
                seq = self.conn.execute(
                    "SELECT COUNT(*) FROM transactions WHERE created_at LIKE ?",
                    (now.strftime("%Y-%m-%d") + "%",),
                ).fetchone()[0] + 1
                trx_code = f"MH-{now:%Y%m%d}-{seq:03d}"
                self.conn.execute(
                    """INSERT INTO transactions (trx_code, created_at, total, profit, payment_method,
                                                 cash_paid, change_amount, items_summary)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (trx_code, created_at, total, profit, method, cash, change, items_summary),
                )
        except sqlite3.Error as e:
            raise CheckoutError(f"Gagal menyimpan transaksi: {e}") from e

        return {
            "trx_code": trx_code,
            "created_at": created_at,
            "items": [dict(i) for i in cart],
            "total": total,
            "method": method,
            "cash": cash,
            "change": change,
            "profit": profit,
        }

    # ---------- Laporan ----------
    def stats(self, date_prefix=""):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(total), 0), COALESCE(SUM(profit), 0), COUNT(*) FROM transactions WHERE created_at LIKE ?",
            (date_prefix + "%",),
        ).fetchone()
        return {"omzet": row[0], "profit": row[1], "count": row[2]}

    def transactions(self, date_prefix=""):
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM transactions WHERE created_at LIKE ? ORDER BY id DESC",
                (date_prefix + "%",),
            )
        ]

    def export_csv(self, date_prefix=""):
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["No Struk", "Waktu", "Detail Pesanan", "Metode Bayar", "Total (Rp)", "Laba (Rp)"])
        for t in self.transactions(date_prefix):
            writer.writerow([t["trx_code"], t["created_at"], t["items_summary"], t["payment_method"], t["total"], t["profit"]])
        # BOM supaya Excel membaca UTF-8 dengan benar.
        return "﻿" + buf.getvalue()


def receipt_text(r):
    lines = [
        "================================",
        "         MACARONI HOLIC",
        "    Stay Cheesy, Stay Happy",
        "    @macaroni.holic.official",
        "================================",
        f"No Struk : {r['trx_code']}",
        f"Waktu    : {r['created_at']}",
        f"Metode   : {r['method']}",
        "--------------------------------",
    ]
    for it in r["items"]:
        sub = it["price"] * it["qty"]
        lines.append(f"[{it['code']}] {it['name']} ({it['size']})")
        lines.append(f"  {it['qty']} x {format_rp(it['price'])} = {format_rp(sub)}")
        lines.append(f"  ({it['spice']}, {it['mayo']})")
    lines += [
        "--------------------------------",
        f"TOTAL    : {format_rp(r['total'])}",
        f"BAYAR    : {format_rp(r['cash'])}",
        f"KEMBALI  : {format_rp(r['change'])}",
        "================================",
        " Terima kasih sudah jajan di sini!",
    ]
    return "\n".join(lines)
