import numpy as np
import math
import matplotlib.pyplot as plt
import cv2

def file_to_binary(filepath):
    "Dipake buat ubah pesan (bisa encrypted/engga) ke biner sebelum disisipin"
    try:
        with open(filepath, 'rb') as file:
            file_bytes = file.read()

        binary_string = ''.join(format(byte, '08b') for byte in file_bytes)
        return binary_string
    except Exception as e:
        print(f"Error membaca file: {e}")
        return None

def binary_to_file(binary_string, output_path):
    "Dipake buat ekstraksi biner ke bentuk asli"
    try:
        byte_list = []
        for i in range(0, len(binary_string), 8):
            byte_segment = binary_string[i:i+8]
            if len(byte_segment) == 8:
                byte_list.append(int(byte_segment, 2))
                
        with open(output_path, 'wb') as file:
            file.write(bytes(byte_list))
        return True
    except Exception as e:
        print(f"Error menyimpan file: {e}")
        return False
    
def hitung_mse(original_frame, stego_frame):
    orig = original_frame.astype("float")
    stego = stego_frame.astype("float")
    
    diff = (orig - stego) ** 2
    
    mse_value = np.mean(diff)
    return mse_value

def hitung_psnr(mse_value, max_pixel_value=255.0):
    if mse_value == 0:
        return float('inf')
    
    psnr_value = 10 * math.log10((max_pixel_value ** 2) / mse_value)
    return psnr_value

def plot_histogram(original_frame, stego_frame):
    "belum rapi ntar benerin"
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    colors = ('b', 'g', 'r')
    
    axes[0].set_title("Histogram Video Asli")
    axes[1].set_title("Histogram Stego-Video")
    
    for i, color in enumerate(colors):
        hist_orig, _ = np.histogram(original_frame[:, :, i], bins=256, range=(0, 256))
        axes[0].plot(hist_orig, color=color, alpha=0.7)
        
        hist_stego, _ = np.histogram(stego_frame[:, :, i], bins=256, range=(0, 256))
        axes[1].plot(hist_stego, color=color, alpha=0.7)
        
    plt.tight_layout()
    plt.show()
    
def cek_kapasitas(payload_binary, video_path, bits_per_pixel=8):
    "cek dulu kapasitas sebelum sisipin pesan"
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Tidak dapat membaca properti video di {video_path}")
            return False, len(payload_binary), 0
            
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        cap.release()
        
        total_pixels = width * height * total_frames
        capacity_bits = total_pixels * bits_per_pixel

        payload_size = len(payload_binary)

        if payload_size > capacity_bits:
            return False, payload_size, capacity_bits
        else:
            return True, payload_size, capacity_bits
            
    except Exception as e:
        print(f"Error saat mengecek kapasitas: {e}")
        return False, len(payload_binary), 0