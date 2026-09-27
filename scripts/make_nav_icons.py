"""Mustamsak navigation icon family for the reviewer workspace sidebar (static/nav-icons.js).`n`nRun:  python scripts/make_nav_icons.py   ->  static/icons/nav/*.svg (sprite skeleton: tight crop, no halo).

One fixed skeleton for every icon: rounded tile, one key light from the top left (diagonal body gradient
plus a soft sheen on the upper half), a hairline edge, then the glyph drawn on a 24-unit grid with a
single teal accent fill on its meaningful part. Two states share the geometry:
  idle   - pale tile, ink strokes, teal accent at low opacity
  active - teal tile, white strokes, white accent
Plain SVG only (no <style>, no animation) so the files can be uploaded as images.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'static' / 'icons' / 'nav'
OUT.mkdir(parents=True, exist_ok=True)

STATES = {
    'idle':   dict(t1='#F8FAFC', t2='#E3EAF0', edge='#D5DEE6', sheen=.85, ink='#2B3B4B', acc='#11685D', acc_op=.20, acc_line='#11685D'),
    'active': dict(t1='#1C8F7C', t2='#0B574D', edge='#0A4C44', sheen=.30, ink='#FFFFFF', acc='#FFFFFF', acc_op=.30, acc_line='#FFFFFF'),
}

# Each glyph: (accent fills, ink strokes, accent strokes) on a 24x24 grid.
GLYPHS = {
    'documents': (
        ['M8 6h8l4 4v10a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z'],
        ['M4 16V4a2 2 0 0 1 2-2h8', 'M8 6h8l4 4v10a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z', 'M16 6v4h4', 'M9.5 14h6', 'M9.5 17.5h4'],
        []),
    'people': (
        ['M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'],
        ['M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'],
        ['M12 13.6a2.1 2.1 0 1 0 0-4.2 2.1 2.1 0 0 0 0 4.2z', 'M8.6 17.6c.6-1.7 1.9-2.6 3.4-2.6s2.8.9 3.4 2.6']),
    'archive': (
        ['M4.5 4h15A1.5 1.5 0 0 1 21 5.5v2A1.5 1.5 0 0 1 19.5 9h-15A1.5 1.5 0 0 1 3 7.5v-2A1.5 1.5 0 0 1 4.5 4z'],
        ['M4.5 4h15A1.5 1.5 0 0 1 21 5.5v2A1.5 1.5 0 0 1 19.5 9h-15A1.5 1.5 0 0 1 3 7.5v-2A1.5 1.5 0 0 1 4.5 4z', 'M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9'],
        ['M10 13h4']),
    'guide': (
        ['M12 6.5C10 5 7 4.5 4 5v13c3-.5 6 0 8 1.5z'],
        ['M12 6.5C10 5 7 4.5 4 5v13c3-.5 6 0 8 1.5', 'M12 6.5C14 5 17 4.5 20 5v13c-3-.5-6 0-8 1.5', 'M12 6.5v13'],
        ['M15 9.5h2.5', 'M15 12.5h2.5']),
    'gemini': (
        ['M12 7c.5 2.6 2.4 4.5 5 5-2.6.5-4.5 2.4-5 5-.5-2.6-2.4-4.5-5-5 2.6-.5 4.5-2.4 5-5z'],
        ['M4 8V6a2 2 0 0 1 2-2h2', 'M16 4h2a2 2 0 0 1 2 2v2', 'M20 16v2a2 2 0 0 1-2 2h-2', 'M8 20H6a2 2 0 0 1-2-2v-2'],
        ['M12 7c.5 2.6 2.4 4.5 5 5-2.6.5-4.5 2.4-5 5-.5-2.6-2.4-4.5-5-5 2.6-.5 4.5-2.4 5-5z']),
    'training': (
        ['M16 6.5h2.5a.5.5 0 0 1 .5.5v11h-3.5V7a.5.5 0 0 1 .5-.5z'],
        ['M4 4v16h16', 'M7.5 13h2.5a.5.5 0 0 1 .5.5V18H7v-4.5a.5.5 0 0 1 .5-.5z', 'M12 9.5h2.5a.5.5 0 0 1 .5.5v8h-3.5v-8a.5.5 0 0 1 .5-.5z'],
        ['M16 6.5h2.5a.5.5 0 0 1 .5.5v11h-3.5V7a.5.5 0 0 1 .5-.5z']),
    'agent': (
        ['M8 9h8v6H8z'],
        ['M4 8V6a2 2 0 0 1 2-2h2', 'M16 4h2a2 2 0 0 1 2 2v2', 'M20 16v2a2 2 0 0 1-2 2h-2', 'M8 20H6a2 2 0 0 1-2-2v-2'],
        ['M8 9h8v6H8z', 'M10 12h4']),
}


def icon(name, state):
    s = STATES[state]
    fills, inks, accents = GLYPHS[name]
    g = [f'<path d="{d}" fill="{s["acc"]}" fill-opacity="{s["acc_op"]}"/>' for d in fills]
    g += [f'<path d="{d}" fill="none" stroke="{s["ink"]}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>' for d in inks]
    g += [f'<path d="{d}" fill="none" stroke="{s["acc_line"]}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>' for d in accents]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{s["t1"]}"/><stop offset="1" stop-color="{s["t2"]}"/></linearGradient>
    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="{s["sheen"]}"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
  </defs>
  <rect x="0.75" y="0.75" width="38.5" height="38.5" rx="11" fill="url(#tile)" stroke="{s["edge"]}" stroke-width="1.5"/>
  <rect x="2" y="2" width="36" height="17" rx="10" fill="url(#sheen)"/>
  <g transform="translate(8 8)">
    {chr(10).join("    " + p for p in g).strip()}
  </g>
</svg>
'''


def brand():
    """The brand mark as a hero-quality tile: deep teal body, top-left sheen, white scan-frame glyph
    with one lit reading line (the focal point)."""
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
  <defs>
    <linearGradient id="body" x1=".15" y1="0" x2=".85" y2="1"><stop offset="0" stop-color="#23A08B"/><stop offset=".5" stop-color="#11685D"/><stop offset="1" stop-color="#0A3F39"/></linearGradient>
    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".38"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
    <linearGradient id="beam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#9FF3E3" stop-opacity="0"/><stop offset=".5" stop-color="#C8FFF4"/><stop offset="1" stop-color="#9FF3E3" stop-opacity="0"/></linearGradient>
  </defs>
  <rect x="2" y="4" width="76" height="74" rx="20" fill="#083530"/>
  <rect x="2" y="2" width="76" height="74" rx="20" fill="url(#body)"/>
  <rect x="5" y="5" width="70" height="34" rx="17" fill="url(#sheen)"/>
  <g fill="none" stroke="#FFFFFF" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M18 29v-6a5 5 0 0 1 5-5h6M51 18h6a5 5 0 0 1 5 5v6M62 49v6a5 5 0 0 1-5 5h-6M29 60h-6a5 5 0 0 1-5-5v-6"/>
    <path d="M30 32h20M30 48h11"/>
  </g>
  <rect x="24" y="38.2" width="32" height="3.6" rx="1.8" fill="url(#beam)"/>
</svg>
'''


for name in GLYPHS:
    for state in STATES:
        if name == 'agent' and state == 'active':
            continue
        (OUT / f'nav-{name}-{state}.svg').write_text(icon(name, state), encoding='utf-8')
(OUT / 'brand-mark.svg').write_text(brand(), encoding='utf-8')
print(len(list(OUT.glob('*.svg'))), 'icons in', OUT)
