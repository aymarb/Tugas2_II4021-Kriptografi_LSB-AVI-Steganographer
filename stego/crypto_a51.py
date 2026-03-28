class MesinA51:
    def __init__(self, key_string):
        self.R1 = [0] * 19
        self.R2 = [0] * 22
        self.R3 = [0] * 23
        self.kunci_biner = self.siapkan_kunci(key_string)
        self.inisialisasi_register()

    def siapkan_kunci(self, key_string):
        biner = ''.join(format(ord(c), '08b') for c in key_string)
        if len(biner) < 64:
            biner = biner.ljust(64, '0')
        return biner[:64]

    def inisialisasi_register(self):
        for i in range(64):
            key_bit = int(self.kunci_biner[i])
            
            fb1 = self.R1[13] ^ self.R1[16] ^ self.R1[17] ^ self.R1[18] ^ key_bit
            self.R1.insert(0, fb1)
            self.R1.pop()

            fb2 = self.R2[20] ^ self.R2[21] ^ key_bit
            self.R2.insert(0, fb2)
            self.R2.pop()

            fb3 = self.R3[7] ^ self.R3[20] ^ self.R3[21] ^ self.R3[22] ^ key_bit
            self.R3.insert(0, fb3)
            self.R3.pop()

    def cek_mayoritas(self):
        jumlah = self.R1[8] + self.R2[10] + self.R3[10]
        if jumlah >= 2:
            return 1
        else:
            return 0

    def geser_register(self):
        mayoritas = self.cek_mayoritas()

        if self.R1[8] == mayoritas:
            fb1 = self.R1[13] ^ self.R1[16] ^ self.R1[17] ^ self.R1[18]
            self.R1.insert(0, fb1)
            self.R1.pop()

        if self.R2[10] == mayoritas:
            fb2 = self.R2[20] ^ self.R2[21]
            self.R2.insert(0, fb2)
            self.R2.pop()

        if self.R3[10] == mayoritas:
            fb3 = self.R3[7] ^ self.R3[20] ^ self.R3[21] ^ self.R3[22]
            self.R3.insert(0, fb3)
            self.R3.pop()

    def hasilkan_bit_keystream(self):
        self.geser_register()
        return self.R1[-1] ^ self.R2[-1] ^ self.R3[-1]

    def proses(self, payload_biner):
        result = []
        for bit_string in payload_biner:
            bit_pesan = int(bit_string)
            bit_kunci = self.hasilkan_bit_keystream()
            
            bit_hasil = bit_pesan ^ bit_kunci
            result.append(str(bit_hasil))
            
        return "".join(result)


def enkripsi_a51(payload: bytes, password: str) -> bytes:
    if not password:
        raise ValueError("Kunci A5/1 tidak boleh kosong.")
    biner = ''.join(format(b, '08b') for b in payload)
    mesin = MesinA51(password)
    cipher_biner = mesin.proses(biner)
    return bytes(int(cipher_biner[i:i+8], 2) for i in range(0, len(cipher_biner), 8))


def dekripsi_a51(cipher: bytes, password: str) -> bytes:
    if not password:
        raise ValueError("Kunci A5/1 tidak boleh kosong.")
    biner = ''.join(format(b, '08b') for b in cipher)
    mesin = MesinA51(password)
    plain_biner = mesin.proses(biner)
    return bytes(int(plain_biner[i:i+8], 2) for i in range(0, len(plain_biner), 8))