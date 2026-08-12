import os
from PIL import Image

src_path = "/root/gakumas-workspace/shared/Screenshot_20260809-132114.png"
out_dir = "/root/gakumas-workspace/shared/preview_crops"
os.makedirs(out_dir, exist_ok=True)

im = Image.open(src_path)
w, h = im.size
print(f"Loaded image: {w} x {h}")

# Hybrid patterns based on feedback:
# - Left/Bottom based on D (left ~17-18, bottom ~154)
# - Top/Right based on B (top ~82-83, right ~70-72)
# Aspect ratio 3:4 (96:128): width 54, height 72 is exact 3:4

crop_configs = [
    {
        "name": "crop_pattern_E1_exact_3to4_left17",
        "box": (17, 82, 71, 154) # w=54, h=72 (ratio 0.750)
    },
    {
        "name": "crop_pattern_E2_exact_3to4_left18",
        "box": (18, 82, 72, 154) # w=54, h=72 (ratio 0.750)
    },
    {
        "name": "crop_pattern_E3_top83_left17",
        "box": (17, 83, 70, 154) # w=53, h=71 (ratio 0.746)
    },
    {
        "name": "crop_pattern_E4_top83_left18",
        "box": (18, 83, 71, 154) # w=53, h=71 (ratio 0.746)
    }
]

for config in crop_configs:
    box = config["box"]
    cropped = im.crop(box)
    resized = cropped.resize((96, 128), Image.Resampling.LANCZOS)
    
    out_png = os.path.join(out_dir, f"{config['name']}.png")
    out_2x = os.path.join(out_dir, f"{config['name']}_2x.png")
    
    resized.save(out_png)
    resized.resize((192, 256), Image.Resampling.NEAREST).save(out_2x)
    print(f"Saved: {out_png} (Box: {box})")

print("\nGenerated hybrid crop patterns (E1 ~ E4) in /root/gakumas-workspace/shared/preview_crops/")
