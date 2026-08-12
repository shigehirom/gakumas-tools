import os
from PIL import Image

src_path = "/root/gakumas-workspace/shared/preview_crops/crop_pattern_E3_top83_left17.png"
im = Image.open(src_path)

# Destination paths
dest_png = "/root/gakumas-workspace/gakumas-tools/packages/gakumas-images/images/pIdols/147.png"
dest_webp = "/root/gakumas-workspace/gk-img/docs/p_idols/147.webp"

os.makedirs(os.path.dirname(dest_png), exist_ok=True)
os.makedirs(os.path.dirname(dest_webp), exist_ok=True)

# Save PNG (96x128)
im.save(dest_png, "PNG")
print(f"Saved PNG to: {dest_png}")

# Save WebP (96x128)
im.convert("RGB").save(dest_webp, "WEBP", quality=90)
print(f"Saved WebP to: {dest_webp}")

print("\nFiles successfully deployed!")
