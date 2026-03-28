"""
main_window.py
--------------
Window utama aplikasi StegoVideo menggunakan CustomTkinter.
Berisi kerangka window, TabView (Sisipkan / Ekstrak),
dan method-method shared yang bisa dipanggil oleh tab.
"""

import customtkinter as ctk
from gui.embed_tab import EmbedTab
from gui.extract_tab import ExtractTab


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MainWindow(ctk.CTk):
    """
    Window utama aplikasi.

    Struktur widget:
        MainWindow (CTk)
        └── CTkTabview
            ├── tab "Sisipkan Pesan" 
            └── tab "Ekstrak Pesan" 
    """

    APP_TITLE   = "StegoVideo — Steganografi LSB pada Video AVI"
    MIN_WIDTH   = 700
    MIN_HEIGHT  = 720
    INIT_WIDTH  = 780
    INIT_HEIGHT = 820

    TAB_EMBED   = "  Sisipkan Pesan  "
    TAB_EXTRACT = "  Ekstrak Pesan  "

    def __init__(self):
        super().__init__()

        self._setup_window()
        self._build_header()
        self._build_tabview()

    def _setup_window(self):
        self.title(self.APP_TITLE)
        self.geometry(f"{self.INIT_WIDTH}x{self.INIT_HEIGHT}")
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resizable(True, True)

        # Grid utama: header (row 0) + tabview (row 1, expandable)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="StegoVideo",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Steganografi LSB pada Video AVI  ·  Kriptografi II4021",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).grid(row=1, column=0, sticky="w")

        # Separator
        sep = ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30"))
        sep.grid(row=0, column=0, sticky="sew", padx=20, pady=(0, 0))

    def _build_tabview(self):
        self._tabview = ctk.CTkTabview(
            self,
            anchor="nw",
            fg_color=("gray95", "gray17"),
        )
        self._tabview.grid(
            row=1, column=0,
            sticky="nsew",
            padx=16, pady=(8, 16),
        )

        # Tambah tab
        self._tabview.add(self.TAB_EMBED)
        self._tabview.add(self.TAB_EXTRACT)

        for tab_name in (self.TAB_EMBED, self.TAB_EXTRACT):
            tab = self._tabview.tab(tab_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

        # Inisialisasi konten tiap tab
        self._embed_tab = EmbedTab(
            master=self._tabview.tab(self.TAB_EMBED),
            app=self,
        )
        self._embed_tab.grid(row=0, column=0, sticky="nsew")

        self._extract_tab = ExtractTab(
            master=self._tabview.tab(self.TAB_EXTRACT),
            app=self,
        )
        self._extract_tab.grid(row=0, column=0, sticky="nsew")



    def switch_to_extract(self):
        self._tabview.set(self.TAB_EXTRACT)

    def switch_to_embed(self):
        self._tabview.set(self.TAB_EMBED)

    def show_error(self, title: str, message: str):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("420x180")
        dialog.resizable(False, False)
        dialog.grab_set() 

        dialog.grid_rowconfigure(0, weight=1)
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text=message,
            wraplength=380,
            justify="left",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=0, padx=24, pady=(24, 8), sticky="nsew")

        ctk.CTkButton(
            dialog,
            text="Tutup",
            width=100,
            command=dialog.destroy,
        ).grid(row=1, column=0, pady=(0, 16))

    def show_info(self, title: str, message: str):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("420x180")
        dialog.resizable(False, False)
        dialog.grab_set()

        dialog.grid_rowconfigure(0, weight=1)
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text=message,
            wraplength=380,
            justify="left",
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=0, padx=24, pady=(24, 8), sticky="nsew")

        ctk.CTkButton(
            dialog,
            text="OK",
            width=100,
            command=dialog.destroy,
        ).grid(row=1, column=0, pady=(0, 16))