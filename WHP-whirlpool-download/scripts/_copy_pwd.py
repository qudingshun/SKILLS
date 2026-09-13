#!/usr/bin/env python3
import hashlib, os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

pw_dir = r'C:\Users\qudin\.openclaw\workspace\skills\WHP-whirlpool-download\scripts\runtime_config\passwords'

# Read fanruan password
with open(os.path.join(pw_dir, 'fanruan_password.dat'), 'rb') as f:
    fanruan_enc = f.read()

# Decrypt fanruan
seed = f"{os.getenv('USERNAME')}|{os.getenv('COMPUTERNAME')}|WPOOL_REPORT_V1"
key = hashlib.sha256(seed.encode('utf-8')).digest()
iv = fanruan_enc[:16]
enc_data = fanruan_enc[16:]
cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
decoder = cipher.decryptor()
decrypted_padded = decoder.update(enc_data) + decoder.finalize()
unpadder = padding.PKCS7(128).unpadder()
pwd = unpadder.update(decrypted_padded) + unpadder.finalize()
pwd = pwd.decode('utf-8')

print(f'Fanruan password decrypted OK, length={len(pwd)}')

# Encrypt as OA password (same key)
iv2 = os.urandom(16)
padder = padding.PKCS7(128).padder()
padded = padder.update(pwd.encode('utf-8')) + padder.finalize()
cipher2 = Cipher(algorithms.AES(key), modes.CBC(iv2), backend=default_backend())
encoder = cipher2.encryptor()
oa_enc = iv2 + encoder.update(padded) + encoder.finalize()

with open(os.path.join(pw_dir, 'oa_password.dat'), 'wb') as f:
    f.write(oa_enc)

print('OA password saved (same as fanruan)')
