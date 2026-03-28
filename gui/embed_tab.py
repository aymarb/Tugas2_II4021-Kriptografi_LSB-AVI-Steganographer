import os
import threading
import customtkinter as ctk
from tkinter import filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from stego.lsb import embed, check_capacity
from stego.crypto_a51 import enkripsi_a51
from stego.metadata import (
    MSG_TYPE_TEXT,
    MSG_TYPE_FILE,
    ENC_NONE,
    ENC_A5_1,
    MODE_SEQUENTIAL,
    MODE_RANDOM,
    text_to_bytes,
)
from utils import hitung_mse, hitung_psnr, plot_histogram
import cv2


class EmbedTab(ctk.CTkScrollableFrame):
    """
    Tab penyisipan pesan
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
        self._cover_path   = ""
        self._msg_file_path = ""
        self._embed_thread  = None
        self._canvas_widget = None   
        self._cover_frames  = None   
        self._stego_frames  = None

        self.grid_columnconfigure(0, weight=1)

        self._build_video_section()
        self._build_config_section()
        self._build_progress_section()
        self._build_action_buttons()
        self._build_analysis_section()

    def _build_video_section(self):
        self._section("VIDEO & PESAN", row=0)

        # Video cover
        self._lbl("Video cover (AVI)", row=1)
        row_frame = self._hframe(row=2)
        self._cover_entry = ctk.CTkEntry(
            row_frame, placeholder_text="Belum ada file dipilih...",
            state="disabled", fg_color="transparent",
        )
        self._cover_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            row_frame, text="Pilih File", width=90,
            command=self._pick_cover,
        ).pack(side="right")

        # Jenis pesan
        self._lbl("Jenis pesan", row=3)
        self._msg_type_var = ctk.StringVar(value="Teks")
        seg = ctk.CTkSegmentedButton(
            self, values=["Teks", "File"],
            variable=self._msg_type_var,
            command=self._on_msg_type_change,
        )
        seg.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Input teks
        self._text_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._text_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 4))
        self._text_frame.grid_columnconfigure(0, weight=1)
        self._lbl("Isi pesan", row=0, parent=self._text_frame)
        self._msg_textbox = ctk.CTkTextbox(self._text_frame, height=80)
        self._msg_textbox.grid(row=1, column=0, sticky="ew")
        self._msg_textbox.bind("<KeyRelease>", lambda e: self._update_capacity())

        # Input file
        self._file_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._file_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 4))
        self._file_frame.grid_columnconfigure(0, weight=1)
        self._file_frame.grid_remove()  # hidden by default
        self._lbl("File pesan", row=0, parent=self._file_frame)
        file_row = ctk.CTkFrame(self._file_frame, fg_color="transparent")
        file_row.grid(row=1, column=0, sticky="ew")
        file_row.grid_columnconfigure(0, weight=1)
        self._file_entry = ctk.CTkEntry(
            file_row, placeholder_text="Belum ada file dipilih...",
            state="disabled", fg_color="transparent",
        )
        self._file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            file_row, text="Pilih File", width=90,
            command=self._pick_msg_file,
        ).grid(row=0, column=1)

        # Kapasitas
        self._lbl("Kapasitas sisip vs ukuran pesan", row=6)
        self._cap_progress = ctk.CTkProgressBar(self, height=8)
        self._cap_progress.set(0)
        self._cap_progress.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 4))

        cap_info_row = ctk.CTkFrame(self, fg_color="transparent")
        cap_info_row.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 2))
        cap_info_row.grid_columnconfigure(0, weight=1)
        cap_info_row.grid_columnconfigure(1, weight=1)
        self._cap_msg_lbl = ctk.CTkLabel(
            cap_info_row, text="Pesan: —",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._cap_msg_lbl.grid(row=0, column=0, sticky="w")
        self._cap_max_lbl = ctk.CTkLabel(
            cap_info_row, text="Kapasitas: —",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._cap_max_lbl.grid(row=0, column=1, sticky="e")

        self._cap_err_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11), text_color="#e74c3c",
            wraplength=600, justify="left",
        )
        self._cap_err_lbl.grid(row=9, column=0, sticky="ew", padx=16, pady=(0, 4))

        self._sep(row=10)

    def _build_config_section(self):
        self._section("KONFIGURASI", row=11)

        # Skema LSB
        self._lbl("Skema LSB", row=12)
        self._lsb_var = ctk.StringVar(value=list(self.LSB_PRESETS.keys())[0])
        ctk.CTkOptionMenu(
            self,
            variable=self._lsb_var,
            values=list(self.LSB_PRESETS.keys()),
            command=self._on_lsb_change,
        ).grid(row=13, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Kustom LSB
        self._lsb_custom_frame = ctk.CTkFrame(self)
        self._lsb_custom_frame.grid(row=14, column=0, sticky="ew", padx=16, pady=(0, 8))
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

        # Mode penyisipan + stego-key
        mode_key_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_key_frame.grid(row=15, column=0, sticky="ew", padx=16, pady=(0, 8))
        mode_key_frame.grid_columnconfigure(0, weight=1)
        mode_key_frame.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(mode_key_frame, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        self._lbl("Mode penyisipan", row=0, parent=left)
        self._mode_var = ctk.StringVar(value="Sekuensial")
        ctk.CTkOptionMenu(
            left,
            variable=self._mode_var,
            values=["Sekuensial", "Acak"],
            command=self._on_mode_change,
        ).grid(row=1, column=0, sticky="ew")

        right = ctk.CTkFrame(mode_key_frame, fg_color="transparent")
        right.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)
        self._lbl("Stego-key", row=0, parent=right)
        self._stegokey_entry = ctk.CTkEntry(
            right, placeholder_text="Masukkan stego-key...",
            show="•", state="disabled",
        )
        self._stegokey_entry.grid(row=1, column=0, sticky="ew")

        # Enkripsi A5/1
        enc_frame = ctk.CTkFrame(self, fg_color="transparent")
        enc_frame.grid(row=16, column=0, sticky="ew", padx=16, pady=(0, 8))
        enc_frame.grid_columnconfigure(0, weight=1)

        self._enc_switch = ctk.CTkSwitch(
            enc_frame,
            text="Enkripsi A5/1",
            command=self._on_enc_toggle,
        )
        self._enc_switch.grid(row=0, column=0, sticky="w")

        self._key_entry = ctk.CTkEntry(
            enc_frame,
            placeholder_text="Kunci A5/1 (64-bit hex)...",
            show="•", state="disabled",
        )
        self._key_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        # Nama file output
        self._lbl("Nama file stego-video output", row=17)
        self._output_entry = ctk.CTkEntry(self, placeholder_text="stego_output.avi")
        self._output_entry.insert(0, "stego_output.avi")
        self._output_entry.grid(row=18, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._sep(row=19)

    def _build_progress_section(self):
        prog_header = ctk.CTkFrame(self, fg_color="transparent")
        prog_header.grid(row=20, column=0, sticky="ew", padx=16, pady=(8, 2))
        prog_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            prog_header, text="Progress penyisipan",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self._prog_pct_lbl = ctk.CTkLabel(
            prog_header, text="0%",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self._prog_pct_lbl.grid(row=0, column=1, sticky="e")

        self._progress = ctk.CTkProgressBar(self, height=8)
        self._progress.set(0)
        self._progress.grid(row=21, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._log_box = ctk.CTkTextbox(
            self, height=100,
            font=ctk.CTkFont(family="Courier", size=11),
            state="disabled",
            fg_color=("gray90", "gray10"),
        )
        self._log_box.grid(row=22, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._status_lbl = ctk.CTkLabel(
            self, text="● Siap",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._status_lbl.grid(row=23, column=0, sticky="w", padx=16, pady=(0, 4))


    def _build_action_buttons(self):
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=24, column=0, sticky="ew", padx=16, pady=(0, 8))
        btn_frame.grid_columnconfigure(0, weight=1)

        self._embed_btn = ctk.CTkButton(
            btn_frame, text="Sisipkan Pesan",
            height=38, font=ctk.CTkFont(size=14, weight="bold"),
            command=self._run_embed,
        )
        self._embed_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Reset",
            width=90, height=38,
            fg_color="transparent",
            border_width=1,
            command=self._reset,
        ).grid(row=0, column=1)

        self._sep(row=25)


    def _build_analysis_section(self):
        self._analysis_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._analysis_frame.grid(row=26, column=0, sticky="ew", padx=0)
        self._analysis_frame.grid_columnconfigure(0, weight=1)
        self._analysis_frame.grid_remove()  # hidden by default

        self._section("ANALISIS KUALITAS", row=0, parent=self._analysis_frame)

        # Metric cards MSE, PSNR, Frame
        cards_frame = ctk.CTkFrame(self._analysis_frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._mse_lbl   = self._metric_card(cards_frame, "MSE (rata-rata)", col=0)
        self._psnr_lbl  = self._metric_card(cards_frame, "PSNR (dB)", col=1)
        self._frame_lbl = self._metric_card(cards_frame, "Frame diproses", col=2)

        # Histogram
        hist_header = ctk.CTkFrame(self._analysis_frame, fg_color="transparent")
        hist_header.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 4))
        hist_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hist_header, text="Histogram RGB — perbandingan frame ke-",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        slider_frame = ctk.CTkFrame(hist_header, fg_color="transparent")
        slider_frame.grid(row=0, column=1, sticky="e")
        self._frame_slider = ctk.CTkSlider(
            slider_frame, from_=0, to=1, number_of_steps=1,
            command=self._on_frame_slider,
            width=120,
        )
        self._frame_slider.set(0)
        self._frame_slider.pack(side="left")
        self._frame_num_lbl = ctk.CTkLabel(
            slider_frame, text="0",
            font=ctk.CTkFont(size=11), width=28,
        )
        self._frame_num_lbl.pack(side="left", padx=(4, 0))

        # Placeholder untuk canvas matplotlib
        self._hist_frame = ctk.CTkFrame(
            self._analysis_frame,
            fg_color=("gray90", "gray15"),
        )
        self._hist_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
        self._hist_frame.grid_columnconfigure(0, weight=1)

    def _pick_cover(self):
        path = filedialog.askopenfilename(
            title="Pilih video cover",
            filetypes=[("Video AVI", "*.avi"), ("Semua file", "*.*")],
        )
        if not path:
            return
        self._cover_path = path
        self._set_entry(self._cover_entry, os.path.basename(path))
        self._update_capacity()

    def _pick_msg_file(self):
        path = filedialog.askopenfilename(
            title="Pilih file pesan",
            filetypes=[("Semua file", "*.*")],
        )
        if not path:
            return
        self._msg_file_path = path
        self._set_entry(self._file_entry, os.path.basename(path))
        self._update_capacity()

    def _on_msg_type_change(self, value):
        if value == "Teks":
            self._file_frame.grid_remove()
            self._text_frame.grid()
        else:
            self._text_frame.grid_remove()
            self._file_frame.grid()
        self._update_capacity()

    def _on_lsb_change(self, value):
        if value == "Kustom...":
            self._lsb_custom_frame.grid()
        else:
            self._lsb_custom_frame.grid_remove()
        self._update_capacity()

    def _on_enc_toggle(self):
        if self._enc_switch.get():
            self._key_entry.configure(state="normal")
        else:
            self._key_entry.configure(state="disabled")
            self._key_entry.delete(0, "end")

    def _on_mode_change(self, value):
        if value == "Acak":
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
            self._embed_btn.configure(state="normal")
            self._update_capacity()
            return True
        else:
            self._lsb_total_lbl.configure(
                text=f"Total: {total} bit — harus tepat 8",
                text_color="#e74c3c",
            )
            self._embed_btn.configure(state="disabled")
            return False

    def _update_capacity(self):
        """Update progress bar kapasitas secara real-time"""
        if not self._cover_path:
            return

        payload_size = self._get_payload_size()
        if payload_size is None:
            return

        lsb_r, lsb_g, lsb_b = self._get_lsb_scheme()
        frame_step = 1  # default

        try:
            result = check_capacity(
                self._cover_path, payload_size,
                frame_step=frame_step,
                lsb_r=lsb_r, lsb_g=lsb_g, lsb_b=lsb_b,
            )
        except Exception:
            return

        cap   = result["capacity_bytes"]
        usage = result["usage_pct"] / 100.0

        self._cap_progress.set(min(1.0, usage))
        self._cap_msg_lbl.configure(text=f"Pesan: {self._fmt_bytes(payload_size)}")
        self._cap_max_lbl.configure(text=f"Kapasitas: {self._fmt_bytes(cap)}")

        if not result["fits"]:
            self._cap_err_lbl.configure(
                text="Pesan melebihi kapasitas sisip. "
                     "Kurangi ukuran pesan atau gunakan video yang lebih besar."
            )
            self._embed_btn.configure(state="disabled")
        else:
            self._cap_err_lbl.configure(text="")
            if self._lsb_var.get() != "Kustom..." or self._validate_custom_lsb():
                self._embed_btn.configure(state="normal")


    def _run_embed(self):
        """Validasi input lalu jalankan embed di thread terpisah"""
        if not self._cover_path:
            self._app.show_error("Input tidak lengkap", "Pilih video cover terlebih dahulu.")
            return

        payload, filename = self._collect_payload()
        if payload is None:
            return

        output_name = self._output_entry.get().strip() or "stego_output.avi"
        if not output_name.endswith(".avi"):
            output_name += ".avi"
        output_path = os.path.join(os.path.dirname(self._cover_path), output_name)

        lsb_r, lsb_g, lsb_b = self._get_lsb_scheme()
        mode       = MODE_RANDOM if self._mode_var.get() == "Acak" else MODE_SEQUENTIAL
        stegokey   = self._stegokey_entry.get() if mode == MODE_RANDOM else ""
        msg_type   = MSG_TYPE_FILE if self._msg_type_var.get() == "File" else MSG_TYPE_TEXT

        if mode == MODE_RANDOM and not stegokey:
            self._app.show_error("Stego-key kosong", "Mode acak dipilih tapi stego-key belum diisi.")
            return

        use_enc  = bool(self._enc_switch.get())
        key_a51  = self._key_entry.get().strip() if use_enc else ""

        if use_enc and not key_a51:
            self._app.show_error("Kunci kosong", "Enkripsi A5/1 dipilih tapi kunci belum diisi.")
            self._embed_btn.configure(state="normal", text="Sisipkan Pesan")
            return

        self._embed_btn.configure(state="disabled", text="Memproses...")
        self._analysis_frame.grid_remove()
        self._reset_progress()
        self._log("[init] Memulai proses penyisipan...")
        self._set_status("run", "Memproses...")

        self._output_path_result = output_path
        self._cover_path_result  = self._cover_path

        def _worker():
            try:
                actual_payload = payload
                if use_enc:
                    self.after(0, lambda: self._log("[a5/1] Mengenkripsi payload..."))
                    actual_payload = enkripsi_a51(payload, key_a51)

                meta = embed(
                    cover_path  = self._cover_path,
                    output_path = output_path,
                    payload     = actual_payload,
                    msg_type    = msg_type,
                    encrypted   = ENC_A5_1 if use_enc else ENC_NONE,
                    mode        = mode,
                    frame_step  = 1,
                    lsb_r       = lsb_r,
                    lsb_g       = lsb_g,
                    lsb_b       = lsb_b,
                    filename    = filename,
                    stegokey    = stegokey,
                    progress_cb = self._on_progress,
                )
                self.after(0, lambda: self._on_embed_done(meta, output_path))
            except Exception as e:
                self.after(0, lambda err=e: self._on_embed_error(err))

        self._embed_thread = threading.Thread(target=_worker, daemon=True)
        self._embed_thread.start()

    def _on_progress(self, current: int, total: int):
        """Dipanggil dari worker thread — update GUI via self.after()."""
        pct = current / total if total else 0
        self.after(0, lambda p=pct, c=current, t=total: self._update_progress(p, c, t))

    def _update_progress(self, pct: float, current: int, total: int):
        self._progress.set(pct)
        self._prog_pct_lbl.configure(text=f"{int(pct * 100)}%")
        self._log(f"[frame] {current}/{total}")

    def _on_embed_done(self, meta, output_path: str):
        self._progress.set(1.0)
        self._prog_pct_lbl.configure(text="100%")
        self._log(f"[done] Berhasil → {os.path.basename(output_path)}")
        self._set_status("ok", "Selesai")
        self._embed_btn.configure(state="normal", text="Sisipkan Pesan")
        self._show_analysis(meta, output_path)

    def _on_embed_error(self, err: Exception):
        self._log(f"[error] {err}", level="error")
        self._set_status("err", f"Gagal: {err}")
        self._embed_btn.configure(state="normal", text="Sisipkan Pesan")
        self._app.show_error("Penyisipan gagal", str(err))


    def _show_analysis(self, meta, output_path: str):
        """Muat analisis kualitas setelah embed selesai"""
        self._analysis_frame.grid()
        self._log("[analysis] Menghitung MSE dan PSNR...")

        def _load():
            try:
                orig_frames, stego_frames = self._load_frames_pair(
                    self._cover_path_result, output_path
                )
                mse_list  = [hitung_mse(o, s) for o, s in zip(orig_frames, stego_frames)]
                psnr_list = [hitung_psnr(m) for m in mse_list]
                avg_mse   = sum(mse_list) / len(mse_list) if mse_list else 0
                avg_psnr  = sum(psnr_list) / len(psnr_list) if psnr_list else 0

                self.after(0, lambda: self._update_analysis(
                    orig_frames, stego_frames,
                    avg_mse, avg_psnr, len(orig_frames),
                ))
            except Exception as e:
                self.after(0, lambda err=e: self._log(
                    f"[analysis error] {err}", level="error"
                ))

        threading.Thread(target=_load, daemon=True).start()

    def _update_analysis(self, orig_frames, stego_frames, avg_mse, avg_psnr, n_frames):
        self._orig_frames  = orig_frames
        self._stego_frames = stego_frames

        self._mse_lbl.configure(text=f"{avg_mse:.4f}")
        self._psnr_lbl.configure(text=f"{avg_psnr:.2f}")
        self._frame_lbl.configure(text=str(n_frames))

        # Setup slider
        max_idx = max(0, n_frames - 1)
        self._frame_slider.configure(to=max_idx, number_of_steps=max_idx)
        self._frame_slider.set(0)
        self._frame_num_lbl.configure(text="0")

        self._draw_histogram(0)
        self._log(f"[analysis] MSE={avg_mse:.4f}  PSNR={avg_psnr:.2f} dB")

    def _on_frame_slider(self, value):
        idx = int(round(value))
        self._frame_num_lbl.configure(text=str(idx))
        if hasattr(self, "_orig_frames") and self._orig_frames:
            self._draw_histogram(idx)

    def _draw_histogram(self, frame_idx: int):
        """Render histogram matplotlib ke dalam widget CTk."""
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


    def _collect_payload(self) -> tuple:
        """Mengumpulkan payload dari input"""
        if self._msg_type_var.get() == "Teks":
            text = self._msg_textbox.get("1.0", "end").strip()
            if not text:
                self._app.show_error("Pesan kosong", "Isi pesan teks terlebih dahulu.")
                return None, ""
            return text_to_bytes(text), ""
        else:
            if not self._msg_file_path:
                self._app.show_error("File tidak dipilih", "Pilih file pesan terlebih dahulu.")
                return None, ""
            try:
                with open(self._msg_file_path, "rb") as f:
                    return f.read(), self._msg_file_path
            except Exception as e:
                self._app.show_error("Gagal membaca file", str(e))
                return None, ""

    def _get_payload_size(self) -> int:
        """Menghitung ukuran payload saat ini"""
        if self._msg_type_var.get() == "Teks":
            text = self._msg_textbox.get("1.0", "end").strip()
            return len(text.encode("utf-8"))
        else:
            if self._msg_file_path and os.path.isfile(self._msg_file_path):
                return os.path.getsize(self._msg_file_path)
            return 0

    def _get_lsb_scheme(self) -> tuple:
        """Mengembalikan (lsb_r, lsb_g, lsb_b) sesuai pilihan"""
        key = self._lsb_var.get()
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
        """Membaca semua frame dari dua video untuk analisis."""
        def _read(path):
            cap = cv2.VideoCapture(path)
            frames = []
            while True:
                ret, f = cap.read()
                if not ret:
                    break
                frames.append(f)
            cap.release()
            return frames

        return _read(orig_path), _read(stego_path)


    def _reset(self):
        self._cover_path    = ""
        self._msg_file_path = ""
        self._set_entry(self._cover_entry, "")
        self._set_entry(self._file_entry, "")
        self._msg_textbox.delete("1.0", "end")
        self._output_entry.delete(0, "end")
        self._output_entry.insert(0, "stego_output.avi")
        self._reset_progress()
        self._cap_progress.set(0)
        self._cap_msg_lbl.configure(text="Pesan: —")
        self._cap_max_lbl.configure(text="Kapasitas: —")
        self._cap_err_lbl.configure(text="")
        self._analysis_frame.grid_remove()
        self._embed_btn.configure(state="normal", text="Sisipkan Pesan")
        self._set_status("idle", "Siap")

    def _reset_progress(self):
        self._progress.set(0)
        self._prog_pct_lbl.configure(text="0%")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _log(self, msg: str, level: str = ""):
        colors = {"error": "#e74c3c", "warn": "#fbbf24", "": "#4ade80"}
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

    def _sep(self, row: int):
        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30")).grid(
            row=row, column=0, sticky="ew", padx=16, pady=(8, 4),
        )

    @staticmethod
    def _fmt_bytes(b: int) -> str:
        if b < 1024:
            return f"{b} B"
        if b < 1048576:
            return f"{b/1024:.1f} KB"
        return f"{b/1048576:.2f} MB"