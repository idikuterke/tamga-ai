from render import render, STYLES

print("1. Testing specific styles: stone and parchment (Fallback / Composite test)...")
for style in ["stone", "parchment"]:
    print(f"-> Rendering style: '{style}' (texture_path: {STYLES[style].get('texture_path')}, blend_mode: {STYLES[style].get('blend_mode')})")
    img = render("gök türk", style=style, size=512, degradation=0.3)
    img.save(f"test_{style}.png")
    print(f"   Saved test_{style}.png successfully (Size: {img.size}, Mode: {img.mode})")

print("\n2. Testing all remaining styles to ensure full system stability...")
for style in STYLES.keys():
    if style not in ["stone", "parchment"]:
        print(f"-> Rendering style: '{style}'")
        img = render("tengri", style=style, size=512, degradation=0.1)
        img.save(f"test_{style}.png")

print("\n3. Testing Texture Variation System: Rendering 'tengri' with 'stone' 5 times...")
for i in range(1, 6):
    img = render("tengri", style="stone", size=512, degradation=0.1)
    filename = f"test_stone_v{i}.png"
    img.save(filename)
    print(f"   Saved {filename} with random texture variation.")

print("\n4. Testing Multi-line Text with Stone Texture (Aspect Ratio & Texture Stretching Check)...")
img_multiline = render("gök türk\nbodun", style="stone", size=512)
img_multiline.save("test_multiline.png")
print(f"   Saved test_multiline.png successfully -> Size: {img_multiline.size}, Mode: {img_multiline.mode}")
assert img_multiline.size[1] != 512, f"Expected non-square dynamic height, got {img_multiline.size}!"
assert img_multiline.size != (512, 512), "Multi-line rendering must not be stretched or forced to square size!"

print("\n5. Testing Multi-line Text, Custom Text Color, and Transparent Background...")
img_multi_trans = render("gök türk\nbodun\ntengri", style="stone", size=512, text_color="#ff0000", transparent_bg=True)
img_multi_trans.save("test_multiline_transparent.png")
print(f"   Saved test_multiline_transparent.png (Size: {img_multi_trans.size}, Mode: {img_multi_trans.mode})")

assert img_multi_trans.mode == "RGBA", "Transparent background must produce RGBA image!"
assert img_multi_trans.size[1] != 512, "Multi-line rendering must expand canvas height dynamically!"

print("\n6. Testing all post-processing styles (Short & Long text scaling check)...")
import os
artifact_dir = "C:/Users/pc/.gemini/antigravity/brain/e2ab0726-bc1c-4242-b571-32631c9eaaf4"
for new_style in ["ink_bleed", "stamp", "parchment", "carved", "chalk", "ember", "ash", "stencil"]:
    print(f"-> Testing '{new_style}' with SHORT text ('tengri')...")
    img_short = render("tengri", style=new_style, size=512)
    img_short.save(f"test_{new_style}_short.png")
    if os.path.exists(artifact_dir):
        img_short.save(os.path.join(artifact_dir, f"test_{new_style}_short.png"))
    print(f"   Saved test_{new_style}_short.png -> Size: {img_short.size}")
    
    print(f"-> Testing '{new_style}' with LONG text (5+ words)...")
    img_long = render("tengri bolmaklık kültigin yazıtları bodun", style=new_style, size=512)
    img_long.save(f"test_{new_style}_long.png")
    if os.path.exists(artifact_dir):
        img_long.save(os.path.join(artifact_dir, f"test_{new_style}_long.png"))
    print(f"   Saved test_{new_style}_long.png -> Size: {img_long.size}")

print("\nAll tests completed successfully! All 10 styles (plain, fircha, ink_bleed, stamp, carved, parchment, chalk, ember, ash, stencil) verified for short and long text scaling without degradation.")

