import os
import threading
import customtkinter as ctk
from tkinter import filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from stego.lsb import extract
from stego.crypto_a51 import dekripsi_a51
from stego.metadata import (
    MSG_TYPE_TEXT,
    MSG_TYPE_FILE,
    InvalidHeaderError,
    MODE_RANDOM,
    bytes_to_text,
)
from utils import hitung_mse, hitung_psnr, plot_histogram
import cv2


class ExtractTab(ctk.CTkScrollableFrame):
    """
    Tab ekstraksi pesan
    """

    LSB_PRESETS = {
        "3-3-2  (R:3  G:3  B:2)": (3, 3, 2),
        "2-3-3  (R:2  G:3  B:3)": (2, 3, 3),
        "4-2-2  (R:4  G:2  B:2)": (4, 2, 2),
        "Kustom...":               None,
    }

    def __init__(self, master, app, **kwargs):
        super().__init__(master, **kwargs)
        self._app = app

        # State
        self._stego_path    = ""
        self._cover_path    = ""
        self._extract_thread = None
        self._meta          = None
        self._payload       = None
        self._canvas_widget = None

        self.grid_columnconfigure(0, weight=1)

        self._build_stego_section()
        self._build_config_section()
        self._build_progress_section()
        self._build_action_buttons()
        self._build_result_section()
        self._build_analysis_section()

    def _build_stego_section(self):
        self._section("STEGO-VIDEO", row=0)

        self._lbl("Stego-video (AVI)", row=1)
        row_frame = self._hframe(row=2)
        self._stego_entry = ctk.CTkEntry(
            row_frame, placeholder_text="Belum ada file dipilih...",
            state="disabled", fg_color="transparent",
        )
        self._stego_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            row_frame, text="Pilih File", width=90,
            command=self._pick_stego,
        ).pack(side="right")

        self._sep(row=3)

    def _build_config_section(self):
        self._section("KONFIGURASI EKSTRAKSI", row=4)

        ctk.CTkLabel(
            self,
            text="Skema LSB, stego-key, dan kunci A5/1 harus sama persis dengan saat penyisipan.\n"
                 "Konfigurasi yang salah akan menghasilkan data rusak atau error.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left",
            wraplength=600,
        ).grid(row=5, column=0, sticky="w", padx=16, pady=(0, 8))

        # Skema
        self._lbl("Skema LSB", row=6)
        self._lsb_var = ctk.StringVar(value=list(self.LSB_PRESETS.keys())[0])
        ctk.CTkOptionMenu(
            self,
            variable=self._lsb_var,
            values=list(self.LSB_PRESETS.keys()),
            command=self._on_lsb_change,
        ).grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Kustom
        self._lsb_custom_frame = ctk.CTkFrame(self)
        self._lsb_custom_frame.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._lsb_custom_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self._lsb_custom_frame.grid_remove()

        for i, (ch, color) in enumerate([("R", "#e74c3c"), ("G", "#2ecc71"), ("B", "#3498db")]):
            ctk.CTkLabel(
                self._lsb_custom_frame,
                text=f"Channel {ch} (bit)",
                font=ctk.CTkFont(size=11),
                text_color=color,
            ).grid(row=0, column=i, padx=8, pady=(8, 2))

        self._lsb_r_var = ctk.StringVar(value="3")
        self._lsb_g_var = ctk.StringVar(value="3")
        self._lsb_b_var = ctk.StringVar(value="2")

        for i, var in enumerate([self._lsb_r_var, self._lsb_g_var, self._lsb_b_var]):
            entry = ctk.CTkEntry(
                self._lsb_custom_frame, textvariable=var,
                justify="center", width=60,
            )
            entry.grid(row=1, column=i, padx=8, pady=(0, 4))
            entry.bind("<KeyRelease>", lambda e: self._validate_custom_lsb())

        self._lsb_total_lbl = ctk.CTkLabel(
            self._lsb_custom_frame, text="Total: 8 bit — valid",
            font=ctk.CTkFont(size=11), text_color="#2ecc71",
        )
        self._lsb_total_lbl.grid(row=2, column=0, columnspan=3, pady=(0, 8))

        # Toggle enkripsi A5/1
        self._enc_switch = ctk.CTkSwitch(
            self,
            text="Pesan dienkripsi A5/1",
            command=self._on_enc_toggle,
        )
        self._enc_switch.grid(row=9, column=0, sticky="w", padx=16, pady=(0, 4))

        self._key_entry = ctk.CTkEntry(
            self,
            placeholder_text="Kunci A5/1 (64-bit hex)...",
            show="•", state="disabled",
        )
        self._key_entry.grid(row=10, column=0, sticky="ew", padx=16, pady=(0, 12))

        # Toggle mode acak + stego-key
        self._rnd_switch = ctk.CTkSwitch(
            self,
            text="Penyisipan dilakukan secara acak",
            command=self._on_rnd_toggle,
        )
        self._rnd_switch.grid(row=11, column=0, sticky="w", padx=16, pady=(0, 4))

        self._stegokey_entry = ctk.CTkEntry(
            self,
            placeholder_text="Masukkan stego-key...",
            show="•", state="disabled",
        )
        self._stegokey_entry.grid(row=12, column=0, sticky="ew", padx=16, pady=(0, 12))

        self._sep(row=13)

    def _build_progress_section(self):
        prog_header = ctk.CTkFrame(self, fg_color="transparent")
        prog_header.grid(row=14, column=0, sticky="ew", padx=16, pady=(8, 2))
        prog_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            prog_header, text="Progress ekstraksi",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self._prog_pct_lbl = ctk.CTkLabel(
            prog_header, text="0%",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self._prog_pct_lbl.grid(row=0, column=1, sticky="e")

        self._progress = ctk.CTkProgressBar(self, height=8)
        self._progress.set(0)
        self._progress.grid(row=15, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._log_box = ctk.CTkTextbox(
            self, height=100,
            font=ctk.CTkFont(family="Courier", size=11),
            state="disabled",
            fg_color=("gray90", "gray10"),
        )
        self._log_box.grid(row=16, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._status_lbl = ctk.CTkLabel(
            self, text="● Siap",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._status_lbl.grid(row=17, column=0, sticky="w", padx=16, pady=(0, 4))


    def _build_action_buttons(self):
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=18, column=0, sticky="ew", padx=16, pady=(0, 8))
        btn_frame.grid_columnconfigure(0, weight=1)

        self._extract_btn = ctk.CTkButton(
            btn_frame, text="Ekstrak Pesan",
            height=38, font=ctk.CTkFont(size=14, weight="bold"),
            command=self._run_extract,
        )
        self._extract_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Reset",
            width=90, height=38,
            fg_color="transparent",
            border_width=1,
            command=self._reset,
        ).grid(row=0, column=1)

        self._sep(row=19)

    def _build_result_section(self):
        self._result_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._result_frame.grid(row=20, column=0, sticky="ew", padx=0)
        self._result_frame.grid_columnconfigure(0, weight=1)
        self._result_frame.grid_remove()

        self._section("HASIL EKSTRAKSI", row=0, parent=self._result_frame)

        # Error card
        self._err_card = ctk.CTkFrame(
            self._result_frame,
            fg_color=("#fde8e8", "#2d1010"),
            border_color="#e74c3c",
            border_width=1,
        )
        self._err_card.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self._err_card.grid_columnconfigure(0, weight=1)
        self._err_lbl = ctk.CTkLabel(
            self._err_card,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#e74c3c",
            wraplength=580,
            justify="left",
        )
        self._err_lbl.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self._err_card.grid_remove()

        self._ok_frame = ctk.CTkFrame(self._result_frame, fg_color="transparent")
        self._ok_frame.grid(row=2, column=0, sticky="ew", padx=16)
        self._ok_frame.grid_columnconfigure(0, weight=1)
        self._ok_frame.grid_remove()

        self._badge_frame = ctk.CTkFrame(self._ok_frame, fg_color="transparent")
        self._badge_frame.grid(row=0, column=0, sticky="w", pady=(0, 8))

        # Nama file + tombol simpan
        self._filename_row = ctk.CTkFrame(self._ok_frame, fg_color="transparent")
        self._filename_row.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self._filename_row.grid_columnconfigure(0, weight=1)
        self._lbl("Nama file asli", row=0, parent=self._filename_row)
        save_row = ctk.CTkFrame(self._filename_row, fg_color="transparent")
        save_row.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        save_row.grid_columnconfigure(0, weight=1)
        self._filename_entry = ctk.CTkEntry(save_row, placeholder_text="—")
        self._filename_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._save_btn = ctk.CTkButton(
            save_row, text="Simpan", width=90,
            command=self._save_file,
        )
        self._save_btn.grid(row=0, column=1)

        # Tampilan teks + tombol copy
        self._lbl("Isi pesan", row=2, parent=self._ok_frame)
        self._result_textbox = ctk.CTkTextbox(
            self._ok_frame, height=100,
            font=ctk.CTkFont(family="Courier", size=11),
            state="disabled",
        )
        self._result_textbox.grid(row=3, column=0, sticky="ew", pady=(0, 4))

        self._copy_btn = ctk.CTkButton(
            self._ok_frame, text="Salin ke Clipboard", width=160,
            fg_color="transparent", border_width=1,
            command=self._copy_to_clipboard,
        )
        self._copy_btn.grid(row=4, column=0, sticky="w", pady=(0, 8))

        self._sep(row=21, parent=self._result_frame)

    def _build_analysis_section(self):
        self._analysis_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._analysis_frame.grid(row=22, column=0, sticky="ew", padx=0)
        self._analysis_frame.grid_columnconfigure(0, weight=1)
        self._analysis_frame.grid_remove()

        self._section("ANALISIS KUALITAS", row=0, parent=self._analysis_frame)

        ctk.CTkLabel(
            self._analysis_frame,
            text="Pilih video asli (cover) sebagai pembanding untuk menghitung MSE dan PSNR.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 6))

        cover_row = self._hframe_in(self._analysis_frame, row=2)
        self._cover_entry = ctk.CTkEntry(
            cover_row,
            placeholder_text="Pilih video asli untuk perbandingan...",
            state="disabled", fg_color="transparent",
        )
        self._cover_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            cover_row, text="Pilih File", width=90,
            command=self._pick_cover,
        ).pack(side="right")

        # Metric cards
        cards_frame = ctk.CTkFrame(self._analysis_frame, fg_color="transparent")
        cards_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 12))
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)
        cards_frame.grid_remove()
        self._cards_frame = cards_frame

        self._mse_lbl   = self._metric_card(cards_frame, "MSE (rata-rata)", col=0)
        self._psnr_lbl  = self._metric_card(cards_frame, "PSNR (dB)", col=1)
        self._frame_lbl = self._metric_card(cards_frame, "Frame diproses", col=2)

        # Histogram
        self._hist_header = ctk.CTkFrame(self._analysis_frame, fg_color="transparent")
        self._hist_header.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 4))
        self._hist_header.grid_columnconfigure(0, weight=1)
        self._hist_header.grid_remove()

        ctk.CTkLabel(
            self._hist_header, text="Histogram RGB — perbandingan frame ke-",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        nav_frame = ctk.CTkFrame(self._hist_header, fg_color="transparent")
        nav_frame.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            nav_frame, text="◀", width=32, height=28,
            command=self._prev_frame,
        ).pack(side="left", padx=(0, 4))

        self._frame_num_entry = ctk.CTkEntry(
            nav_frame, width=52, justify="center",
        )
        self._frame_num_entry.insert(0, "0")
        self._frame_num_entry.pack(side="left")
        self._frame_num_entry.bind("<Return>", lambda e: self._on_frame_entry())

        self._frame_total_lbl = ctk.CTkLabel(
            nav_frame, text="/ 0",
            font=ctk.CTkFont(size=11), text_color="gray", width=40,
        )
        self._frame_total_lbl.pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            nav_frame, text="▶", width=32, height=28,
            command=self._next_frame,
        ).pack(side="left", padx=(4, 0))

        self._hist_frame = ctk.CTkFrame(
            self._analysis_frame,
            fg_color=("gray90", "gray15"),
        )
        self._hist_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 16))
        self._hist_frame.grid_columnconfigure(0, weight=1)
        self._hist_frame.grid_remove()

    def _pick_stego(self):
        path = filedialog.askopenfilename(
            title="Pilih stego-video",
            filetypes=[("Video AVI", "*.avi"), ("Semua file", "*.*")],
        )
        if not path:
            return
        self._stego_path = path
        self._set_entry(self._stego_entry, os.path.basename(path))

    def _on_lsb_change(self, value):
        if value == "Kustom...":
            self._lsb_custom_frame.grid()
        else:
            self._lsb_custom_frame.grid_remove()

    def _on_enc_toggle(self):
        if self._enc_switch.get():
            self._key_entry.configure(state="normal")
        else:
            self._key_entry.configure(state="disabled")
            self._key_entry.delete(0, "end")

    def _on_rnd_toggle(self):
        if self._rnd_switch.get():
            self._stegokey_entry.configure(state="normal")
        else:
            self._stegokey_entry.configure(state="disabled")
            self._stegokey_entry.delete(0, "end")

    def _validate_custom_lsb(self) -> bool:
        try:
            r = int(self._lsb_r_var.get())
            g = int(self._lsb_g_var.get())
            b = int(self._lsb_b_var.get())
            total = r + g + b
        except ValueError:
            total = -1

        if total == 8:
            self._lsb_total_lbl.configure(
                text="Total: 8 bit — valid", text_color="#2ecc71",
            )
            self._extract_btn.configure(state="normal")
            return True
        else:
            self._lsb_total_lbl.configure(
                text=f"Total: {total} bit — harus tepat 8",
                text_color="#e74c3c",
            )
            self._extract_btn.configure(state="disabled")
            return False

    def _pick_cover(self):
        path = filedialog.askopenfilename(
            title="Pilih video asli (cover)",
            filetypes=[("Video AVI", "*.avi"), ("Semua file", "*.*")],
        )
        if not path:
            return
        self._cover_path = path
        self._set_entry(self._cover_entry, os.path.basename(path))
        self._run_analysis()


    def _run_extract(self):
        if not self._stego_path:
            self._app.show_error("Input tidak lengkap", "Pilih stego-video terlebih dahulu.")
            return

        lsb_r, lsb_g, lsb_b = self._get_lsb_scheme()
        is_random = bool(self._rnd_switch.get())
        stegokey  = self._stegokey_entry.get() if is_random else ""

        if is_random and not stegokey:
            self._app.show_error("Stego-key kosong", "Mode acak dipilih tapi stego-key belum diisi.")
            return

        use_enc  = bool(self._enc_switch.get())
        key_a51  = self._key_entry.get().strip() if use_enc else ""

        if use_enc and not key_a51:
            self._app.show_error("Kunci kosong", "Enkripsi A5/1 dipilih tapi kunci belum diisi.")
            return

        self._extract_btn.configure(state="disabled", text="Memproses...")
        self._result_frame.grid_remove()
        self._analysis_frame.grid_remove()
        self._reset_progress()
        self._log("[init] Memulai proses ekstraksi...")
        self._set_status("run", "Memproses...")

        def _worker():
            try:
                meta, payload = extract(
                    stego_path  = self._stego_path,
                    lsb_r       = lsb_r,
                    lsb_g       = lsb_g,
                    lsb_b       = lsb_b,
                    stegokey    = stegokey,
                    progress_cb = self._on_progress,
                )
                if meta.is_encrypted:
                    if not key_a51:
                        raise ValueError(
                            "Pesan ini dienkripsi A5/1 tapi kunci tidak diisi."
                        )
                    self.after(0, lambda: self._log("[a5/1] Mendekripsi payload..."))
                    payload = dekripsi_a51(payload, key_a51)
                self.after(0, lambda: self._on_extract_done(meta, payload))
            except InvalidHeaderError as e:
                self.after(0, lambda err=e: self._on_extract_header_error(err))
            except Exception as e:
                self.after(0, lambda err=e: self._on_extract_error(err))

        self._extract_thread = threading.Thread(target=_worker, daemon=True)
        self._extract_thread.start()

    def _on_progress(self, current: int, total: int):
        pct = current / total if total else 0
        self.after(0, lambda p=pct, c=current, t=total: self._update_progress(p, c, t))

    def _update_progress(self, pct: float, current: int, total: int):
        self._progress.set(pct)
        self._prog_pct_lbl.configure(text=f"{int(pct * 100)}%")
        self._log(f"[frame] {current}/{total}")

    def _on_extract_done(self, meta, payload: bytes):
        self._progress.set(1.0)
        self._prog_pct_lbl.configure(text="100%")
        self._log("[done] Ekstraksi berhasil.")
        self._set_status("ok", "Selesai")
        self._extract_btn.configure(state="normal", text="Ekstrak Pesan")

        self._meta    = meta
        self._payload = payload

        self._show_result_ok(meta, payload)
        self._analysis_frame.grid()

    def _on_extract_header_error(self, err: InvalidHeaderError):
        self._progress.set(1.0)
        self._log(f"[error] {err}", level="error")
        self._set_status("err", "Gagal — konfigurasi tidak sesuai")
        self._extract_btn.configure(state="normal", text="Ekstrak Pesan")
        self._show_result_error(str(err))

    def _on_extract_error(self, err: Exception):
        self._log(f"[error] {err}", level="error")
        self._set_status("err", f"Gagal: {err}")
        self._extract_btn.configure(state="normal", text="Ekstrak Pesan")
        self._show_result_error(str(err))


    def _show_result_ok(self, meta, payload: bytes):
        self._result_frame.grid()
        self._err_card.grid_remove()
        self._ok_frame.grid()

        for w in self._badge_frame.winfo_children():
            w.destroy()

        # Badges
        badges = []
        badges.append(("File" if meta.is_file else "Teks", "#7c83fd", "#1e1e3a"))
        if meta.is_file:
            badges.append((meta.extension_str or "—", "#4ade80", "#0a1a0a"))
        if meta.is_encrypted:
            badges.append(("Terenkripsi A5/1", "#fbbf24", "#1a1400"))
        if meta.is_random:
            badges.append(("Mode acak", "#60a5fa", "#0a1020"))

        for i, (text, fg, bg) in enumerate(badges):
            ctk.CTkLabel(
                self._badge_frame, text=text,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=fg,
                fg_color=bg,
                corner_radius=4,
                padx=8, pady=3,
            ).grid(row=0, column=i, padx=(0, 6))

        if meta.is_file:
            self._filename_row.grid()
            self._copy_btn.grid_remove()
            self._result_textbox.grid_remove()
            self._filename_entry.configure(state="normal")
            self._filename_entry.delete(0, "end")
            self._filename_entry.insert(0, meta.filename_str or "extracted_file")
            self._save_btn.configure(state="normal")
        else:
            self._filename_row.grid_remove()
            self._copy_btn.grid()
            self._result_textbox.grid()
            self._result_textbox.configure(state="normal")
            self._result_textbox.delete("1.0", "end")
            self._result_textbox.insert("1.0", bytes_to_text(payload))
            self._result_textbox.configure(state="disabled")

    def _show_result_error(self, message: str):
        self._result_frame.grid()
        self._ok_frame.grid_remove()
        self._err_card.grid()
        self._err_lbl.configure(
            text=f"Header metadata tidak terbaca.\n{message}\n\n"
                 "Pastikan skema LSB, stego-key, dan kunci A5/1 sama persis "
                 "dengan yang digunakan saat penyisipan."
        )

    def _copy_to_clipboard(self):
        text = self._result_textbox.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self._copy_btn.configure(text="Tersalin ✓")
        self.after(2000, lambda: self._copy_btn.configure(text="Salin ke Clipboard"))

    def _save_file(self):
        if self._payload is None:
            return
        default_name = self._filename_entry.get().strip() or "extracted_file"
        path = filedialog.asksaveasfilename(
            title="Simpan file hasil ekstraksi",
            initialfile=default_name,
            defaultextension=self._meta.extension_str if self._meta else "",
        )
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(self._payload)
            self._app.show_info("Berhasil", f"File disimpan ke:\n{path}")
            self._log(f"[save] File disimpan → {os.path.basename(path)}")
        except Exception as e:
            self._app.show_error("Gagal menyimpan", str(e))


    def _run_analysis(self):
        if not self._cover_path or not self._stego_path:
            return

        self._log("[analysis] Memuat frame untuk analisis...")
        meta = self._meta

        def _load():
            try:
                orig_frames, stego_frames = self._load_frames_pair(
                    self._cover_path, self._stego_path
                )
                if meta is not None:
                    step = meta.frame_step
                    modified_indices = [0] + list(range(1, len(orig_frames), step))
                    orig_mod  = [orig_frames[i]  for i in modified_indices if i < len(orig_frames)]
                    stego_mod = [stego_frames[i] for i in modified_indices if i < len(stego_frames)]
                else:
                    orig_mod, stego_mod = orig_frames, stego_frames

                mse_list  = [hitung_mse(o, s) for o, s in zip(orig_mod, stego_mod)]
                psnr_list = [hitung_psnr(m) for m in mse_list]
                avg_mse   = sum(mse_list) / len(mse_list) if mse_list else 0
                avg_psnr  = sum(p for p in psnr_list if p != float('inf')) / \
                            max(1, sum(1 for p in psnr_list if p != float('inf')))

                self.after(0, lambda: self._update_analysis(
                    orig_frames, stego_frames, avg_mse, avg_psnr, len(orig_mod)
                ))
            except Exception as e:
                self.after(0, lambda err=e: self._log(
                    f"[analysis error] {err}", level="error"
                ))

        threading.Thread(target=_load, daemon=True).start()

    def _update_analysis(self, orig_frames, stego_frames, avg_mse, avg_psnr, n_frames):
        self._orig_frames  = orig_frames
        self._stego_frames = stego_frames
        self._current_frame_idx = 0

        self._cards_frame.grid()
        self._hist_header.grid()
        self._hist_frame.grid()

        self._mse_lbl.configure(text=f"{avg_mse:.4f}")
        self._psnr_lbl.configure(text=f"{avg_psnr:.2f}")
        self._frame_lbl.configure(text=str(n_frames))

        total = max(0, len(orig_frames) - 1)
        self._frame_num_entry.delete(0, "end")
        self._frame_num_entry.insert(0, "0")
        self._frame_total_lbl.configure(text=f"/ {total}")

        self._draw_histogram(0)
        self._log(f"[analysis] MSE={avg_mse:.4f}  PSNR={avg_psnr:.2f} dB")

    def _on_frame_entry(self):
        try:
            idx = int(self._frame_num_entry.get())
            idx = max(0, min(idx, len(self._orig_frames) - 1))
        except ValueError:
            idx = 0
        self._current_frame_idx = idx
        self._frame_num_entry.delete(0, "end")
        self._frame_num_entry.insert(0, str(idx))
        self._draw_histogram(idx)

    def _prev_frame(self):
        if not hasattr(self, "_orig_frames") or not self._orig_frames:
            return
        idx = max(0, self._current_frame_idx - 1)
        self._current_frame_idx = idx
        self._frame_num_entry.delete(0, "end")
        self._frame_num_entry.insert(0, str(idx))
        self._draw_histogram(idx)

    def _next_frame(self):
        if not hasattr(self, "_orig_frames") or not self._orig_frames:
            return
        idx = min(len(self._orig_frames) - 1, self._current_frame_idx + 1)
        self._current_frame_idx = idx
        self._frame_num_entry.delete(0, "end")
        self._frame_num_entry.insert(0, str(idx))
        self._draw_histogram(idx)

    def _draw_histogram(self, frame_idx: int):
        if self._canvas_widget:
            self._canvas_widget.get_tk_widget().destroy()
            self._canvas_widget = None

        fig = plot_histogram(
            self._orig_frames[frame_idx],
            self._stego_frames[frame_idx],
        )
        fig.patch.set_facecolor("#1a1a2e")
        for ax in fig.axes:
            ax.set_facecolor("#0f0f23")
            ax.tick_params(colors="gray")
            ax.title.set_color("white")
            for spine in ax.spines.values():
                spine.set_edgecolor("#2a2a4a")

        self._canvas_widget = FigureCanvasTkAgg(fig, master=self._hist_frame)
        self._canvas_widget.draw()
        self._canvas_widget.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

    def _reset(self):
        self._stego_path  = ""
        self._cover_path  = ""
        self._meta        = None
        self._payload     = None
        self._set_entry(self._stego_entry, "")
        self._reset_progress()
        self._result_frame.grid_remove()
        self._analysis_frame.grid_remove()
        self._extract_btn.configure(state="normal", text="Ekstrak Pesan")
        self._set_status("idle", "Siap")

    def _reset_progress(self):
        self._progress.set(0)
        self._prog_pct_lbl.configure(text="0%")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _log(self, msg: str, level: str = ""):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.configure(state="disabled")
        self._log_box.see("end")

    def _set_status(self, state: str, text: str):
        colors = {"ok": "#4ade80", "run": "#7c83fd", "err": "#e74c3c", "idle": "gray"}
        self._status_lbl.configure(
            text=f"● {text}",
            text_color=colors.get(state, "gray"),
        )

    def _set_entry(self, entry: ctk.CTkEntry, value: str):
        entry.configure(state="normal")
        entry.delete(0, "end")
        if value:
            entry.insert(0, value)
        entry.configure(state="disabled")

    def _get_lsb_scheme(self) -> tuple:
        key    = self._lsb_var.get()
        preset = self.LSB_PRESETS.get(key)
        if preset:
            return preset
        try:
            return (
                int(self._lsb_r_var.get()),
                int(self._lsb_g_var.get()),
                int(self._lsb_b_var.get()),
            )
        except ValueError:
            return (3, 3, 2)

    @staticmethod
    def _load_frames_pair(orig_path: str, stego_path: str):
        def _read(path):
            cap    = cv2.VideoCapture(path)
            frames = []
            while True:
                ret, f = cap.read()
                if not ret:
                    break
                frames.append(f)
            cap.release()
            return frames
        return _read(orig_path), _read(stego_path)

    def _metric_card(self, parent, label: str, col: int) -> ctk.CTkLabel:
        card = ctk.CTkFrame(parent, fg_color=("gray85", "gray20"))
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0))
        card.grid_columnconfigure(0, weight=1)
        val_lbl = ctk.CTkLabel(
            card, text="—",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#7c83fd",
        )
        val_lbl.grid(row=0, column=0, pady=(10, 2))
        ctk.CTkLabel(
            card, text=label,
            font=ctk.CTkFont(size=10), text_color="gray",
        ).grid(row=1, column=0, pady=(0, 10))
        return val_lbl

    def _section(self, text: str, row: int, parent=None):
        p = parent or self
        ctk.CTkLabel(
            p, text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#7c83fd",
        ).grid(row=row, column=0, sticky="w", padx=16, pady=(12, 4))

    def _lbl(self, text: str, row: int, parent=None):
        p = parent or self
        ctk.CTkLabel(
            p, text=text,
            font=ctk.CTkFont(size=12),
        ).grid(row=row, column=0, sticky="w", padx=16, pady=(4, 2))

    def _hframe(self, row: int) -> ctk.CTkFrame:
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
        f.grid_columnconfigure(0, weight=1)
        return f

    def _hframe_in(self, parent, row: int) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
        f.grid_columnconfigure(0, weight=1)
        return f

    def _sep(self, row: int, parent=None):
        p = parent or self
        ctk.CTkFrame(p, height=1, fg_color=("gray80", "gray30")).grid(
            row=row, column=0, sticky="ew", padx=16, pady=(8, 4),
        )