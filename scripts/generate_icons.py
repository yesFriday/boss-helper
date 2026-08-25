#!/usr/bin/env python3
"""
生成 Tauri 所需的默认图标资源
"""

from pathlib import Path

def create_simple_png(width, height, filepath):
    import struct
    import zlib

    # 简单生成一个蓝青色 RGB PNG 图片
    raw_data = bytearray()
    for _ in range(height):
        raw_data.append(0) # filter byte
        for _ in range(width):
            raw_data.extend([14, 165, 233]) # #0ea5e9

    compressed = zlib.compress(raw_data)
    
    png = bytearray(b'\x89PNG\r\n\x1a\n')
    
    # IHDR
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    png.extend(struct.pack('>I', len(ihdr_data)) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc))
    
    # IDAT
    idat_crc = zlib.crc32(b'IDAT' + compressed)
    png.extend(struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc))
    
    # IEND
    iend_crc = zlib.crc32(b'IEND')
    png.extend(struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc))
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'wb') as f:
        f.write(png)

def main():
    icons_dir = Path(__file__).parent.parent / "src-tauri" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    create_simple_png(32, 32, icons_dir / "32x32.png")
    create_simple_png(128, 128, icons_dir / "128x128.png")
    create_simple_png(256, 256, icons_dir / "128x128@2x.png")
    create_simple_png(256, 256, icons_dir / "icon.png")
    create_simple_png(32, 32, icons_dir / "icon.ico")
    create_simple_png(128, 128, icons_dir / "icon.icns")
    print(f"[OK] 图标资源生成完成: {icons_dir}")

if __name__ == "__main__":
    main()
