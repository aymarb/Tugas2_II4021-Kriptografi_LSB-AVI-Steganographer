import struct
import zlib
import os
from dataclasses import dataclass, field
from typing import Optional


MAGIC = b"STGV"
HEADER_SIZE = 24

MSG_TYPE_TEXT = 0x00
MSG_TYPE_FILE = 0x01

ENC_NONE = 0x00
ENC_A5_1 = 0x01

MODE_SEQUENTIAL = 0x00
MODE_RANDOM     = 0x01


# ------------------------------------------------------------------
# Dataclass metadata
# ------------------------------------------------------------------

@dataclass
class StegoMetadata:
    """Representasi semua informasi yang disimpan dalam header"""

    msg_type:    int            # MSG_TYPE_TEXT atau MSG_TYPE_FILE
    encrypted:   int            # ENC_NONE atau ENC_A5_1
    mode:        int            # MODE_SEQUENTIAL atau MODE_RANDOM
    frame_step:  int            # 1–255
    lsb_r:       int            # bit untuk channel R
    lsb_g:       int            # bit untuk channel G
    lsb_b:       int            # bit untuk channel B
    payload_size: int           # ukuran payload dalam byte
    crc32:       int            # CRC32 dari payload
    extension:   bytes = b""    # ekstensi file, misal b".png"
    filename:    bytes = b""    # nama file asli dalam UTF-8

    @property
    def lsb_scheme(self):
        """Mengembalikan tuple (R, G, B) bits"""
        return (self.lsb_r, self.lsb_g, self.lsb_b)

    @property
    def bits_per_pixel(self):
        """Total bit yang disisipkan per piksel"""
        return self.lsb_r + self.lsb_g + self.lsb_b

    @property
    def is_file(self):
        return self.msg_type == MSG_TYPE_FILE

    @property
    def is_encrypted(self):
        return self.encrypted == ENC_A5_1

    @property
    def is_random(self):
        return self.mode == MODE_RANDOM

    @property
    def filename_str(self) -> str:
        """Nama file asli sebagai string."""
        return self.filename.decode("utf-8", errors="replace")

    @property
    def extension_str(self) -> str:
        """Ekstensi file sebagai string, misal '.png'."""
        return self.extension.decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# Packing header
# ------------------------------------------------------------------

def pack_header(meta: StegoMetadata) -> bytes:
    """
    Mengubah StegoMetadata menjadi bytes header
    """
    _validate_metadata(meta)

    ext_bytes  = meta.extension
    name_bytes = meta.filename
    ext_len    = len(ext_bytes)
    name_len   = len(name_bytes)

    header = struct.pack(
        ">4sBBBBBBBBIII",
        MAGIC,
        meta.msg_type,
        meta.encrypted,
        meta.mode,
        meta.frame_step,
        meta.lsb_r,
        meta.lsb_g,
        meta.lsb_b,
        ext_len,
        meta.payload_size,
        meta.crc32,
        name_len,
    )

    return header + ext_bytes + name_bytes


def header_total_size(meta: StegoMetadata) -> int:
    """
    Menghitung ukuran total header (fixed + variabel) dalam byte
    """
    return HEADER_SIZE + len(meta.extension) + len(meta.filename)


# ------------------------------------------------------------------
# Unpacking header
# ------------------------------------------------------------------

class InvalidHeaderError(Exception):
    """Dilempar saat magic bytes tidak cocok atau header korup."""
    pass


def unpack_header(data: bytes) -> tuple[StegoMetadata, int]:
    """
    Membaca header dari bytes hasil ekstraksi LSB
    """
    if len(data) < HEADER_SIZE:
        raise InvalidHeaderError(
            f"Data terlalu pendek: {len(data)} byte, minimal {HEADER_SIZE} byte."
        )

    magic = data[0:4]
    if magic != MAGIC:
        raise InvalidHeaderError(
            f"Magic bytes tidak cocok: {magic!r} != {MAGIC!r}. "
            "Kemungkinan skema LSB, stego-key, atau kunci A5/1 tidak sesuai."
        )

    (
        _magic,
        msg_type,
        encrypted,
        mode,
        frame_step,
        lsb_r,
        lsb_g,
        lsb_b,
        ext_len,
        payload_size,
        crc32,
        name_len,
    ) = struct.unpack(">4sBBBBBBBBIII", data[:HEADER_SIZE])

    offset = HEADER_SIZE
    ext_bytes  = data[offset : offset + ext_len];  offset += ext_len
    name_bytes = data[offset : offset + name_len]; offset += name_len

    meta = StegoMetadata(
        msg_type     = msg_type,
        encrypted    = encrypted,
        mode         = mode,
        frame_step   = frame_step,
        lsb_r        = lsb_r,
        lsb_g        = lsb_g,
        lsb_b        = lsb_b,
        payload_size = payload_size,
        crc32        = crc32,
        extension    = ext_bytes,
        filename     = name_bytes,
    )

    return meta, offset


def build_metadata(
    payload: bytes,
    msg_type: int,
    encrypted: int,
    mode: int,
    frame_step: int,
    lsb_r: int,
    lsb_g: int,
    lsb_b: int,
    filename: str = "",
) -> StegoMetadata:
    """
    Membangun StegoMetadata dari input pengguna secara otomatis
    """
    extension = b""
    name_bytes = b""

    if msg_type == MSG_TYPE_FILE and filename:
        ext = os.path.splitext(filename)[1]   # misal ".png"
        extension  = ext.encode("utf-8")
        name_bytes = os.path.basename(filename).encode("utf-8")

    return StegoMetadata(
        msg_type     = msg_type,
        encrypted    = encrypted,
        mode         = mode,
        frame_step   = frame_step,
        lsb_r        = lsb_r,
        lsb_g        = lsb_g,
        lsb_b        = lsb_b,
        payload_size = len(payload),
        crc32        = zlib.crc32(payload) & 0xFFFFFFFF,
        extension    = extension,
        filename     = name_bytes,
    )


# ------------------------------------------------------------------
# Validasi integritas payload hasil ekstraksi
# ------------------------------------------------------------------

def verify_payload(payload: bytes, expected_crc32: int) -> bool:
    """
    Memverifikasi integritas payload dengan membandingkan CRC32
    """
    actual = zlib.crc32(payload) & 0xFFFFFFFF
    return actual == expected_crc32


# ------------------------------------------------------------------
# Konversi payload ke binary string
# ------------------------------------------------------------------

def bytes_to_bits(data: bytes) -> str:
    """
    Mengubah bytes ke binary string

    Contoh: b'\\x41' -> '01000001'
    """
    return "".join(format(byte, "08b") for byte in data)


def bits_to_bytes(bits: str) -> bytes:
    """
    Mengubah binary string ke bytes

    Contoh: '01000001' -> b'\\x41'
    """
    result = bytearray()
    for i in range(0, len(bits) - 7, 8):
        result.append(int(bits[i:i + 8], 2))
    return bytes(result)


def text_to_bytes(text: str) -> bytes:
    """Mengubah string teks ke bytes UTF-8."""
    return text.encode("utf-8")


def bytes_to_text(data: bytes) -> str:
    """Mengubah bytes ke string teks UTF-8."""
    return data.decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# Validasi internal
# ------------------------------------------------------------------

def _validate_metadata(meta: StegoMetadata):
    if meta.lsb_r + meta.lsb_g + meta.lsb_b != 8:
        raise ValueError(
            f"Total LSB bits harus 8, didapat: "
            f"{meta.lsb_r}+{meta.lsb_g}+{meta.lsb_b}="
            f"{meta.lsb_r + meta.lsb_g + meta.lsb_b}"
        )
    if not (1 <= meta.frame_step <= 255):
        raise ValueError(f"frame_step harus 1–255, didapat: {meta.frame_step}")
    if meta.msg_type not in (MSG_TYPE_TEXT, MSG_TYPE_FILE):
        raise ValueError(f"msg_type tidak valid: {meta.msg_type}")
    if meta.encrypted not in (ENC_NONE, ENC_A5_1):
        raise ValueError(f"encrypted tidak valid: {meta.encrypted}")
    if meta.mode not in (MODE_SEQUENTIAL, MODE_RANDOM):
        raise ValueError(f"mode tidak valid: {meta.mode}")
    if len(meta.extension) > 255:
        raise ValueError("Ekstensi file terlalu panjang (maks 255 byte).")