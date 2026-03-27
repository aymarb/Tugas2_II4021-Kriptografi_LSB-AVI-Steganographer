import numpy as np
from typing import Callable, Optional

from stego.metadata import (
    StegoMetadata,
    InvalidHeaderError,
    HEADER_SIZE,
    MSG_TYPE_TEXT,
    MSG_TYPE_FILE,
    ENC_NONE,
    ENC_A5_1,
    MODE_SEQUENTIAL,
    MODE_RANDOM,
    pack_header,
    unpack_header,
    build_metadata,
    verify_payload,
    bytes_to_bits,
    bits_to_bytes,
    text_to_bytes,
    bytes_to_text,
)
from stego.io_video import VideoReader, VideoWriter, copy_video_passthrough
from stego.stegokey import generate_pixel_permutation
#stegokeynya n seednya blom

# progress_callback(current_frame: int, total_frames: int)
ProgressCallback = Optional[Callable[[int, int], None]]


"Konversi bit ↔ numpy array"
def _bytes_to_bitarray(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    return np.unpackbits(arr)


def _bitarray_to_bytes(bits: np.ndarray) -> bytes:
    pad = (8 - len(bits) % 8) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    return np.packbits(bits).tobytes()


def _embed_bits_in_frame(
    frame: np.ndarray,
    bits: np.ndarray,
    lsb_r: int,
    lsb_g: int,
    lsb_b: int,
    pixel_indices: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, int]:
    """
    Menyisipkan bits ke dalam satu frame
    """
    h, w, _ = frame.shape
    total_pixels = h * w
    bits_per_pixel = lsb_r + lsb_g + lsb_b
    capacity_bits = total_pixels * bits_per_pixel

    bits_to_embed = bits[:capacity_bits]
    actual_count = len(bits_to_embed)

    if actual_count == 0:
        return frame.copy(), 0

    frame_out = frame.copy()
    flat = frame_out.reshape(-1, 3)  # shape (H*W, 3), kolom = B, G, R

    # Tentukan urutan piksel
    if pixel_indices is None:
        indices = np.arange(total_pixels)
    else:
        indices = pixel_indices[:total_pixels]

    # Sisipkan bit per channel
    # OpenCV menyimpan frame dalam urutan BGR, jadi:
    #   flat[:, 0] = B, flat[:, 1] = G, flat[:, 2] = R
    bit_cursor = 0
    channels = [
        (2, lsb_r),   # channel R
        (1, lsb_g),   # channel G
        (0, lsb_b),   # channel B
    ]

    for ch_idx, n_bits in channels:
        if n_bits == 0 or bit_cursor >= actual_count:
            continue

        # Ambil piksel sesuai urutan
        n_pixels = min(
            len(indices),
            (actual_count - bit_cursor + n_bits - 1) // n_bits
        )
        pix = indices[:n_pixels]

        mask = np.uint8(0xFF << n_bits & 0xFF)

        for bit_offset in range(n_bits):
            if bit_cursor >= actual_count:
                break

            # Ambil satu bit dari setiap piksel yang akan diproses
            n_pix_this = min(n_pixels, actual_count - bit_cursor)
            chunk = bits_to_embed[bit_cursor : bit_cursor + n_pix_this]

            # Shift bit ke posisi yang tepat dalam byte
            shift = n_bits - 1 - bit_offset
            flat[pix[:n_pix_this], ch_idx] = (
                (flat[pix[:n_pix_this], ch_idx] & mask)
                | (chunk.astype(np.uint8) << shift)
            )
            bit_cursor += n_pix_this

    return frame_out, bit_cursor


def _extract_bits_from_frame(
    frame: np.ndarray,
    n_bits_to_read: int,
    lsb_r: int,
    lsb_g: int,
    lsb_b: int,
    pixel_indices: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Mengekstrak bits dari satu frame
    """
    h, w, _ = frame.shape
    total_pixels = h * w
    bits_per_pixel = lsb_r + lsb_g + lsb_b
    capacity_bits = total_pixels * bits_per_pixel
    actual_read = min(n_bits_to_read, capacity_bits)

    flat = frame.reshape(-1, 3)

    if pixel_indices is None:
        indices = np.arange(total_pixels)
    else:
        indices = pixel_indices[:total_pixels]

    extracted = np.zeros(actual_read, dtype=np.uint8)
    bit_cursor = 0

    channels = [
        (2, lsb_r),
        (1, lsb_g),
        (0, lsb_b),
    ]

    for ch_idx, n_bits in channels:
        if n_bits == 0 or bit_cursor >= actual_read:
            continue

        n_pixels = min(
            len(indices),
            (actual_read - bit_cursor + n_bits - 1) // n_bits
        )
        pix = indices[:n_pixels]

        for bit_offset in range(n_bits):
            if bit_cursor >= actual_read:
                break

            shift = n_bits - 1 - bit_offset
            n_pix_this = min(n_pixels, actual_read - bit_cursor)
            extracted[bit_cursor : bit_cursor + n_pix_this] = (
                (flat[pix[:n_pix_this], ch_idx] >> shift) & 1
            ).astype(np.uint8)
            bit_cursor += n_pix_this

    return extracted[:bit_cursor]


def embed(
    cover_path: str,
    output_path: str,
    payload: bytes,
    msg_type: int,
    encrypted: int,
    mode: int,
    frame_step: int,
    lsb_r: int,
    lsb_g: int,
    lsb_b: int,
    filename: str = "",
    stegokey: str = "",
    progress_cb: ProgressCallback = None,
) -> StegoMetadata:
    """
    Menyisipkan payload ke dalam video cover dan menulis stego-video
    """
    meta = build_metadata(
        payload    = payload,
        msg_type   = msg_type,
        encrypted  = encrypted,
        mode       = mode,
        frame_step = frame_step,
        lsb_r      = lsb_r,
        lsb_g      = lsb_g,
        lsb_b      = lsb_b,
        filename   = filename,
    )
    header_bytes = pack_header(meta)

    header_bits  = _bytes_to_bitarray(header_bytes)
    payload_bits = _bytes_to_bitarray(payload)

    with VideoReader(cover_path) as reader:
        info       = reader.get_info()
        size       = (info["width"], info["height"])
        fps        = info["fps"]
        total_frames = info["frame_count"]

        # Kapasitas frame 0 untuk header
        header_capacity = info["width"] * info["height"] * (lsb_r + lsb_g + lsb_b)
        if len(header_bits) > header_capacity:
            raise ValueError(
                f"Resolusi video terlalu kecil untuk header "
                f"({len(header_bits)} bit > {header_capacity} bit kapasitas frame 0)."
            )

        # Kapasitas payload (frame 1 dst, ikuti frame_step)
        usable_frames    = len(range(1, total_frames, frame_step))
        payload_capacity = usable_frames * info["width"] * info["height"] * (lsb_r + lsb_g + lsb_b)
        if len(payload_bits) > payload_capacity:
            raise ValueError(
                f"Payload terlalu besar: {len(payload_bits)} bit "
                f"> kapasitas {payload_capacity} bit "
                f"({usable_frames} frame × {info['width']}×{info['height']} piksel)."
            )

    # Metode penyisipan acak
    pixels_per_frame = info["width"] * info["height"]
    pixel_indices = None
    if mode == MODE_RANDOM and stegokey:
        pixel_indices = generate_pixel_permutation(stegokey, pixels_per_frame)

    # Proses frame per frame
    payload_cursor = 0
    processed_frames = 0
    total_usable = 1 + usable_frames  # frame 0 (header) + frame payload

    with VideoReader(cover_path) as reader:
        with VideoWriter(output_path, fps=fps, size=size) as writer:
            reader._cap.set(0, 0)
            frame_idx = 0

            while True:
                ret, frame = reader._cap.read()
                if not ret:
                    break

                if frame_idx == 0:
                    # Frame 0: sisipkan header
                    frame, _ = _embed_bits_in_frame(
                        frame, header_bits, lsb_r, lsb_g, lsb_b
                    )
                    processed_frames += 1

                elif (frame_idx - 1) % frame_step == 0 and payload_cursor < len(payload_bits):
                    # Frame payload
                    remaining = payload_bits[payload_cursor:]
                    frame, consumed = _embed_bits_in_frame(
                        frame, remaining, lsb_r, lsb_g, lsb_b,
                        pixel_indices
                    )
                    payload_cursor += consumed
                    processed_frames += 1

                writer.write(frame)
                frame_idx += 1

                if progress_cb:
                    progress_cb(processed_frames, total_usable)

    return meta

def extract(
    stego_path: str,
    lsb_r: int,
    lsb_g: int,
    lsb_b: int,
    stegokey: str = "",
    progress_cb: ProgressCallback = None,
) -> tuple[StegoMetadata, bytes]:
    """
    Mengekstrak pesan dari stego-video
    """

    return

def check_capacity(
    cover_path: str,
    payload_size_bytes: int,
    frame_step: int = 1,
    lsb_r: int = 3,
    lsb_g: int = 3,
    lsb_b: int = 2,
) -> dict:
    """
    Mengecek apakah payload muat di video cover
    """
    from stego.io_video import calculate_capacity
    bits_per_pixel = lsb_r + lsb_g + lsb_b
    # Frame 0 untuk header, frame 1+ untuk payload
    with VideoReader(cover_path) as reader:
        total = reader.frame_count
        w, h  = reader.width, reader.height
        usable = len(range(1, total, frame_step))
        cap_bits = usable * w * h * bits_per_pixel
        cap_bytes = cap_bits // 8

    return {
        "capacity_bytes": cap_bytes,
        "payload_bytes":  payload_size_bytes,
        "fits":           payload_size_bytes <= cap_bytes,
        "usage_pct":      round(payload_size_bytes / cap_bytes * 100, 1) if cap_bytes else 0.0,
    }