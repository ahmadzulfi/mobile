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
            # Tabel & kolom tambahan versi mobile. Versi desktop tetap bisa membaca database ini.
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS transaction_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trx_id INTEGER NOT NULL,
                    pid INTEGER,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    size TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    cost INTEGER NOT NULL,
                    qty INTEGER NOT NULL,
                    spice TEXT NOT NULL,
                    mayo TEXT NOT NULL
                )
            """)
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(transactions)")]
            if "edited_at" not in cols:
                self.conn.execute("ALTER TABLE transactions ADD COLUMN edited_at TEXT")
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

    def codes(self):
        """Kode menu yang ada di database, urut sesuai menu pertama kali dibuat."""
        return [r[0] for r in self.conn.execute("SELECT code FROM products GROUP BY code ORDER BY MIN(id)")]

    @staticmethod
    def _clean_menu(code, name, size, price, cost):
        code, name, size = code.strip().upper(), name.strip(), size.strip()
        if not code or not name or not size:
            raise ValueError("Kode, nama, dan ukuran wajib diisi.")
        price, cost = int(price), int(cost)
        if price <= 0 or cost < 0:
            raise ValueError("Harga jual harus lebih dari 0 dan modal tidak boleh minus.")
        return code, name, size, price, cost

    def add_product(self, code, name, size, price, cost, stock=0):
        vals = self._clean_menu(code, name, size, price, cost)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO products (code, name, size, price, cost, stock) VALUES (?, ?, ?, ?, ?, ?)",
                (*vals, max(0, int(stock))),
            )
        return cur.lastrowid

    def update_product(self, pid, code, name, size, price, cost):
        vals = self._clean_menu(code, name, size, price, cost)
        with self.conn:
            self.conn.execute(
                "UPDATE products SET code = ?, name = ?, size = ?, price = ?, cost = ? WHERE id = ?",
                (*vals, pid),
            )

    def delete_product(self, pid):
        # Riwayat transaksi tetap aman: detail pesanan disimpan sebagai teks.
        with self.conn:
            self.conn.execute("DELETE FROM products WHERE id = ?", (pid,))

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
    @staticmethod
    def _summarize(items, method, cash):
        if not items:
            raise CheckoutError("Keranjang masih kosong.")
        total = sum(i["price"] * i["qty"] for i in items)
        if method != "Tunai" and not cash:
            cash = total
        if cash < total:
            raise CheckoutError(f"Uang diterima kurang {format_rp(total - cash)}.")
        profit = sum((i["price"] - i["cost"]) * i["qty"] for i in items)
        summary = "; ".join(item_label(i) for i in items)
        return total, profit, cash, cash - total, summary

    def _apply_stock(self, delta):
        """Potong stok sebanyak delta[pid] (nilai minus = stok dikembalikan).

        Harus dipanggil di dalam blok "with self.conn" supaya bisa di-rollback.
        """
        for pid, qty in delta.items():
            if qty > 0:
                cur = self.conn.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?", (qty, pid, qty)
                )
                if cur.rowcount == 0:
                    row = self.conn.execute("SELECT code, size, stock FROM products WHERE id = ?", (pid,)).fetchone()
                    if row is None:
                        raise CheckoutError("Ada menu di pesanan yang sudah dihapus.")
                    raise CheckoutError(f"Stok [{row['code']}] {row['size']} tinggal {row['stock']} porsi.")
            elif qty < 0:
                # Kalau menunya sudah dihapus, tidak ada stok yang perlu dikembalikan.
                self.conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (-qty, pid))

    def _save_items(self, trx_id, items):
        self.conn.execute("DELETE FROM transaction_items WHERE trx_id = ?", (trx_id,))
        self.conn.executemany(
            """INSERT INTO transaction_items (trx_id, pid, code, name, size, price, cost, qty, spice, mayo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(trx_id, i["pid"], i["code"], i["name"], i["size"], i["price"], i["cost"], i["qty"],
              i["spice"], i["mayo"]) for i in items],
        )

    @staticmethod
    def _qty_by_pid(items):
        out = {}
        for i in items:
            out[i["pid"]] = out.get(i["pid"], 0) + i["qty"]
        return out

    def checkout(self, cart, method, cash, now=None):
        """Simpan transaksi dan potong stok dalam satu transaksi database.

        Kalau stok salah satu menu ternyata tidak cukup, semua dibatalkan.
        Mengembalikan dict data struk.
        """
        total, profit, cash, change, summary = self._summarize(cart, method, cash)
        now = now or datetime.now()
        created_at = now.strftime("%Y-%m-%d %H:%M:%S")

        try:
            with self.conn:  # BEGIN ... COMMIT, atau ROLLBACK kalau ada error
                self._apply_stock(self._qty_by_pid(cart))
                # Nomor urut harian; pakai nomor terbesar supaya tetap unik walau ada transaksi yang dihapus.
                prefix = f"MH-{now:%Y%m%d}-"
                last = self.conn.execute(
                    "SELECT MAX(CAST(substr(trx_code, ?) AS INTEGER)) FROM transactions WHERE trx_code LIKE ?",
                    (len(prefix) + 1, prefix + "%"),
                ).fetchone()[0] or 0
                trx_code = f"{prefix}{last + 1:03d}"
                cur = self.conn.execute(
                    """INSERT INTO transactions (trx_code, created_at, total, profit, payment_method,
                                                 cash_paid, change_amount, items_summary)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (trx_code, created_at, total, profit, method, cash, change, summary),
                )
                self._save_items(cur.lastrowid, cart)
        except sqlite3.Error as e:
            raise CheckoutError(f"Gagal menyimpan transaksi: {e}") from e

        return {
            "id": cur.lastrowid,
            "trx_code": trx_code,
            "created_at": created_at,
            "items": [dict(i) for i in cart],
            "total": total,
            "method": method,
            "cash": cash,
            "change": change,
            "profit": profit,
        }

    # ---------- Edit & hapus transaksi ----------
    def transaction_items(self, trx_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT pid, code, name, size, price, cost, qty, spice, mayo FROM transaction_items "
            "WHERE trx_id = ? ORDER BY id", (trx_id,))]

    def receipt(self, trx_id):
        """Data struk dari transaksi yang tersimpan (None kalau detail itemnya tidak ada)."""
        t = self.conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,)).fetchone()
        items = self.transaction_items(trx_id)
        if t is None or not items:
            return None
        return {"id": t["id"], "trx_code": t["trx_code"], "created_at": t["created_at"], "items": items,
                "total": t["total"], "method": t["payment_method"], "cash": t["cash_paid"],
                "change": t["change_amount"], "profit": t["profit"]}

    def update_transaction(self, trx_id, items, method, cash, now=None):
        """Ubah isi transaksi. Stok disesuaikan dengan selisih jumlah porsi lama dan baru.

        Untuk transaksi lama yang detail itemnya tidak tersimpan (items=None),
        hanya metode bayar dan uang diterima yang bisa diubah.
        """
        t = self.conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,)).fetchone()
        if t is None:
            raise CheckoutError("Transaksi tidak ditemukan.")
        edited_at = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        old_items = self.transaction_items(trx_id)

        try:
            with self.conn:
                if items is None:
                    total = t["total"]
                    if method != "Tunai" and not cash:
                        cash = total
                    if cash < total:
                        raise CheckoutError(f"Uang diterima kurang {format_rp(total - cash)}.")
                    self.conn.execute(
                        "UPDATE transactions SET payment_method = ?, cash_paid = ?, change_amount = ?, "
                        "edited_at = ? WHERE id = ?",
                        (method, cash, cash - total, edited_at, trx_id),
                    )
                    return
                if not old_items:
                    raise CheckoutError("Detail item transaksi lama ini tidak tersimpan, jadi item tidak bisa diubah.")

                total, profit, cash, change, summary = self._summarize(items, method, cash)
                old_qty, new_qty = self._qty_by_pid(old_items), self._qty_by_pid(items)
                delta = {pid: new_qty.get(pid, 0) - old_qty.get(pid, 0) for pid in set(old_qty) | set(new_qty)}
                self._apply_stock(delta)
                self.conn.execute(
                    """UPDATE transactions SET total = ?, profit = ?, payment_method = ?, cash_paid = ?,
                       change_amount = ?, items_summary = ?, edited_at = ? WHERE id = ?""",
                    (total, profit, method, cash, change, summary, edited_at, trx_id),
                )
                self._save_items(trx_id, items)
        except sqlite3.Error as e:
            raise CheckoutError(f"Gagal menyimpan perubahan: {e}") from e

    def delete_transaction(self, trx_id, restore_stock=True):
        with self.conn:
            if restore_stock:
                items = self.transaction_items(trx_id)
                self._apply_stock({pid: -q for pid, q in self._qty_by_pid(items).items()})
            self.conn.execute("DELETE FROM transaction_items WHERE trx_id = ?", (trx_id,))
            self.conn.execute("DELETE FROM transactions WHERE id = ?", (trx_id,))

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
