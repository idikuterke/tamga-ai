import os
from PIL import Image, ImageDraw, ImageFont
from render import render

artifact_dir = "C:/Users/pc/.gemini/antigravity/brain/e2ab0726-bc1c-4242-b571-32631c9eaaf4"
os.makedirs(artifact_dir, exist_ok=True)

print("--- İŞ 2: GENERATING STAMP DIAGNOSTICS (4 VARIATIONS) ---")
variations = [
    ("ref", None, "a) Mevcut Hal (Referans)"),
    ("rot", "rot", "b) Artırılmış Döndürme (±4-5°)"),
    ("grunge", "grunge", "c) Yoğun Grunge / Aşınma"),
    ("black", "black", "d) Koyu Siyah Renk")
]

imgs = []
for name, var_param, label in variations:
    print(f"-> Generating stamp variation: {label}...")
    img = render("tengri", style="stamp", size=512, stamp_var=var_param)
    out_path = os.path.join(artifact_dir, f"stamp_var_{name}.png")
    img.save(out_path)
    print(f"   Saved {out_path} (Size: {img.size})")
    imgs.append((img, label))

# Create a 2x2 grid
w, h = imgs[0][0].size
grid_w = w * 2 + 40
grid_h = h * 2 + 80
grid_img = Image.new("RGB", (grid_w, grid_h), (240, 240, 240))
draw = ImageDraw.Draw(grid_img)

# Try loading a basic font for labels
try:
    font = ImageFont.truetype("arial.ttf", 20)
except Exception:
    font = ImageFont.load_default()

coords = [
    (10, 35, 10, 10),
    (w + 30, 35, w + 30, 10),
    (10, h + 75, 10, h + 50),
    (w + 30, h + 75, w + 30, h + 50)
]

for i, (img, label) in enumerate(imgs):
    img_x, img_y, lbl_x, lbl_y = coords[i]
    draw.text((lbl_x, lbl_y), label, fill=(0, 0, 0), font=font)
    grid_img.paste(img, (img_x, img_y))

grid_path = os.path.join(artifact_dir, "stamp_diagnostics_2x2.png")
grid_img.save(grid_path)
print(f"-> Saved 2x2 comparison grid to: {grid_path}")


print("\n--- İŞ 3: GENERATING NEW STYLES TESTS (SHORT & LONG) ---")
for style in ["parchment", "carved", "chalk", "ember", "ash", "stencil"]:
    print(f"-> Testing '{style}' with SHORT text ('tengri')...")
    img_short = render("tengri", style=style, size=512)
    out_short = os.path.join(artifact_dir, f"test_{style}_short.png")
    img_short.save(out_short)
    print(f"   Saved {out_short} (Size: {img_short.size})")
    
    print(f"-> Testing '{style}' with LONG text (5+ words)...")
    img_long = render("tengri bolmaklık kültigin yazıtları bodun", style=style, size=512)
    out_long = os.path.join(artifact_dir, f"test_{style}_long.png")
    img_long.save(out_long)
    print(f"   Saved {out_long} (Size: {img_long.size})")

print("\n--- RUNNING SYSTEM REGRESSION TESTS ---")
import test_render
print("\nAll tasks and regression tests completed successfully!")
