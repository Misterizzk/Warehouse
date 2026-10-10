"""Shared desktop palette: warm white, charcoal and Warehouse yellow.

Use STATUS_* on light cards and VIDEO_STATUS_COLORS on dark camera/map
surfaces. Brand yellow is an accent/background; body text uses dark ink.
"""
BG = '#F4F3ED'
PANEL = '#FFFFFF'
FG = '#1B1D18'
MUTED = '#62655C'
ACCENT = '#FFD500'
ACCENT_HOVER = '#E7C200'
SIDEBAR = HEADER = '#191B18'
ON_DARK = '#F7F7F2'
MUTED_ON_DARK = '#BFC2B7'
EDGE = '#DDDED4'
FIELD_BORDER = '#858A7B'
FOCUS = '#756100'
SURFACE_ALT = '#F0F1EA'
ROW_ALT = '#F7F8F2'
ROW_SELECTED = '#FFF3B0'
DISABLED_BG = '#E1E3D9'
DISABLED_FG = '#686C61'
SCROLL_THUMB = '#8A9081'
SCROLL_TRACK = '#E5E7DE'
DARK_HOVER = '#30332B'
SUCCESS = '#14734E'
SUCCESS_BG = '#E6F5EB'
WARNING = '#795600'
WARNING_BG = '#FFF4C4'
DANGER = '#B42338'
DANGER_BG = '#FDE8EB'
NEUTRAL_BG = '#E9EBE3'
STATUS_COLORS = {
    'Normal': SUCCESS, 'Warning': WARNING, 'Melewati batas': DANGER,
    'Data perlu diperbaiki': MUTED, 'Tanpa stok': MUTED,
    'Stok habis': MUTED, 'QR tidak dikenal': MUTED,
}
STATUS_BACKGROUNDS = {
    'Normal': SUCCESS_BG, 'Warning': WARNING_BG, 'Melewati batas': DANGER_BG,
    'Data perlu diperbaiki': NEUTRAL_BG, 'Tanpa stok': NEUTRAL_BG,
    'Stok habis': NEUTRAL_BG, 'QR tidak dikenal': NEUTRAL_BG,
}
VIDEO_BG = '#171C18'
VIDEO_FG = '#EEF2E8'
VIDEO_MUTED = '#BFC9B7'
VIDEO_GRID = '#303A31'
VIDEO_STATUS_COLORS = {
    'Normal': '#63D59A', 'Warning': ACCENT, 'Melewati batas': '#FF8C99',
    'Data perlu diperbaiki': VIDEO_MUTED, 'Tanpa stok': VIDEO_MUTED,
    'Stok habis': VIDEO_MUTED, 'QR tidak dikenal': VIDEO_MUTED,
}
