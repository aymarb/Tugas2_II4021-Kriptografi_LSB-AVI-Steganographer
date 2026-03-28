import hashlib
import numpy as np


def stegokey_to_seed(stegokey: str) -> int:
    """
    Mengubah stego-key string menjadi integer seed 64-bit
    """
    if not stegokey:
        raise ValueError("Stego-key tidak boleh kosong.")

    digest = hashlib.sha256(stegokey.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], byteorder="big")
    return seed

def generate_pixel_permutation(
    stegokey: str,
    n_pixels: int,
) -> np.ndarray:
    """
    Menghasilkan permutasi acak indeks piksel berdasarkan stego-key.

    Permutasi bersifat deterministik: stego-key dan n_pixels yang sama
    selalu menghasilkan array yang identik
    """
    if n_pixels <= 0:
        raise ValueError(f"n_pixels harus > 0, didapat: {n_pixels}")

    seed = stegokey_to_seed(stegokey)
    rng  = np.random.default_rng(seed)

    indices = np.arange(n_pixels, dtype=np.int64)
    rng.shuffle(indices)
    return indices

def verify_stegokey_reproducible(stegokey: str, n_pixels: int) -> bool:
    """
    Memverifikasi bahwa dua pemanggilan dengan key yang sama menghasilkan permutasi yang identik
    """
    p1 = generate_pixel_permutation(stegokey, n_pixels)
    p2 = generate_pixel_permutation(stegokey, n_pixels)
    return np.array_equal(p1, p2)


def stegokey_info(stegokey: str) -> dict:
    """
    Mengembalikan informasi debug tentang transformasi stego-key
    """
    digest = hashlib.sha256(stegokey.encode("utf-8")).digest()
    seed   = int.from_bytes(digest[:8], byteorder="big")
    return {
        "input":      stegokey,
        "sha256_hex": digest.hex(),
        "seed_int":   seed,
        "seed_hex":   hex(seed),
    }