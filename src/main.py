"""Macaroni Holic POS - versi mobile (Flet).

Jalankan di komputer : flet run src/main.py      (atau: python src/main.py)
Build APK Android    : flet build apk
"""

import os
from datetime import datetime

import flet as ft

from core import (
    MAYO_OPTIONS, PAYMENT_METHODS, SIZES, SPICE_LEVELS,
    CheckoutError, Store, format_rp, receipt_text,
)

PURPLE = "#3B1E6D"
PURPLE_DARK = "#27124C"
PURPLE_SOFT = "#E2DCF0"
YELLOW = "#FFD200"
BG = "#F4F2F8"
WHITE = "#FFFFFF"
TEXT = "#1E1B2E"
MUTED = "#6B6580"
DANGER = "#D92D20"
DANGER_SOFT = "#FEE4E2"
SUCCESS = "#12B76A"
WARNING = "#D97706"


def db_path():
    # Di Android/iOS, Flet menyediakan folder data aplikasi yang tidak hilang saat update.
    folder = os.getenv("FLET_APP_STORAGE_DATA") or os.path.dirname(os.path.abspath(__file__))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "macaroni_holic.db")


def pill(text, bg, fg, size=11):
    return ft.Container(
        content=ft.Text(text, size=size, weight=ft.FontWeight.BOLD, color=fg),
        bgcolor=bg,
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        border_radius=6,
    )


def chip(text, selected, on_click):
    return ft.Container(
        content=ft.Text(text, size=13, weight=ft.FontWeight.BOLD, color=YELLOW if selected else PURPLE),
        bgcolor=PURPLE if selected else PURPLE_SOFT,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        border_radius=20,
        on_click=on_click,
        ink=True,
    )


def card(content, padding=14):
    return ft.Container(
        content=content,
        bgcolor=WHITE,
        padding=padding,
        border_radius=12,
        border=ft.Border.all(1, "#E7E3EF"),
    )


def stock_color(stock):
    return DANGER if stock == 0 else (SUCCESS if stock >= 10 else WARNING)


class PosApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.store = Store(db_path())
        self.cart = []
        self.size_filter = "ALL"
        self.code_filter = "ALL"
        self.report_today = True

        self.clipboard = ft.Clipboard()
        self.share = ft.Share()
        self.file_picker = ft.FilePicker()

        page.title = "Macaroni Holic POS"
        page.bgcolor = BG
        page.padding = 0
        page.theme = ft.Theme(color_scheme_seed=PURPLE)
        page.theme_mode = ft.ThemeMode.LIGHT

        self.clock = ft.Text("", size=11, color=WHITE)
        page.appbar = ft.AppBar(
            bgcolor=PURPLE,
            toolbar_height=60,
            title=ft.Column(
                [
                    ft.Text("MACARONI HOLIC", size=18, weight=ft.FontWeight.BOLD, color=YELLOW),
                    self.clock,
                ],
                spacing=0,
            ),
        )
        page.navigation_bar = ft.NavigationBar(
            bgcolor=WHITE,
            indicator_color=YELLOW,
            selected_index=0,
            on_change=self.on_nav,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.POINT_OF_SALE, label="Kasir"),
                ft.NavigationBarDestination(icon=ft.Icons.INVENTORY_2, label="Stok"),
                ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART, label="Laporan"),
            ],
        )

        self.body = ft.Container(expand=True)
        page.add(ft.SafeArea(content=self.body, expand=True))
        self.show_tab(0)
        page.run_task(self.tick_clock)

    async def tick_clock(self):
        import asyncio
        while True:
            self.clock.value = "Mode Offline  •  " + datetime.now().strftime("%d/%m/%Y %H:%M")
            try:
                self.clock.update()
            except Exception:
                return
            await asyncio.sleep(20)

    def toast(self, msg, color=PURPLE_DARK):
        self.page.show_dialog(ft.SnackBar(ft.Text(msg, color=WHITE), bgcolor=color))

    # ================= Navigasi =================
    def on_nav(self, e):
        self.show_tab(e.control.selected_index)

    def show_tab(self, idx):
        self.tab = idx
        self.page.navigation_bar.selected_index = idx
        self.body.content = [self.build_pos, self.build_stock, self.build_report][idx]()
        self.page.update()

    def refresh(self):
        self.show_tab(self.tab)

    # ================= TAB KASIR =================
    def build_pos(self):
        def set_size(s):
            self.size_filter = s
            self.refresh()

        def set_code(c):
            self.code_filter = c
            self.refresh()

        codes = self.store.codes()
        if self.code_filter not in codes:
            self.code_filter = "ALL"

        size_row = ft.Row(
            [chip("Semua" if s == "ALL" else s, self.size_filter == s, lambda e, s=s: set_size(s))
             for s in ["ALL"] + SIZES],
            spacing=6,
        )
        code_row = ft.Row(
            [chip("Semua" if c == "ALL" else c, self.code_filter == c, lambda e, c=c: set_code(c))
             for c in ["ALL"] + codes],
            spacing=6,
            scroll=ft.ScrollMode.HIDDEN,
        )

        products = self.store.products(self.size_filter, self.code_filter)
        grid = ft.ResponsiveRow(
            [ft.Container(self.product_card(p), col={"xs": 12, "sm": 6, "lg": 4}) for p in products],
            spacing=10,
            run_spacing=10,
        )
        if not products:
            grid = ft.Text("Tidak ada menu untuk filter ini.", color=MUTED)

        return ft.Column(
            [
                ft.Container(ft.Column([size_row, code_row], spacing=8),
                             padding=ft.Padding.only(left=12, right=12, top=12)),
                ft.Container(ft.Column([grid], scroll=ft.ScrollMode.AUTO, expand=True),
                             padding=ft.Padding.symmetric(horizontal=12), expand=True),
                self.cart_bar(),
            ],
            expand=True,
            spacing=10,
        )

    def in_cart(self, pid):
        return sum(i["qty"] for i in self.cart if i["pid"] == pid)

    def product_card(self, p):
        stock = p["stock"]
        left = stock - self.in_cart(p["id"])
        stock_text = "Stok kosong" if stock == 0 else f"Stok: {stock}"
        if stock > 0 and left < stock:
            stock_text += f" (sisa {left})"

        if stock == 0:
            action = ft.Button(
                "Isi stok", bgcolor=DANGER_SOFT, color=DANGER,
                on_click=lambda e: self.show_tab(1),
            )
        else:
            action = ft.Button(
                "Tambah", icon=ft.Icons.ADD, bgcolor=PURPLE, color=YELLOW,
                disabled=left <= 0,
                on_click=lambda e, p=p: self.open_customize(p),
            )

        return card(ft.Column(
            [
                ft.Row(
                    [
                        pill(p["code"], PURPLE, YELLOW),
                        pill(p["size"], YELLOW if p["size"] == "Size L" else PURPLE_SOFT, PURPLE_DARK),
                        ft.Container(expand=True),
                        ft.Text(stock_text, size=12, weight=ft.FontWeight.BOLD, color=stock_color(stock)),
                    ],
                    spacing=6,
                ),
                ft.Text(p["name"], size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Row(
                    [ft.Text(format_rp(p["price"]), size=17, weight=ft.FontWeight.BOLD, color=PURPLE), action],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=8,
        ))

    def open_customize(self, p):
        max_qty = p["stock"] - self.in_cart(p["id"])
        if max_qty <= 0:
            self.toast("Semua stok menu ini sudah ada di keranjang.", DANGER)
            return

        spice = ft.RadioGroup(
            value="Pedas Sedang",
            content=ft.Column([ft.Radio(value=s, label=s, active_color=PURPLE) for s in SPICE_LEVELS], spacing=0),
        )
        mayo = ft.RadioGroup(
            value="Mayo Normal",
            content=ft.Column([ft.Radio(value=m, label=m, active_color=PURPLE) for m in MAYO_OPTIONS], spacing=0),
        )
        qty = {"n": 1}
        qty_text = ft.Text("1", size=20, weight=ft.FontWeight.BOLD, width=40, text_align=ft.TextAlign.CENTER)

        def step(d):
            qty["n"] = min(max_qty, max(1, qty["n"] + d))
            qty_text.value = str(qty["n"])
            qty_text.update()

        def confirm(e):
            item = {
                "pid": p["id"], "code": p["code"], "name": p["name"], "size": p["size"],
                "price": p["price"], "cost": p["cost"], "qty": qty["n"],
                "spice": spice.value, "mayo": mayo.value,
            }
            # Gabungkan dengan item yang sama persis supaya keranjang rapi.
            for it in self.cart:
                if (it["pid"], it["spice"], it["mayo"]) == (item["pid"], item["spice"], item["mayo"]):
                    it["qty"] += item["qty"]
                    break
            else:
                self.cart.append(item)
            self.page.pop_dialog()
            self.refresh()

        sheet = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            content=ft.Container(
                padding=ft.Padding.only(left=20, right=20, bottom=20),
                content=ft.Column(
                    [
                        ft.Text(f"[{p['code']}] {p['name']}", size=16, weight=ft.FontWeight.BOLD, color=PURPLE),
                        ft.Text(f"{p['size']}  •  {format_rp(p['price'])}", color=MUTED),
                        ft.Divider(),
                        ft.Text("Level pedas / saus sambal", weight=ft.FontWeight.BOLD),
                        spice,
                        ft.Text("Topping saus mayo", weight=ft.FontWeight.BOLD),
                        mayo,
                        ft.Divider(),
                        ft.Row(
                            [
                                ft.Text(f"Jumlah porsi (maks {max_qty})", weight=ft.FontWeight.BOLD),
                                ft.Row(
                                    [
                                        ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=PURPLE, icon_size=30,
                                                      on_click=lambda e: step(-1)),
                                        qty_text,
                                        ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=PURPLE, icon_size=30,
                                                      on_click=lambda e: step(1)),
                                    ],
                                    spacing=0,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row([
                            ft.FilledButton(
                                "MASUKKAN KE KERANJANG", bgcolor=YELLOW, color=PURPLE_DARK,
                                height=50, expand=True, on_click=confirm,
                            )
                        ]),
                    ],
                    tight=True,
                    spacing=6,
                ),
            ),
        )
        self.page.show_dialog(sheet)
    
    def cart_bar(self):
        count = sum(i["qty"] for i in self.cart)
        total = sum(i["price"] * i["qty"] for i in self.cart)
        return ft.Container(
            bgcolor=PURPLE,
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(f"{count} porsi di keranjang", size=12, color=WHITE),
                            ft.Text(format_rp(total), size=18, weight=ft.FontWeight.BOLD, color=YELLOW),
                        ],
                        spacing=0,
                    ),
                    ft.FilledButton(
                        "Bayar", icon=ft.Icons.SHOPPING_CART_CHECKOUT,
                    bgcolor=YELLOW if count else "#6E5A93", color=PURPLE_DARK if count else "#B9AED0",
                        disabled=count == 0, on_click=lambda e: self.open_cart(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    def open_cart(self):
        state = {"method": "Tunai"}
        total = lambda: sum(i["price"] * i["qty"] for i in self.cart)

        cash_field = ft.TextField(
            label="Uang diterima (Rp)", keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(), text_align=ft.TextAlign.RIGHT,
            text_size=18, dense=True,
        )
        change_text = ft.Text("Rp 0", size=18, weight=ft.FontWeight.BOLD, color=SUCCESS)
        total_text = ft.Text("", size=22, weight=ft.FontWeight.BOLD, color=PURPLE)
        items_col = ft.Column(spacing=4)

        def cash_value():
            try:
                return int(cash_field.value or 0)
            except ValueError:
                return 0

        def recalc(update=True):
            t = total()
            total_text.value = format_rp(t)
            diff = cash_value() - t
            change_text.value = format_rp(diff) if diff >= 0 else "Kurang " + format_rp(-diff)
            change_text.color = SUCCESS if diff >= 0 else DANGER
            if update:
                total_text.update()
                change_text.update()

        def set_cash(n):
            cash_field.value = str(n)
            cash_field.update()
            recalc()

        def remove(idx):
            self.cart.pop(idx)
            if not self.cart:
                self.page.pop_dialog()
                self.refresh()
                return
            render_items()
            items_col.update()
            recalc()

        def render_items():
            items_col.controls = [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(f"[{it['code']}] {it['size']}  x{it['qty']}", weight=ft.FontWeight.BOLD),
                                ft.Text(f"{it['spice']}, {it['mayo']}", size=12, color=MUTED),
                            ],
                            spacing=0, expand=True,
                        ),
                        ft.Text(format_rp(it["price"] * it["qty"]), weight=ft.FontWeight.BOLD),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=DANGER, on_click=lambda e, i=idx: remove(i)),
                    ],
                )
                for idx, it in enumerate(self.cart)
            ]

        def on_method(e):
            state["method"] = list(e.control.selected)[0]
            if state["method"] != "Tunai":
                cash_field.value = str(total())
                cash_field.update()
            recalc()

        def clear(e):
            self.cart.clear()
            self.page.pop_dialog()
            self.refresh()

        async def pay(e):
            try:
                result = self.store.checkout(self.cart, state["method"], cash_value())
            except CheckoutError as err:
                self.toast(str(err), DANGER)
                return
            self.cart.clear()
            self.page.pop_dialog()
            self.refresh()
            self.show_receipt(result)

        cash_field.on_change = lambda e: recalc()
        render_items()
        recalc(update=False)

        quick = ft.Row(
            [ft.OutlinedButton("Uang pas", on_click=lambda e: set_cash(total()))]
            + [ft.OutlinedButton(f"{n // 1000}rb", on_click=lambda e, n=n: set_cash(n))
               for n in [10000, 20000, 50000, 100000]],
            spacing=6, scroll=ft.ScrollMode.HIDDEN,
        )

        sheet = ft.BottomSheet(
            show_drag_handle=True,
            scrollable=True,
            content=ft.Container(
                padding=ft.Padding.only(left=20, right=20, bottom=20),
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("KERANJANG PESANAN", size=16, weight=ft.FontWeight.BOLD, color=PURPLE),
                                ft.TextButton("Kosongkan", style=ft.ButtonStyle(color=DANGER), on_click=clear),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        items_col,
                        ft.Divider(),
                        ft.Row([ft.Text("TOTAL BAYAR", weight=ft.FontWeight.BOLD), total_text],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.SegmentedButton(
                            selected=["Tunai"],
                            segments=[ft.Segment(value=m, label=ft.Text(m)) for m in PAYMENT_METHODS],
                            on_change=on_method,
                        ),
                        cash_field,
                        quick,
                        ft.Row([ft.Text("Kembalian", weight=ft.FontWeight.BOLD), change_text],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([
                            ft.FilledButton(
                                "PROSES TRANSAKSI", icon=ft.Icons.RECEIPT_LONG, bgcolor=YELLOW, color=PURPLE_DARK,
                                height=52, expand=True, on_click=pay,
                            )
                        ]),
                    ],
                    tight=True,
                    spacing=10,
                ),
            ),
        )
        self.page.show_dialog(sheet)

    def show_receipt(self, result, title="Transaksi berhasil"):
        text = receipt_text(result)

        async def share(e):
            # Membuka menu Bagikan Android/iOS: pilih WhatsApp, lalu kirim ke pelanggan.
            try:
                await self.share.share_text(text, subject="Struk Macaroni Holic")
            except Exception:
                await self.clipboard.set(text)
                self.toast("Menu Bagikan tidak tersedia di sini. Struk disalin ke clipboard.")

        async def copy(e):
            await self.clipboard.set(text)
            self.toast("Struk disalin ke clipboard.")

        dialog = ft.AlertDialog(
            title=ft.Text(title, color=PURPLE, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [ft.Text(text, font_family="monospace", size=12, selectable=True, color=TEXT)],
                    scroll=ft.ScrollMode.AUTO, tight=True,
                ),
                bgcolor="#FAFAFA", padding=12, border_radius=8, width=340,
            ),
            actions=[
                ft.TextButton("Salin", on_click=copy),
                ft.FilledButton("Bagikan ke WA", icon=ft.Icons.SHARE, bgcolor=PURPLE, color=YELLOW, on_click=share),
                ft.TextButton("Tutup", on_click=lambda e: self.page.pop_dialog()),
            ],
        )
        self.page.show_dialog(dialog)

    # ================= TAB STOK =================
    def build_stock(self):
        def confirm_reset(e):
            def do_reset(e):
                self.store.reset_all_stocks()
                self.page.pop_dialog()
                self.refresh()

            self.page.show_dialog(ft.AlertDialog(
                title=ft.Text("Kosongkan semua stok?"),
                content=ft.Text("Stok semua menu akan diubah menjadi 0."),
                actions=[
                    ft.TextButton("Batal", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton("Kosongkan", bgcolor=DANGER, color=WHITE, on_click=do_reset),
                ],
            ))

        rows = [self.stock_row(p) for p in self.store.products()]
        return ft.Column(
            [
                ft.Container(
                    ft.Row(
                        [
                            ft.Text("Menu & stok", size=18, weight=ft.FontWeight.BOLD, color=PURPLE),
                            ft.Row(
                                [
                                    ft.FilledButton("Menu", icon=ft.Icons.ADD, bgcolor=PURPLE, color=YELLOW,
                                                    tooltip="Tambah menu baru",
                                                    on_click=lambda e: self.open_menu_form()),
                                    ft.IconButton(ft.Icons.DELETE_SWEEP, icon_color=DANGER,
                                                  tooltip="Kosongkan semua stok", on_click=confirm_reset),
                                ],
                                spacing=0,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.Padding.only(left=12, right=12, top=12),
                ),
                ft.Container(
                    ft.Column(
                        [ft.ResponsiveRow([ft.Container(r, col={"xs": 12, "md": 6}) for r in rows],
                                          spacing=10, run_spacing=10)],
                        scroll=ft.ScrollMode.AUTO, expand=True,
                    ),
                    padding=ft.Padding.only(left=12, right=12, bottom=12), expand=True,
                ),
            ],
            expand=True,
        )

    def stock_row(self, p):
        field = ft.TextField(
            value=str(p["stock"]), width=80, dense=True, text_align=ft.TextAlign.CENTER,
            keyboard_type=ft.KeyboardType.NUMBER, input_filter=ft.NumbersOnlyInputFilter(),
        )

        def save(e=None):
            try:
                val = int(field.value or 0)
            except ValueError:
                self.toast("Masukkan angka stok yang benar.", DANGER)
                return
            self.store.set_stock(p["id"], val)
            self.toast(f"Stok [{p['code']}] {p['size']} jadi {max(0, val)} porsi.")
            self.refresh()

        def add_ten(e):
            self.store.add_stock(p["id"], 10)
            self.refresh()

        field.on_submit = save
        return card(ft.Column(
            [
                ft.Row(
                    [
                        pill(p["code"], PURPLE, YELLOW),
                        pill(p["size"], YELLOW if p["size"] == "Size L" else PURPLE_SOFT, PURPLE_DARK),
                        ft.Container(expand=True),
                        ft.Text(f"{p['stock']} porsi", weight=ft.FontWeight.BOLD, color=stock_color(p["stock"])),
                        ft.IconButton(ft.Icons.EDIT_NOTE, icon_color=PURPLE, icon_size=22, tooltip="Edit menu",
                                      on_click=lambda e: self.open_menu_form(p)),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=DANGER, icon_size=22, tooltip="Hapus menu",
                                      on_click=lambda e: self.confirm_delete(p)),
                    ],
                    spacing=0,
                ),
                ft.Text(p["name"], weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Text(f"Jual {format_rp(p['price'])}  •  Modal {format_rp(p['cost'])}", size=12, color=MUTED),
                ft.Row(
                    [
                        field,
                        ft.FilledButton("Simpan", bgcolor=PURPLE, color=YELLOW, on_click=save),
                        ft.FilledButton("+10", bgcolor=YELLOW, color=PURPLE_DARK, on_click=add_ten),
                    ],
                    spacing=8,
                ),
            ],
            spacing=6,
        ), padding=12)

    def open_menu_form(self, p=None):
        """Dialog tambah menu (p=None) atau edit menu yang sudah ada."""
        editing = p is not None
        p = p or {"code": "", "name": "", "size": "Size M", "price": "", "cost": "", "stock": 0}

        field_style = dict(
            dense=True, filled=True, fill_color="#F6F5F9", border_color="#E4E1EC",
            focused_border_color=PURPLE, border_radius=10, text_size=14,
            content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        )

        def text_field(value, **kw):
            return ft.TextField(value=str(value), **field_style, **kw)

        def num_field(value):
            return text_field(value, keyboard_type=ft.KeyboardType.NUMBER,
                              input_filter=ft.NumbersOnlyInputFilter())

        def labeled(label, control, expand=True):
            return ft.Column(
                [ft.Text(f"{label} *", size=12, weight=ft.FontWeight.BOLD, color=TEXT), control],
                spacing=6, expand=expand,
            )

        code = text_field(p["code"], capitalization=ft.TextCapitalization.CHARACTERS)
        name = text_field(p["name"])
        size = ft.Dropdown(
            value=p["size"], editable=True, expand=True,
            options=[ft.DropdownOption(key=s, text=s) for s in SIZES],
            **field_style,
        )
        cost = num_field(p["cost"])
        price = num_field(p["price"])
        stock = num_field(p["stock"])
        error = ft.Text("", color=DANGER, size=12, visible=False)

        def save(e):
            try:
                args = (code.value or "", name.value or "", size.value or "",
                        int(price.value or 0), int(cost.value or 0))
                if editing:
                    self.store.update_product(p["id"], *args)
                    self.store.set_stock(p["id"], int(stock.value or 0))
                else:
                    self.store.add_product(*args, stock=int(stock.value or 0))
            except ValueError as err:
                error.value = str(err) if "invalid literal" not in str(err) else "Harga harus berupa angka."
                error.visible = True
                error.update()
                return
            self.page.pop_dialog()
            self.toast("Menu diperbarui." if editing else "Menu baru ditambahkan.")
            self.refresh()

        title = f"Edit Menu [{p['code']}] - {p['size']}" if editing else "Tambah Menu Baru"
        header = ft.Container(
            bgcolor=PURPLE,
            padding=ft.Padding.only(left=20, right=8, top=8, bottom=8),
            content=ft.Row(
                [
                    ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=WHITE, expand=True),
                    ft.IconButton(ft.Icons.CLOSE, icon_color=WHITE, icon_size=18, tooltip="Tutup",
                                  style=ft.ButtonStyle(bgcolor="#33FFFFFF", shape=ft.CircleBorder()),
                                  on_click=lambda e: self.page.pop_dialog()),
                ],
            ),
        )
        body = ft.Container(
            padding=ft.Padding.only(left=20, right=20, top=20, bottom=20),
            content=ft.Column(
                [
                    ft.Row([labeled("Kode Menu", code), labeled("Ukuran", size)], spacing=12,
                           vertical_alignment=ft.CrossAxisAlignment.START),
                    labeled("Nama Menu", name, expand=False),
                    ft.Row([labeled("Modal / HPP (Rp)", cost), labeled("Harga Jual (Rp)", price)], spacing=12),
                    labeled("Stok Porsi Saat Ini", stock, expand=False),
                    error,
                    ft.Divider(height=8, color="#ECE9F2"),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Batal", expand=True, height=46,
                                style=ft.ButtonStyle(color=TEXT, shape=ft.RoundedRectangleBorder(radius=10)),
                                on_click=lambda e: self.page.pop_dialog(),
                            ),
                            ft.FilledButton(
                                "Simpan Menu", expand=True, height=46, bgcolor=PURPLE, color=YELLOW,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                                on_click=save,
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True, spacing=14, scroll=ft.ScrollMode.AUTO,
            ),
        )

        self.page.show_dialog(ft.AlertDialog(
            bgcolor=WHITE,
            shape=ft.RoundedRectangleBorder(radius=16),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            title_padding=0,
            content_padding=0,
            inset_padding=ft.Padding.symmetric(horizontal=16, vertical=24),
            content=ft.Container(ft.Column([header, body], tight=True, spacing=0), width=400),
        ))

    def confirm_delete(self, p):
        def do_delete(e):
            self.store.delete_product(p["id"])
            self.cart = [i for i in self.cart if i["pid"] != p["id"]]
            self.page.pop_dialog()
            self.toast(f"Menu [{p['code']}] {p['size']} dihapus.")
            self.refresh()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Hapus menu?"),
            content=ft.Text(
                f"[{p['code']}] {p['name']} ({p['size']}) akan dihapus dari daftar menu. "
                "Riwayat transaksi yang sudah ada tidak ikut terhapus."
            ),
            actions=[
                ft.TextButton("Batal", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("Hapus", bgcolor=DANGER, color=WHITE, on_click=do_delete),
            ],
        ))

    # ================= TAB LAPORAN =================
    def build_report(self):
        prefix = datetime.now().strftime("%Y-%m-%d") if self.report_today else ""
        stats = self.store.stats(prefix)
        trxs = self.store.transactions(prefix)

        def set_period(today):
            self.report_today = today
            self.refresh()

        async def export(e):
            data = self.store.export_csv(prefix).encode("utf-8")
            name = f"Laporan_Macaroni_Holic_{datetime.now():%Y%m%d}.csv"
            try:
                if not self.page.web and self.page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
                    await self.share.share_files(
                        [ft.ShareFile.from_bytes(data, mime_type="text/csv", name=name)],
                        subject="Laporan Macaroni Holic",
                    )
                    return
                if self.page.web:
                    # Di browser file langsung diunduh.
                    await self.file_picker.save_file(file_name=name, src_bytes=data)
                    return
                path = await self.file_picker.save_file(
                    dialog_title="Simpan laporan", file_name=name, allowed_extensions=["csv"],
                )
                if path:
                    with open(path, "wb") as f:
                        f.write(data)
                    self.toast(f"Laporan disimpan ke {path}")
            except Exception as err:
                self.toast(f"Gagal export laporan: {err}", DANGER)

        def stat(title, value, color):
            return ft.Container(card(ft.Column(
                [ft.Text(title, size=11, weight=ft.FontWeight.BOLD, color=MUTED),
                 ft.Text(value, size=18, weight=ft.FontWeight.BOLD, color=color)],
                spacing=2,
            ), padding=12), col={"xs": 12, "sm": 4})

        trx_cards = [self.trx_card(t) for t in trxs] or [ft.Text("Belum ada transaksi.", color=MUTED)]

        return ft.Container(
            ft.Column(
                [
                    ft.Row([chip("Hari ini", self.report_today, lambda e: set_period(True)),
                            chip("Semua", not self.report_today, lambda e: set_period(False))], spacing=6),
                    ft.ResponsiveRow(
                        [stat("TOTAL OMZET", format_rp(stats["omzet"]), PURPLE),
                         stat("ESTIMASI LABA", format_rp(stats["profit"]), SUCCESS),
                         stat("JUMLAH TRANSAKSI", f"{stats['count']} transaksi", WARNING)],
                        spacing=8, run_spacing=8,
                    ),
                    ft.Row(
                        [ft.Text("Riwayat transaksi", size=16, weight=ft.FontWeight.BOLD, color=PURPLE),
                         ft.FilledButton("Export CSV", icon=ft.Icons.IOS_SHARE, bgcolor=PURPLE, color=YELLOW,
                                         disabled=not trxs, on_click=export)],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    *trx_cards,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=12,
            expand=True,
        )


    # ================= EDIT / HAPUS TRANSAKSI =================
    def trx_card(self, t):
        has_items = bool(self.store.transaction_items(t["id"]))

        def show(e):
            self.show_receipt(self.store.receipt(t["id"]), title=f"Struk {t['trx_code']}")

        actions = []
        if has_items:
            actions.append(ft.IconButton(ft.Icons.RECEIPT_LONG, icon_color=PURPLE, icon_size=20,
                                         tooltip="Lihat / bagikan struk", on_click=show))
        actions += [
            ft.IconButton(ft.Icons.EDIT_NOTE, icon_color=PURPLE, icon_size=22, tooltip="Edit transaksi",
                          on_click=lambda e: self.open_trx_edit(t)),
            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=DANGER, icon_size=22, tooltip="Hapus transaksi",
                          on_click=lambda e: self.confirm_trx_delete(t, has_items)),
        ]
        time_line = [ft.Text(t["created_at"], size=12, color=MUTED)]
        if t.get("edited_at"):
            time_line.append(pill(f"Diedit {t['edited_at'][11:16]}", "#FEF0C7", "#93370D", size=10))

        return card(ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(t["trx_code"], weight=ft.FontWeight.BOLD, color=PURPLE),
                        pill(t["payment_method"], PURPLE_SOFT, PURPLE_DARK),
                        ft.Container(expand=True),
                        *actions,
                    ],
                    spacing=0,
                ),
                ft.Row(time_line, spacing=8),
                ft.Text(t["items_summary"].replace("; ", "\n"), size=12, color=TEXT),
                ft.Row(
                    [ft.Text(f"Total {format_rp(t['total'])}", weight=ft.FontWeight.BOLD),
                     ft.Text(f"Laba {format_rp(t['profit'])}", color=SUCCESS, weight=ft.FontWeight.BOLD)],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
        ), padding=12)

    def open_trx_edit(self, t):
        legacy = not self.store.transaction_items(t["id"])
        items = None if legacy else self.store.transaction_items(t["id"])
        state = {"method": t["payment_method"]}

        field_style = dict(
            dense=True, filled=True, fill_color="#F6F5F9", border_color="#E4E1EC",
            focused_border_color=PURPLE, border_radius=10, text_size=14,
            content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        )

        def section(label):
            return ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=TEXT)

        total_of = lambda: t["total"] if legacy else sum(i["price"] * i["qty"] for i in items)
        cash = ft.TextField(value=str(t["cash_paid"]), keyboard_type=ft.KeyboardType.NUMBER,
                            input_filter=ft.NumbersOnlyInputFilter(), expand=True, **field_style)
        total_text = ft.Text("", size=18, weight=ft.FontWeight.BOLD, color=PURPLE)
        change_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        error = ft.Text("", color=DANGER, size=12, visible=False)
        items_col = ft.Column(spacing=6)

        def recalc(update=True):
            total = total_of()
            diff = int(cash.value or 0) - total
            total_text.value = format_rp(total)
            change_text.value = format_rp(diff) if diff >= 0 else "Kurang " + format_rp(-diff)
            change_text.color = SUCCESS if diff >= 0 else DANGER
            if update:
                total_text.update()
                change_text.update()

        def set_qty(idx, d):
            items[idx]["qty"] += d
            if items[idx]["qty"] <= 0:
                items.pop(idx)
            render_items()
            items_col.update()
            recalc()

        def render_items():
            if not items:
                items_col.controls = [ft.Text("Belum ada item. Tambahkan minimal satu item, "
                                              "atau hapus transaksinya.", size=12, color=DANGER)]
                return
            items_col.controls = [
                ft.Container(
                    bgcolor="#F6F5F9", border_radius=10, padding=ft.Padding.only(left=12, right=4, top=6, bottom=6),
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(f"[{it['code']}] {it['size']}", weight=ft.FontWeight.BOLD, size=13),
                                    ft.Text(f"{it['spice']}, {it['mayo']}", size=11, color=MUTED),
                                    ft.Text(format_rp(it["price"] * it["qty"]), size=12, color=PURPLE,
                                            weight=ft.FontWeight.BOLD),
                                ],
                                spacing=0, expand=True,
                            ),
                            ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=PURPLE, icon_size=22,
                                          on_click=lambda e, i=idx: set_qty(i, -1)),
                            ft.Text(str(it["qty"]), size=16, weight=ft.FontWeight.BOLD, width=24,
                                    text_align=ft.TextAlign.CENTER),
                            ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=PURPLE, icon_size=22,
                                          on_click=lambda e, i=idx: set_qty(i, 1)),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=DANGER, icon_size=20,
                                          tooltip="Hapus item", on_click=lambda e, i=idx: set_qty(i, -items[i]["qty"])),
                        ],
                        spacing=0,
                    ),
                )
                for idx, it in enumerate(items)
            ]

        products = {str(p["id"]): p for p in self.store.products()}
        new_menu = ft.Dropdown(
            hint_text="Pilih menu", expand=True, **field_style,
            options=[ft.DropdownOption(key=k, text=f"[{p['code']}] {p['size']} - {format_rp(p['price'])}")
                     for k, p in products.items()],
        )

        def add_item(e):
            p = products.get(new_menu.value or "")
            if not p:
                return
            for it in items:
                if (it["pid"], it["spice"], it["mayo"]) == (p["id"], "Pedas Sedang", "Mayo Normal"):
                    it["qty"] += 1
                    break
            else:
                items.append({"pid": p["id"], "code": p["code"], "name": p["name"], "size": p["size"],
                              "price": p["price"], "cost": p["cost"], "qty": 1,
                              "spice": "Pedas Sedang", "mayo": "Mayo Normal"})
            render_items()
            items_col.update()
            recalc()

        def on_method(e):
            state["method"] = list(e.control.selected)[0]
            if state["method"] != "Tunai":
                cash.value = str(total_of())
                cash.update()
            recalc()

        def exact(e):
            cash.value = str(total_of())
            cash.update()
            recalc()

        def save(e):
            try:
                self.store.update_transaction(t["id"], items, state["method"], int(cash.value or 0))
            except CheckoutError as err:
                error.value = str(err)
                error.visible = True
                error.update()
                return
            self.page.pop_dialog()
            self.toast(f"Transaksi {t['trx_code']} diperbarui.")
            self.refresh()

        cash.on_change = lambda e: recalc()
        recalc(update=False)

        if legacy:
            item_section = [
                section("Detail pesanan"),
                ft.Container(
                    bgcolor="#FEF0C7", border_radius=10, padding=12,
                    content=ft.Text(
                        "Transaksi ini dibuat sebelum detail item disimpan, jadi item-nya tidak bisa diubah. "
                        "Metode bayar dan uang diterima tetap bisa diedit.\n\n"
                        + t["items_summary"].replace("; ", "\n"),
                        size=12, color="#93370D",
                    ),
                ),
            ]
        else:
            render_items()
            item_section = [
                section("Item pesanan"),
                items_col,
                ft.Row([new_menu, ft.FilledButton("Tambah", icon=ft.Icons.ADD, bgcolor=PURPLE, color=YELLOW,
                                                  height=44, on_click=add_item)], spacing=8),
                ft.Text("Item tambahan memakai saus Pedas Sedang & Mayo Normal.", size=11, color=MUTED),
            ]

        header = ft.Container(
            bgcolor=PURPLE,
            padding=ft.Padding.only(left=20, right=8, top=8, bottom=8),
            content=ft.Row(
                [
                    ft.Column(
                        [ft.Text(f"Edit Transaksi {t['trx_code']}", size=16, weight=ft.FontWeight.BOLD,
                                 color=WHITE),
                         ft.Text(t["created_at"], size=11, color="#D9D0EC")],
                        spacing=0, expand=True,
                    ),
                    ft.IconButton(ft.Icons.CLOSE, icon_color=WHITE, icon_size=18, tooltip="Tutup",
                                  style=ft.ButtonStyle(bgcolor="#33FFFFFF", shape=ft.CircleBorder()),
                                  on_click=lambda e: self.page.pop_dialog()),
                ],
            ),
        )
        body = ft.Container(
            padding=20,
            content=ft.Column(
                [
                    *item_section,
                    ft.Divider(height=8, color="#ECE9F2"),
                    section("Metode bayar"),
                    ft.SegmentedButton(
                        selected=[t["payment_method"]],
                        segments=[ft.Segment(value=m, label=ft.Text(m)) for m in PAYMENT_METHODS],
                        on_change=on_method,
                    ),
                    section("Uang diterima (Rp)"),
                    ft.Row([cash, ft.OutlinedButton("Uang pas", height=44, on_click=exact)], spacing=8),
                    ft.Row([ft.Text("Total", weight=ft.FontWeight.BOLD), total_text],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([ft.Text("Kembalian", weight=ft.FontWeight.BOLD), change_text],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("Stok porsi otomatis disesuaikan dengan perubahan jumlah item.", size=11, color=MUTED)
                    if not legacy else ft.Container(),
                    error,
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Batal", expand=True, height=46,
                                style=ft.ButtonStyle(color=TEXT, shape=ft.RoundedRectangleBorder(radius=10)),
                                on_click=lambda e: self.page.pop_dialog(),
                            ),
                            ft.FilledButton(
                                "Simpan Perubahan", expand=True, height=46, bgcolor=PURPLE, color=YELLOW,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                                on_click=save,
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                tight=True, spacing=12, scroll=ft.ScrollMode.AUTO,
            ),
        )
        self.page.show_dialog(ft.AlertDialog(
            bgcolor=WHITE,
            shape=ft.RoundedRectangleBorder(radius=16),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            title_padding=0,
            content_padding=0,
            inset_padding=ft.Padding.symmetric(horizontal=16, vertical=24),
            content=ft.Container(ft.Column([header, body], tight=True, spacing=0), width=420),
        ))

    def confirm_trx_delete(self, t, has_items):
        restore = ft.Checkbox(label="Kembalikan stok porsi", value=True, active_color=PURPLE, visible=has_items)

        def do_delete(e):
            self.store.delete_transaction(t["id"], restore_stock=has_items and bool(restore.value))
            self.page.pop_dialog()
            self.toast(f"Transaksi {t['trx_code']} dihapus.")
            self.refresh()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Hapus transaksi?"),
            content=ft.Column(
                [
                    ft.Text(f"{t['trx_code']} ({format_rp(t['total'])}) akan dihapus dari laporan. "
                            "Ini tidak bisa dibatalkan."),
                    restore,
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Batal", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("Hapus", bgcolor=DANGER, color=WHITE, on_click=do_delete),
            ],
        ))


def main(page: ft.Page):
    PosApp(page)


if __name__ == "__main__":
    ft.run(main)
