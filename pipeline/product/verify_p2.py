import sys
from pathlib import Path
from PIL import Image
import numpy as np
from render import render

print("1. Generating 5x2 + 2 Neon test PNGs...")
styles = ['chalk', 'ember', 'ash', 'stamp', 'stencil']
for s in styles:
    render('tengri', style=s, size=512, light_direction=(-1,-1)).save(f'test_p2_{s}.png')
    render('gokturk bodun', style=s, size=512, light_direction=(-1,-1)).save(f'test_p2_{s}_long.png')

render('tengri', style='neon', size=512).save('test_p2_neon.png')
render('gokturk bodun', style='neon', size=512).save('test_p2_neon_long.png')
print("-> 12 PNGs successfully generated!")

print("\n2. Letter-First Verification (target: avg_alpha > 180 for letter body):")
results = []
for s in ['chalk', 'ember', 'ash', 'stamp', 'stencil', 'neon']:
    img_rgba = np.array(render('tengri', style=s, size=512, transparent_bg=True))
    alpha_chan = img_rgba[:, :, 3]
    letter_pixels = alpha_chan[alpha_chan > 100]
    avg_alpha = letter_pixels.mean() if len(letter_pixels) > 0 else 0
    coverage = len(letter_pixels) / alpha_chan.size * 100
    results.append((s, avg_alpha, coverage))
    status = "PASS" if avg_alpha >= 180 else "FAIL"
    print(f"-> {s:10s}: avg_alpha={avg_alpha:6.1f}, coverage={coverage:4.1f}% [{status}]")

print("\n3. Color Identity Checks:")
ember_rgba = np.array(render('tengri', style='ember', size=512, transparent_bg=True))
ember_pixels = ember_rgba[ember_rgba[:, :, 3] > 100][:, :3]
emb_avg = ember_pixels.mean(axis=0) if len(ember_pixels) > 0 else np.array([0,0,0])
emb_pass = (emb_avg[0] > 200) and (emb_avg[1] > 100) and (emb_avg[2] < 100)
print(f"-> Ember RGB: R={emb_avg[0]:.0f}, G={emb_avg[1]:.0f}, B={emb_avg[2]:.0f} [{'PASS' if emb_pass else 'FAIL'}]")

neon_rgba = np.array(render('tengri', style='neon', size=512, transparent_bg=True))
neon_pixels = neon_rgba[neon_rgba[:, :, 3] > 100][:, :3]
ne_avg = neon_pixels.mean(axis=0) if len(neon_pixels) > 0 else np.array([0,0,0])
ne_pass = (ne_avg[0] < 100) and (ne_avg[1] > 200) and (ne_avg[2] > 150)
print(f"-> Neon  RGB: R={ne_avg[0]:.0f}, G={ne_avg[1]:.0f}, B={ne_avg[2]:.0f} [{'PASS' if ne_pass else 'FAIL'}]")

print("\n4. Legacy & Stamp Variant Tests:")
render('tengri', style='stone', size=512).save('test_legacy.png')
render('tengri', style='stamp', size=512, stamp_var='rot').save('test_stamp_rot.png')
render('tengri', style='stamp', size=512, stamp_var='grunge').save('test_stamp_grunge.png')
print("-> Legacy & Stamp variants passed!")
