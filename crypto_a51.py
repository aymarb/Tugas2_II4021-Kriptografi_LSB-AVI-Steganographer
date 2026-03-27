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


def enkripsi_a51(payload_biner_asli, password):
    if not password:
        password = "Kriptografi_asik"
        
    mesin = MesinA51(password)
    return mesin.proses(payload_biner_asli)


def dekripsi_a51(cipher_biner, password):
    if not password:
        password = "Kriptografi_asik"
        
    mesin = MesinA51(password)
    return mesin.proses(cipher_biner)
