"""Interactive, vector-drawn warehouse overview; geometry is schematic only."""
import math
import tkinter as tk


STATUS = {
    'Normal': ('#2CC982', '#164A3E', 'N'),
    'Warning': ('#FFBD3D', '#665026', 'W'),
    'Melewati batas': ('#FF646F', '#682F3D', '!'),
    'Tanpa stok': ('#788C9F', '#2D3D4C', '–'),
    'Data perlu diperbaiki': ('#C3A1FA', '#4B3D67', '?'),
}


class RackMap(tk.Canvas):
    """Schematic overhead plan: each actionable section summarizes three levels.

    ``on_section((area, rack), column, row)`` opens a side elevation for that
    column. The rack heading and border are context, never click targets.
    """

    def __init__(self, parent, on_section, **kwargs):
        kwargs.setdefault('bg', '#0C1D2C')
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('takefocus', True)
        kwargs.setdefault('height', 340)
        super().__init__(parent, **kwargs)
        self.on_section = on_section
        self.racks = {}
        self.highlight = None
        self.selected = None
        self.selected_section = None
        self.page = 0
        self.page_size = 6
        self._redraw_job = None
        self._tooltip = None
        self._tooltip_job = None
        self._destroyed = False
        self.rack_bounds = {}
        self.section_bounds = {}
        self.bind('<Configure>', self._schedule_draw)
        self.bind('<Leave>', lambda e: self._hide_tooltip())
        self.bind('<Left>', lambda e: self._key_move(-1, 0))
        self.bind('<Right>', lambda e: self._key_move(1, 0))
        self.bind('<Up>', lambda e: self._key_move(0, -1))
        self.bind('<Down>', lambda e: self._key_move(0, 1))
        self.bind('<Return>', self._key_open)
        self.bind('<space>', self._key_open)
        self.bind('<FocusIn>', self._schedule_draw)
        self.bind('<FocusOut>', self._schedule_draw)

    def set_data(self, racks, highlight=None, selected=None):
        self.racks = dict(racks)
        self.highlight = highlight.get('location_code') if isinstance(highlight, dict) else highlight
        if isinstance(selected, str):
            selected = tuple(selected.split('-')[:2])
        self.selected = selected if selected in self.racks else None
        if self.selected_section and self.selected_section[0] not in self.racks:
            self.selected_section = None
        keys = list(self.racks)
        self.page_size = 6 if self.winfo_width() >= 550 else 3
        if self.selected:
            self.page = keys.index(self.selected) // self.page_size
        self._draw()

    def _schedule_draw(self, event=None):
        if self._destroyed:
            return
        if self._redraw_job:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(25, self._draw)

    def _draw(self):
        if self._destroyed:
            return
        # Direct redraws (selection, data refresh) supersede pending resize work.
        # Keep its id until cancellation so destroy never leaves an orphan job.
        if self._redraw_job:
            self.after_cancel(self._redraw_job)
        self._redraw_job = None
        self._hide_tooltip()
        self.delete('all')
        self.rack_bounds.clear()
        self.section_bounds.clear()
        width, height = self.winfo_width(), self.winfo_height()
        if width < 10 or height < 10:
            return
        keys = list(self.racks)
        self.page_size = 6 if width >= 550 else 3
        pages = max(1, math.ceil(len(keys) / self.page_size))
        self.page = min(self.page, pages - 1)
        shown = keys[self.page * self.page_size:(self.page + 1) * self.page_size]
        self.create_text(14, 10, text='TAMPAK ATAS · KLIK SECTION UNTUK LIHAT TINGKAT', anchor='w',
                         fill='#90A9C0', font=('Segoe UI', 8, 'bold'))
        if pages > 1:
            self._page_control(width - 102, 9, '‹', -1, self.page > 0)
            self.create_text(width - 65, 9, text=f'{self.page + 1} / {pages}',
                             fill='#C5D8EA', font=('Segoe UI', 9))
            self._page_control(width - 28, 9, '›', 1, self.page < pages - 1)
        else:
            self.create_text(width - 14, 10, text=f'{len(keys)} rak', anchor='e',
                             fill='#90A9C0', font=('Segoe UI', 9))
        if not shown:
            self.create_text(width / 2, height / 2, text='Belum ada lokasi di area ini',
                             fill='#ADC2D6', font=('Segoe UI', 12))
            return

        left, top, right, bottom = 13, 31, width - 13, height - 13
        # Shallow floor gradient and construction lines keep this diagram crisp
        # at any desktop scale, with no raster mockup masquerading as live data.
        self.create_rectangle(left + 5, top + 6, right + 5, bottom + 5, fill='#06111D', outline='')
        bands = 24
        for i in range(bands):
            y0 = top + (bottom - top) * i / bands
            y1 = top + (bottom - top) * (i + 1) / bands + 1
            value = round(29 + 9 * i / bands)
            color = f'#{value-7:02x}{value+7:02x}{value+18:02x}'
            self.create_rectangle(left, y0, right, y1, fill=color, outline='')
        for x in range(int(left + 38), int(right), 38):
            self.create_line(x, top, x, bottom, fill='#253C4D')
        for y in range(int(top + 36), int(bottom), 36):
            self.create_line(left, y, right, y, fill='#253C4D')
        self._walls(left, top, right, bottom)

        # A wider aisle divides the two groups, matching the overview reference.
        count = len(shown)
        aisle_after = 3 if count > 3 else None
        extra_aisle = max(22, min(46, width * .055)) if aisle_after else 0
        margin = 25
        gap = max(12, min(20, width * .018))
        unit_width = min(122, (right - left - margin * 2 - gap * (count - 1) - extra_aisle) / count)
        used = count * unit_width + gap * (count - 1) + extra_aisle
        start = (left + right - used) / 2
        rack_top = top + 51
        rack_bottom = bottom - 18
        if rack_bottom - rack_top < 110:
            # The dashboard's 1366×768 layout has a short map panel. Spend
            # its spare space on the nine section targets, not on empty floor.
            rack_top = top + 35
            rack_bottom = bottom - 12
        for i, key in enumerate(shown):
            x = start + i * (unit_width + gap) + (extra_aisle if aisle_after and i >= aisle_after else 0)
            self._rack(key, self.racks[key], x, rack_top, unit_width, rack_bottom - rack_top)
        if aisle_after:
            aisle_x = start + 3 * unit_width + 2.5 * gap + extra_aisle / 2
            self.create_text(aisle_x, (rack_top + rack_bottom) / 2,
                             text='L O R O N G', angle=90, fill='#7B96AD', font=('Segoe UI', 8, 'bold'))
            for y in (rack_top + 15, rack_bottom - 15):
                self.create_line(aisle_x, y - 5, aisle_x, y + 5, fill='#577284', arrow='last', width=1)
        # A marked entry is decorative, not a claim about physical warehouse dimensions.
        middle = (left + right) / 2
        self.create_rectangle(middle - 32, bottom - 3, middle + 32, bottom + 3, fill='#142A3A', outline='')
        self.create_line(middle - 31, bottom - 6, middle + 31, bottom - 6, fill='#7B93A2', width=2)
        for direction in (-1, 1):
            x = middle + direction * 35
            self.create_rectangle(x - 5, bottom - 8, x + 5, bottom + 3, fill='#B98B2D', outline='')
            self.create_line(x - 4, bottom + 2, x + 4, bottom - 7, fill='#263441', width=3)
        if self.focus_get() is self:
            self.create_rectangle(1, 1, width - 2, height - 2, outline='#64B7FF', dash=(3, 3))

    def _walls(self, left, top, right, bottom):
        self.create_rectangle(left, top, right, bottom, outline='#61788A', width=7)
        self.create_rectangle(left + 3, top + 3, right - 3, bottom - 3, outline='#9BACB7', width=1)
        self.create_rectangle(left + 7, top + 7, right - 7, bottom - 7, outline='#102132', width=2)
        for x in range(int(left + 25), int(right - 15), 86):
            for y in (top, bottom):
                self.create_rectangle(x - 4, y - 4, x + 4, y + 6, fill='#748B99', outline='#A3B3BA')
        for y in range(int(top + 46), int(bottom - 15), 90):
            for x in (left, right):
                self.create_rectangle(x - 4, y - 5, x + 5, y + 5, fill='#748B99', outline='#A3B3BA')

    def _rack(self, key, rack, x, y, width, height):
        rack_index = len(self.rack_bounds)
        self.rack_bounds[key] = (x, y, x + width, y + height)
        color, _, _ = STATUS.get(rack['status'], STATUS['Data perlu diperbaiki'])
        selected = key == self.selected
        last = any(c['code'] == self.highlight for c in rack['cells'])
        self.create_text(x + width / 2, y - 28, text=f'AREA {key[0]}', fill='#A7BED0',
                         font=('Segoe UI', 8))
        self.create_text(x + width / 2, y - 11, text=key[1], fill='#F0F7FD',
                         font=('Segoe UI', 10, 'bold'))
        self.create_rectangle(x + 6, y + 7, x + width + 6, y + height + 6,
                              fill='#0B1722', outline='')
        if selected or last:
            self.create_rectangle(x - 4, y - 4, x + width + 4, y + height + 4,
                                  outline='#2B71AA', width=5)
            self.create_rectangle(x - 4, y - 4, x + width + 4, y + height + 4,
                                  outline='#7CCBFF' if last else '#5CAFFF', width=2)
        self.create_rectangle(x, y, x + width, y + height, fill='#102230',
                              outline=color, width=3)
        grid_left, grid_top = x + 14, y + 17
        grid_right, grid_bottom = x + width - 5, y + height - 5
        cell_width = (grid_right - grid_left) / 3
        cell_height = (grid_bottom - grid_top) / 3
        gap = 2 if width < 105 else 3
        for column in range(1, 4):
            center = grid_left + (column - .5) * cell_width
            self.create_text(center, y + 8, text=f'K{column:02d}',
                             fill='#BDD0E1', font=('Segoe UI', 7, 'bold'))
        for row in range(1, 4):
            center = grid_top + (row - .5) * cell_height
            self.create_text(x + 7, center, text=f'R{row}', angle=90,
                             fill='#BDD0E1', font=('Segoe UI', 7, 'bold'))
            for column in range(1, 4):
                section = rack['sections'].get((column, row))
                if section is None:
                    continue
                tag = f'section_{rack_index}_{column}_{row}'
                x0 = grid_left + (column - 1) * cell_width + gap / 2
                x1 = grid_left + column * cell_width - gap / 2
                y0 = grid_top + (row - 1) * cell_height + gap / 2
                y1 = grid_top + row * cell_height - gap / 2
                self.section_bounds[(key, column, row)] = (x0, y0, x1, y1)
                section_color, section_fill, section_symbol = STATUS.get(
                    section['status'], STATUS['Data perlu diperbaiki'])
                active = self.selected_section == (key, column, row)
                highlighted = any(c['code'] == self.highlight for c in section['cells'])
                self.create_rectangle(x0, y0, x1, y1, fill=section_fill,
                                      outline='#6DC6FF' if active or highlighted else section_color,
                                      width=2 if active or highlighted else 1, tags=(tag,))
                self.create_line(x0 + 2, y0 + 2, x1 - 2, y0 + 2,
                                 fill=section_color, width=2, tags=(tag,))
                self.create_text((x0 + x1) / 2, (y0 + y1) / 2 + 1,
                                 text=section_symbol, fill='#FFFFFF',
                                 font=('Segoe UI', 8, 'bold'), tags=(tag,))
                self.tag_bind(tag, '<Button-1>',
                              lambda e, k=key, c=column, r=row: self._open_section(k, c, r))
                self.tag_bind(tag, '<Enter>',
                              lambda e, k=key, c=column, r=row, s=section: self._hover(
                                  e, f"{k[0]}-{k[1]} · Kolom {c:02d} · Baris {r:02d}\n"
                                     f"Status: {s['status']} (dari 3 tingkat)\n"
                                     f"{s['batches']} batch · {s['stock']} unit\nKlik untuk tampak samping kolom"))
                self.tag_bind(tag, '<Leave>', lambda e: self._hide_tooltip())
    def _page_control(self, x, y, text, delta, enabled):
        tag = f'page_{delta}'
        self.create_rectangle(x - 12, y - 10, x + 12, y + 10,
                              fill='#203C53' if enabled else '#152B3D', outline='', tags=(tag,))
        self.create_text(x, y - 1, text=text, fill='#DFEDFA' if enabled else '#50677A',
                         font=('Segoe UI', 15, 'bold'), tags=(tag,))
        if enabled:
            self.tag_bind(tag, '<Button-1>', lambda e: self._change_page(delta))

    def _change_page(self, delta):
        next_page = self.page + delta
        pages = max(1, math.ceil(len(self.racks) / self.page_size))
        if 0 <= next_page < pages:
            self.page = next_page
            self._draw()

    def _open_section(self, key, column, row):
        self.focus_set()
        self._hide_tooltip()
        self.selected = key
        self.selected_section = (key, column, row)
        self._draw()
        self.on_section(key, column, row)

    def _key_move(self, column_delta, row_delta):
        keys = list(self.racks)
        if not keys:
            return 'break'
        if self.selected_section and self.selected_section[0] in self.racks:
            key, column, row = self.selected_section
        else:
            key = self.selected if self.selected in self.racks else keys[0]
            column, row = 1, 1
        column += column_delta
        row = (row + row_delta - 1) % 3 + 1
        index = keys.index(key)
        if column < 1:
            index = (index - 1) % len(keys)
            column = 3
        elif column > 3:
            index = (index + 1) % len(keys)
            column = 1
        key = keys[index]
        if (column, row) not in self.racks[key]['sections']:
            column, row = next(iter(self.racks[key]['sections']), (1, 1))
        self.selected = key
        self.selected_section = (key, column, row)
        self.page = index // self.page_size
        self._draw()
        return 'break'

    def _key_open(self, event=None):
        if self.selected_section and self.selected_section[0] in self.racks:
            self._open_section(*self.selected_section)
        return 'break'

    def _hover(self, event, text):
        self._hide_tooltip()
        self.configure(cursor='hand2')
        x, y = event.x_root + 12, event.y_root + 15
        self._tooltip_job = self.after(350, lambda: self._show_tooltip(x, y, text))

    def _show_tooltip(self, x, y, text):
        self._tooltip_job = None
        if self._destroyed:
            return
        tip = self._tooltip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.attributes('-topmost', True)
        tk.Label(tip, text=text, bg='#0A1D2D', fg='#E5F0F9', font=('Segoe UI', 10),
                 justify='left', padx=12, pady=9, relief='solid', borderwidth=1).pack()
        tip.update_idletasks()
        x = min(x, self.winfo_screenwidth() - tip.winfo_reqwidth() - 8)
        y = min(y, self.winfo_screenheight() - tip.winfo_reqheight() - 8)
        tip.geometry(f'+{max(0, x)}+{max(0, y)}')

    def _hide_tooltip(self):
        if self._tooltip_job:
            self.after_cancel(self._tooltip_job)
            self._tooltip_job = None
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None
        if not self._destroyed:
            self.configure(cursor='')

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self._redraw_job:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        self._hide_tooltip()
        super().destroy()
