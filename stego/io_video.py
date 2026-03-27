import cv2
import os
from typing import Generator, Tuple
import numpy as np


class VideoReader:
    """
    Membuka video AVI dan akses frame secara streaming
    """

    def __init__(self, path: str):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File tidak ditemukan: {path}")
        if not path.lower().endswith(".avi"):
            raise ValueError(f"File harus berformat AVI: {path}")

        self._path = path
        self._cap: cv2.VideoCapture = None

    def __enter__(self):
        self._cap = cv2.VideoCapture(self._path)
        if not self._cap.isOpened():
            raise IOError(f"Gagal membuka video: {self._path}")
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._cap and self._cap.isOpened():
            self._cap.release()

    # ------------------------------------------------------------------
    # Properti video
    # ------------------------------------------------------------------

    @property
    def frame_count(self) -> int:
        """Total frame dalam video."""
        return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    @property
    def fps(self) -> float:
        """Frame per detik."""
        return self._cap.get(cv2.CAP_PROP_FPS)

    @property
    def width(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    @property
    def height(self) -> int:
        return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    @property
    def resolution(self) -> Tuple[int, int]:
        """Mengembalikan (width, height)."""
        return self.width, self.height

    def get_info(self) -> dict:
        """Mengembalikan ringkasan properti video."""
        return {
            "path": self._path,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "pixels_per_frame": self.width * self.height,
        }

    def stream(
        self, frame_step: int = 1
    ) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        Generator frame

        Parameter
        ---------
        frame_step : int
            Jarak antar frame yang diambil.
            1  → semua frame dipakai (default).
            2  → frame 0, 2, 4, ...
            N  → frame 0, N, 2N, ...

        Yield
        -----
        (frame_index, frame_bgr)
            frame_index : indeks asli frame dalam video.
            frame_bgr   : np.ndarray shape (H, W, 3) dtype uint8.
        """
        if frame_step < 1:
            raise ValueError("frame_step harus >= 1")

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        current = 0

        while True:
            ret, frame = self._cap.read()
            if not ret:
                break
            if current % frame_step == 0:
                yield current, frame
            current += 1

    def count_usable_frames(self, frame_step: int = 1) -> int:
        "Menghitung jumlah frame yang akan dipakai untuk penyisipan"
        return len(range(0, self.frame_count, frame_step))

    def calculate_capacity(
        self, frame_step: int = 1, bits_per_pixel: int = 8
    ) -> int:
        """
        Menghitung kapasitas sisip
        """
        usable_frames = self.count_usable_frames(frame_step)
        pixels_per_frame = self.width * self.height
        total_bits = usable_frames * pixels_per_frame * bits_per_pixel
        return total_bits // 8


class VideoWriter:
    """
    Menulis frame satu per satu ke file AVI output (lossless).
    """

    # Codec yang direkomendasikan untuk AVI lossless
    CODEC = "FFV1"

    def __init__(self, path: str, fps: float, size: Tuple[int, int]):
        if not path.lower().endswith(".avi"):
            raise ValueError("Output harus berformat AVI.")

        self._path = path
        self._fps = fps
        self._size = size
        self._writer: cv2.VideoWriter = None
        self._frame_count = 0

    def __enter__(self):
        fourcc = cv2.VideoWriter_fourcc(*self.CODEC)
        self._writer = cv2.VideoWriter(
            self._path, fourcc, self._fps, self._size
        )
        if not self._writer.isOpened():
            raise IOError(f"Gagal membuat file video: {self._path}")
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._writer and self._writer.isOpened():
            self._writer.release()

    def write(self, frame: np.ndarray):
        """
        Menulis satu frame ke video output
        """
        if frame.dtype != np.uint8:
            raise TypeError("Frame harus bertipe uint8.")
        if frame.shape[:2] != (self._size[1], self._size[0]):
            raise ValueError(
                f"Ukuran frame {frame.shape[:2]} tidak sesuai "
                f"dengan ukuran video {self._size}."
            )
        self._writer.write(frame)
        self._frame_count += 1

    @property
    def frames_written(self) -> int:
        return self._frame_count


def copy_video_passthrough(
    src_path: str,
    dst_path: str,
    frame_callback=None,
    frame_step: int = 1,
) -> int:
    """
    Menyalin video dari src ke dst frame per frame.
    Frame yang dipilih (sesuai frame_step) dikirim ke frame_callback
    untuk dimodifikasi sebelum ditulis; frame lainnya disalin apa adanya.
    """
    processed = 0

    with VideoReader(src_path) as reader:
        info = reader.get_info()
        size = (info["width"], info["height"])

        with VideoWriter(dst_path, fps=info["fps"], size=size) as writer:
            reader._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            current = 0

            while True:
                ret, frame = reader._cap.read()
                if not ret:
                    break

                if frame_callback and current % frame_step == 0:
                    frame = frame_callback(current, frame)
                    processed += 1

                writer.write(frame)
                current += 1

    return processed


def get_video_info(path: str) -> dict:
    """Membaca properti video tanpa context manager"""
    with VideoReader(path) as reader:
        return reader.get_info()


def calculate_capacity(
    path: str, frame_step: int = 1, bits_per_pixel: int = 8
) -> int:
    """Menghitung kapasitas sisip dari path video secara langsung"""
    with VideoReader(path) as reader:
        return reader.calculate_capacity(frame_step, bits_per_pixel)