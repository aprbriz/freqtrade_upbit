from PIL import Image, ImageDraw
import numpy as np

SRC = "/home/opc/python/ft_userdata_upbit/user_data/upbit_exchange_memo/W2_XRP_Order_Dashboard_Light.png"
DST = "/home/opc/python/ft_userdata_upbit/user_data/upbit_exchange_memo/W2_XRP_Order_Dashboard_Light_v2.png"

img = Image.open(SRC).convert("RGB")
W, H = img.size  # 1920x1080

# ── Step 1: Remove alert bar (y=0..24), shift body up ──
SHIFT = 24
HDR = 36  # header height (60-24)

new_img = Image.new("RGB", (W, H), (246, 247, 249))

# Header (y=24..60) → y=0
new_img.paste(img.crop((0, 24, W, 60)), (0, 0))

# Alert text centered in header (exclude clock)
atxt = img.crop((5, 2, 350, 22))
aw, ah = atxt.size
new_img.paste(atxt, ((W - aw) // 2, (HDR - ah) // 2))

# Body (y=60..end) → y=36
new_img.paste(img.crop((0, 60, W, H)), (0, HDR))

# ── Step 2: Identify & move ONLY the red button ──
# In original: "주문 하기" button at y≈1000..1052, spanning x≈825..1430
# After shift: y = orig_y - 60 + 36 = orig_y - 24
# So: y≈976..1028

# Use numpy to find exact button bounds (only the rectangular button, not chart candles)
arr = np.array(new_img)

# The button is in the order panel area (x>820) and below the order content
# Find rows where there's a WIDE block of (229,64,64) in x=820..1440
btn_top = None
btn_bot = None
for y in range(900, 1060):
    row = arr[y, 820:1440, :]
    match = ((row[:, 0] == 229) & (row[:, 1] == 64) & (row[:, 2] == 64)).sum()
    if match > 200:
        if btn_top is None:
            btn_top = y
        btn_bot = y

if btn_top and btn_bot:
    btn_bot += 1  # exclusive
    # Find x bounds within this y range
    region = arr[btn_top:btn_bot, 820:1440, :]
    r_mask = (region[:, :, 0] == 229) & (region[:, :, 1] == 64) & (region[:, :, 2] == 64)
    xs = np.where(r_mask.any(axis=0))[0]
    btn_x0 = 820 + xs.min()
    btn_x1 = 820 + xs.max() + 1

    print(f"Button found: x={btn_x0}..{btn_x1}, y={btn_top}..{btn_bot}")

    # Add margin around button
    margin = 3
    cut_x0 = btn_x0 - margin
    cut_x1 = btn_x1 + margin
    cut_y0 = btn_top - margin
    cut_y1 = btn_bot + margin

    # Crop ONLY the button (x>820, so no volume bars from chart)
    btn_img = new_img.crop((cut_x0, cut_y0, cut_x1, cut_y1))

    # Fill old position with proper background colors
    draw = ImageDraw.Draw(new_img)
    # Left part (x=820..~990) is white bg, right part is (246,247,249)
    # Simplify: sample the row just above the button for the fill
    # Actually, below the button is all (246,247,249)
    draw.rectangle([cut_x0, cut_y0, cut_x1, cut_y1], fill=(246, 247, 249))

    # Target: vertical center of the order panel
    # Order panel content: y ≈ HDR+30 (66) to y ≈ cut_y0 (button top)
    panel_top = HDR + 30
    panel_bot = cut_y0
    btn_h = cut_y1 - cut_y0
    target_y = (panel_top + panel_bot) // 2 - btn_h // 2

    print(f"Moving to: y={target_y}..{target_y + btn_h}")
    new_img.paste(btn_img, (cut_x0, target_y))

# ── Step 3: Fill bottom gap (24px) ──
footer = new_img.crop((0, H - SHIFT - 3, W, H - SHIFT - 2))
for y in range(H - SHIFT, H):
    new_img.paste(footer, (0, y))

new_img.save(DST, "PNG")
print(f"Saved: {DST}")
