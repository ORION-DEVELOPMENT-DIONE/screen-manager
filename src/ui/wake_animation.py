"""
Wake animation — shared boot/wake sequence for Orion Screen Manager

This module provides a single reusable animation function used for:
  1. Initial boot (full speed, "SYSTEM ONLINE" message)
  2. Wake from idle (quick speed, "WELCOME BACK" message)

"""

import math
import time
import logging
from PIL import Image, ImageDraw
 
from config.constants import SCREEN_WIDTH, SCREEN_HEIGHT
from ui.renderer import (DARK, CX, CY, R, font, font_bold,
                         _STARS, _NODE_ANGLES, _ACTIVE_NODES)
 
log = logging.getLogger("orion.boot")
 
W, H = SCREEN_WIDTH, SCREEN_HEIGHT
DR   = R   # 118
 
# Text Y positions
Y_DIONE     = 136
Y_PROTOCOL  = 160
Y_VALIDATOR = 177
Y_ONLINE    = 192
 
# Orb ring colours — matched to dione-logo.jpg
ORB_RINGS = [
    (1.00, (30,  15,  70)),
    (0.88, (55,  22, 110)),
    (0.76, (85,  28, 145)),
    (0.64, (105, 40, 175)),
    (0.52, (75,  85, 205)),
    (0.40, (40, 145, 215)),
    (0.28, (0,  195, 218)),
    (0.16, (0,  225, 215)),
]
ORB_MAX_R = 62
BG_DEEP   = (8,  3, 18)
BG_INNER  = (15, 8, 35)
 
 
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))
 
def _ease_out(t):
    return 1 - (1 - t) * (1 - t)
 
def _ease_in_out(t):
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
 
def _col_lerp(c1, c2, t):
    t = _clamp(t, 0, 1)
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
 
def _col_alpha(color, alpha, bg=(0, 0, 0)):
    a = _clamp(alpha, 0.0, 1.0)
    return tuple(int(bg[i] * (1 - a) + color[i] * a) for i in range(3))
 
 
_bg_masked = None
_bg_mask   = None
 
def _get_background():
    global _bg_masked, _bg_mask
    if _bg_masked is not None:
        return _bg_masked, _bg_mask
 
    bg_base = Image.new("RGB", (W, H), (0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_base)
 
    for ring in range(DR, 0, -2):
        t = 1 - ring / DR
        rc = _col_lerp(BG_DEEP, BG_INNER, t)
        bg_draw.ellipse([CX - ring, CY - ring, CX + ring, CY + ring], fill=rc)
 
    hs = 24
    grid_col = _col_alpha((50, 20, 90), 0.35, BG_DEEP)
    for row in range(-1, 12):
        for col in range(-1, 12):
            hx = col * hs * 1.732
            hy = row * hs * 2 + (col % 2) * hs
            if math.hypot(hx - CX, hy - CY) > DR + hs:
                continue
            pts = []
            for a in range(6):
                ang = math.radians(60 * a - 30)
                pts.append((hx + hs * 0.55 * math.cos(ang),
                            hy + hs * 0.55 * math.sin(ang)))
            for j in range(6):
                bg_draw.line([pts[j], pts[(j + 1) % 6]], fill=grid_col, width=1)
 
    _bg_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(_bg_mask).ellipse([CX - DR, CY - DR, CX + DR, CY + DR], fill=255)
    _bg_masked = Image.new("RGB", (W, H), (0, 0, 0))
    _bg_masked.paste(bg_base, mask=_bg_mask)
 
    return _bg_masked, _bg_mask
 
 
def _render_frame(boot_t, final_msg):
    """Render one animation frame. No fade-out — holds steady after t=0.88."""
    T = DARK
    bg, mask = _get_background()
    node_r = DR - 5
 
    img  = bg.copy()
    draw = ImageDraw.Draw(img)
 
    # ── Phase 1: Orb (0.00 → 0.45) ───────────────────────────────────────
    orb_t = _clamp(boot_t / 0.45, 0, 1)
    if orb_t > 0:
        sc = _ease_out(orb_t)
        al = min(1.0, orb_t * 1.4)
 
        halo_r = int(90 * sc)
        if halo_r > 4:
            for hr in range(halo_r, 0, -4):
                frac = hr / halo_r
                halo_al = 0.15 * al * (1 - frac)
                draw.ellipse([CX - hr, CY - hr, CX + hr, CY + hr],
                             fill=_col_alpha((0, 160, 170), halo_al, BG_INNER))
 
        for ring_i, (r_frac, r_col) in enumerate(ORB_RINGS):
            r_px = int(r_frac * ORB_MAX_R * sc)
            if r_px <= 1:
                continue
            ring_progress = _clamp((orb_t - ring_i * 0.03) / 0.20, 0, 1)
            brightness = 0.65 + 0.35 * ring_progress * al
            ring_col = tuple(min(255, int(c * brightness)) for c in r_col)
            draw.ellipse([CX - r_px, CY - r_px, CX + r_px, CY + r_px], fill=ring_col)
 
        pulse = 0.5 + 0.5 * math.sin(boot_t * math.pi * 6)
        core_bright = 0.7 + 0.3 * pulse
        core_r = int(12 * sc)
        if core_r > 0:
            for cr in range(core_r, 0, -1):
                cf = 1 - cr / core_r
                cal = al * core_bright * cf * cf
                draw.ellipse([CX - cr, CY - cr, CX + cr, CY + cr],
                             fill=_col_alpha((230, 255, 255), cal, (0, 225, 215)))
 
    # ── Phase 2: Scan arc (0.40 → 0.60) ──────────────────────────────────
    scan_t = _clamp((boot_t - 0.40) / 0.20, 0, 1)
    if scan_t > 0:
        sweep_r = DR - 8
        sweep_deg = _ease_in_out(scan_t) * 360
        arc_bright = 1.0 - scan_t * 0.3
        arc_col = tuple(min(255, int(c * arc_bright)) for c in (0, 220, 200))
 
        if sweep_deg > 2:
            draw.arc([CX - sweep_r, CY - sweep_r, CX + sweep_r, CY + sweep_r],
                     start=-90, end=-90 + sweep_deg, fill=arc_col, width=2)
 
        trail_ang = math.radians(-90 + _ease_in_out(scan_t) * 360)
        tx = int(CX + sweep_r * math.cos(trail_ang))
        ty = int(CY + sweep_r * math.sin(trail_ang))
        draw.ellipse([tx - 7, ty - 7, tx + 7, ty + 7],
                     fill=_col_alpha((0, 220, 200), 0.4, BG_DEEP))
        draw.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], fill=(0, 248, 228))
 
    # ── Phase 3: Bezel nodes (0.55 → 0.68) ───────────────────────────────
    nodes_t = _clamp((boot_t - 0.55) / 0.13, 0, 1)
    nodes_lit = int(nodes_t * 12)
 
    for i, ang_deg in enumerate(_NODE_ANGLES):
        ang = math.radians(ang_deg - 90)
        nx = int(CX + node_r * math.cos(ang))
        ny = int(CY + node_r * math.sin(ang))
        if i < nodes_lit:
            draw.ellipse([nx - 6, ny - 6, nx + 6, ny + 6],
                         fill=_col_alpha((0, 220, 200), 0.35, BG_DEEP))
            draw.ellipse([nx - 3, ny - 3, nx + 3, ny + 3], fill=(0, 185, 175))
            draw.ellipse([nx - 2, ny - 2, nx + 2, ny + 2], fill=(0, 240, 220))
        else:
            draw.ellipse([nx - 1, ny - 1, nx + 1, ny + 1], fill=(0, 35, 32))
 
    # ── Phase 4: "DIONE" + "PROTOCOL" (0.58 → 0.72) ─────────────────────
    text_t = _clamp((boot_t - 0.58) / 0.14, 0, 1)
    if text_t > 0:
        eo = _ease_out(text_t)
        text_y = int(Y_DIONE + 6 * (1 - eo))
 
        fb24 = font_bold(24)
        fr10 = font(10)
 
        alpha_ramp = min(1.0, text_t * 2.0)
        dione_col = _col_alpha((0, 220, 200), alpha_ramp)
        tw = draw.textlength("DIONE", font=fb24)
        draw.text((int((W - tw) / 2), text_y), "DIONE", font=fb24, fill=dione_col)
 
        proto_t = _clamp((boot_t - 0.64) / 0.10, 0, 1)
        if proto_t > 0:
            proto_al = min(1.0, proto_t * 1.8)
            proto_col = _col_alpha((0, 200, 185), 0.75 * proto_al)
            ptxt = "P R O T O C O L"
            pw = draw.textlength(ptxt, font=fr10)
            draw.text((int((W - pw) / 2), text_y + (Y_PROTOCOL - Y_DIONE)),
                      ptxt, font=fr10, fill=proto_col)
 
    # ── Phase 5: "· ORION VALIDATOR ·" (0.70 → 0.80) ────────────────────
    val_t = _clamp((boot_t - 0.70) / 0.10, 0, 1)
    if val_t > 0:
        fr10 = font(11)
        val_al = min(1.0, val_t * 1.5)
        val_col = _col_alpha((160, 180, 210), 0.85 * val_al)
        vtxt = "· ORION  VALIDATOR ·"
        vw = draw.textlength(vtxt, font=fr10)
        draw.text((int((W - vw) / 2), Y_VALIDATOR), vtxt, font=fr10, fill=val_col)
 
    # ── Phase 6: Final message (0.78 → 0.88) — stays visible ────────────
    online_t = _clamp((boot_t - 0.78) / 0.10, 0, 1)
    if online_t > 0:
        pulse_decay = max(0, 1.0 - online_t * 1.5)
        pulse_wave = 1.0 - pulse_decay * 0.25 * math.sin(online_t * math.pi * 4)
        online_al = min(1.0, online_t * 2.0) * pulse_wave
 
        online_col = _col_alpha((46, 204, 113), online_al)
        fb13 = font_bold(13)
        ow = draw.textlength(final_msg, font=fb13)
        draw.text((int((W - ow) / 2), Y_ONLINE), final_msg, font=fb13, fill=online_col)
 
    # Outer bezel ring
    draw.arc([CX - DR + 1, CY - DR + 1, CX + DR - 1, CY + DR - 1],
             start=0, end=360, fill=_col_alpha((28, 45, 90), 0.8), width=2)
 
    # Circular mask
    final = Image.new("RGB", (W, H), (0, 0, 0))
    final.paste(img, mask=mask)
    return final
 
 
def play_boot_animation(display, quick=False):
    """Play the Dione Protocol boot/wake animation.
 
    quick=False → full boot: 6s anim + 2s hold, "SYSTEM ONLINE"
    quick=True  → wake:      2s anim + 1s hold, "WELCOME BACK"
    """
    if quick:
        anim_duration = 2.0
        frame_count   = 24
        hold_time     = 1.0
        final_msg     = "WELCOME  BACK"
    else:
        anim_duration = 6.0
        frame_count   = 72
        hold_time     = 2.0
        final_msg     = "SYSTEM  ONLINE"
 
    frame_dt = anim_duration / frame_count
    mode_str = "quick wake" if quick else "full boot"
 
    log.debug("Boot animation [%s]: %d frames, %.1fs + %.1fs hold",
             mode_str, frame_count, anim_duration, hold_time)
    t0 = time.monotonic()
 
    _get_background()
 
    for frame_i in range(frame_count + 1):
        boot_t = frame_i / frame_count
        frame = _render_frame(boot_t, final_msg)
        display.show_image(frame)
        time.sleep(frame_dt)
 
    # Hold — last frame is already on screen
    log.debug("Boot animation [%s]: hold (%.1fs)", mode_str, hold_time)
    time.sleep(hold_time)
 
    elapsed = time.monotonic() - t0
    log.debug("Boot animation [%s]: complete (%.1fs)", mode_str, elapsed)