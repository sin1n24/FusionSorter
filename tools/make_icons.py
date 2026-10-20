# ツールバー用アイコン（16/32/64px）を作る。外部ライブラリ不要。
# 図柄: 3枚のカード（サムネイル）とフォルダ。色はオレンジ系。
# 使い方: python tools/make_icons.py  → resources/icon/16x16.png など
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'resources', 'icon')

ORANGE = (194, 65, 12, 255)
ORANGE_L = (251, 146, 60, 255)
CARD = (255, 255, 255, 255)
EDGE = (90, 90, 90, 255)


def png(w, h, px):
    raw = b''.join(b'\x00' + bytes(px[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def draw(n):
    s = n / 32.0
    px = bytearray(n * n * 4)

    def rect(x0, y0, x1, y1, c):
        for y in range(max(0, round(y0 * s)), min(n, round(y1 * s))):
            for x in range(max(0, round(x0 * s)), min(n, round(x1 * s))):
                px[(y * n + x) * 4:(y * n + x) * 4 + 4] = bytes(c)

    def card(x, y):
        rect(x, y, x + 9, y + 9, EDGE)
        rect(x + 1, y + 1, x + 8, y + 8, CARD)
        rect(x + 2, y + 5, x + 7, y + 7, ORANGE_L)
    card(2, 2)
    card(12, 2)
    card(22, 2)
    # フォルダ
    rect(4, 15, 14, 18, ORANGE)
    rect(4, 17, 28, 30, ORANGE)
    rect(6, 20, 26, 28, ORANGE_L)
    # 矢印（カード→フォルダ）
    rect(15, 12, 17, 16, EDGE)
    return png(n, n, px)


os.makedirs(OUT, exist_ok=True)
for n in (16, 32, 64):
    with open(os.path.join(OUT, f'{n}x{n}.png'), 'wb') as f:
        f.write(draw(n))
print('ok', OUT)
