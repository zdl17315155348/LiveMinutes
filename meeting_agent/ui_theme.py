"""Small, dependency-free desktop widgets for the LiveMinutes workspace."""
import math
import tkinter as tk
from tkinter import ttk

BG = '#F2F3F8'
INK = '#17262A'
MUTED = '#7C839F'
BLUE = '#3933D8'
TEAL = '#2CBFB4'
FONT = 'Microsoft YaHei UI'


def setup_theme(root):
    root.configure(bg=BG)
    root.option_add('*Font', (FONT, 10))
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=(FONT, 10), background='white', foreground=INK)
    style.configure('TFrame', background='white')
    style.configure('TLabel', background='white', foreground=INK)
    style.configure('TButton', padding=(14, 8), borderwidth=0, background='#EFEEFC', foreground=BLUE)
    style.map('TButton', background=[('active', '#E1DFFD'), ('disabled', '#F2F3F8')],
              foreground=[('disabled', '#A4A9BB')])
    style.configure('TCombobox', padding=7, borderwidth=1, arrowsize=14,
                    fieldbackground='white', background='white', bordercolor='#E3E5EE')
    style.map('TCombobox', fieldbackground=[('readonly', 'white')],
              foreground=[('disabled', '#A4A9BB')])
    style.configure('TCheckbutton', background='white', padding=(0, 8))
    style.configure('Mode.TRadiobutton', background='#F2F3F8', foreground=MUTED,
                    padding=(10, 9), indicatoron=False)
    style.layout('Mode.TRadiobutton', [('Radiobutton.padding', {'children': [
        ('Radiobutton.label', {'sticky': 'nswe'})], 'sticky': 'nswe'})])
    style.map('Mode.TRadiobutton', background=[('selected', '#DFDCFF')],
              foreground=[('disabled', '#A4A9BB'), ('selected', BLUE)])
    style.configure('TNotebook', background=BG, borderwidth=0, bordercolor=BG, lightcolor=BG, darkcolor=BG, tabmargins=0)
    style.configure('TNotebook.Tab', padding=(24, 11), background='#E9EAF3', foreground=MUTED, borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', BLUE), ('active', '#DFDCFF')],
              foreground=[('selected', 'white')])
    style.layout('TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
    style.layout('TNotebook.Tab', [])
    style.configure('Horizontal.TProgressbar', background=TEAL, troughcolor='#ECEEF5',
                    borderwidth=0, lightcolor=TEAL, darkcolor=TEAL)
    style.configure('Vertical.TScrollbar', borderwidth=0, arrowsize=10,
                    background='#DDDDEB', troughcolor='white')


def rounded(canvas, x, y, w, h, color, radius=18, top_right=None, **kwargs):
    r = min(radius, w / 2, h / 2)
    t = min(top_right or r, w / 2, h / 2)
    points = []
    for cx, cy, cr, start in [(x+w-t, y+t, t, -90), (x+w-r, y+h-r, r, 0),
                               (x+r, y+h-r, r, 90), (x+r, y+r, r, 180)]:
        for step in range(13):
            angle = math.radians(start+step*7.5)
            points.extend((cx+cr*math.cos(angle), cy+cr*math.sin(angle)))
    return canvas.create_polygon(*points, fill=color, outline='', **kwargs)


class Card(tk.Canvas):
    def __init__(self, parent, color='white', signature=False, padding=22, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, **kwargs)
        self.color, self.signature, self.padding = color, signature, padding
        self.body = tk.Frame(self, bg=color)
        self.window = self.create_window(padding, padding, window=self.body, anchor='nw')
        self.bind('<Configure>', self._resize)

    def _resize(self, event):
        self.delete('surface')
        rounded(self, 1, 4, event.width-2, event.height-5, '#E6E8F1', top_right=60 if self.signature else None, tags='surface')
        rounded(self, 0, 0, event.width-2, event.height-5, self.color, top_right=60 if self.signature else None, tags='surface')
        self.tag_lower('surface')
        self.itemconfigure(self.window, width=max(1, event.width-self.padding*2),
                           height=max(1, event.height-self.padding*2-5))


class ActionButton(tk.Canvas):
    """Rounded button with keyboard focus and ttk-compatible state configuration."""
    def __init__(self, parent, text, command, fill='white', foreground=BLUE, **kwargs):
        self._text, self._command = text, command
        self._state = kwargs.pop('state', 'normal')
        self.fill, self.foreground, self.hover = fill, foreground, False
        super().__init__(parent, height=44, width=kwargs.pop('width', 220), bg=parent.cget('bg'),
                         highlightthickness=0, takefocus=True, cursor='hand2', **kwargs)
        self.bind('<Configure>', self._draw)
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<ButtonRelease-1>', self._click)
        self.bind('<space>', self._click)
        self.bind('<Return>', self._click)
        self.bind('<FocusIn>', self._draw)
        self.bind('<FocusOut>', self._draw)

    def _hover(self, value):
        self.hover = value
        self._draw()

    def _click(self, event):
        if self._state != 'disabled':
            if event.type == tk.EventType.ButtonRelease and not (0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()):
                return
            self.focus_set()
            self._command()
        return 'break'

    def _draw(self, event=None):
        self.delete('all')
        disabled = self._state == 'disabled'
        color = '#E9EAF2' if disabled else ('#E3E0FF' if self.hover else self.fill)
        rounded(self, 1, 1, self.winfo_width()-2, self.winfo_height()-2, color, radius=22)
        self.create_text(self.winfo_width()/2, self.winfo_height()/2, text=self._text,
                         fill='#A4A9BB' if disabled else self.foreground, font=(FONT, 10, 'bold'))
        if self.focus_get() == self:
            self.create_rectangle(8, 6, self.winfo_width()-8, self.winfo_height()-6, outline='#AAA5FF', dash=(2, 3))
        self.configure(cursor='arrow' if disabled else 'hand2')

    def configure(self, cnf=None, **kwargs):
        redraw = False
        if 'state' in kwargs:
            self._state = kwargs.pop('state')
            redraw = True
        if 'text' in kwargs:
            self._text = kwargs.pop('text')
            redraw = True
        result = super().configure(cnf, **kwargs) if cnf is not None or kwargs else None
        if redraw:
            self._draw()
        return result

    config = configure

    def __getitem__(self, name):
        return self._state if name == 'state' else super().__getitem__(name)


class Waveform(tk.Canvas):
    """Smoothed input-level visualization; silence stays visually quiet."""
    def __init__(self, parent):
        super().__init__(parent, bg=BLUE, height=62, highlightthickness=0)
        self.level = 0.0
        self.phase = 0

    def draw(self, target, active):
        self.level += (target-self.level)*.22
        self.phase += .24
        self.delete('all')
        width = self.winfo_width()
        for i in range(39):
            envelope = .3 + .7*abs(math.sin(i*.38+self.phase))
            height = 3 + (42*self.level*envelope if active else 0)
            x = 3+i*max(1, (width-6)/38)
            self.create_line(x, 31-height/2, x, 31+height/2, fill='#C9C7FF', width=3, capstyle='round')


class Selection(ActionButton):
    """Rounded mode selector or compact switch, backed by a Tk variable."""
    def __init__(self, parent, text, variable, command=None, value=None, **kwargs):
        self.variable, self.value = variable, value
        self.changed = command
        super().__init__(parent, text, self._select, **kwargs)
        self.trace = variable.trace_add('write', lambda *args: self._draw())
        self.bind('<Destroy>', self._cleanup_trace, add='+')

    def _cleanup_trace(self, event):
        if event.widget == self:
            self.variable.trace_remove('write', self.trace)

    def _select(self):
        self.variable.set(self.value if self.value is not None else not self.variable.get())
        if self.changed:
            self.changed()

    def _draw(self, event=None):
        self.delete('all')
        selected = self.variable.get() == self.value if self.value is not None else bool(self.variable.get())
        disabled = self._state == 'disabled'
        width, height = self.winfo_width(), self.winfo_height()
        text_color = '#A4A9BB' if disabled else (BLUE if selected else MUTED)
        if self.value is not None:
            color = '#E5E2FC' if selected else ('#EAE9F5' if self.hover else '#F2F3F8')
            rounded(self, 2, 3, max(1, width-4), max(1, height-6), color, radius=18)
            self.create_text(width/2, height/2, text=self._text, fill=text_color,
                             font=(FONT, 10, 'bold' if selected else 'normal'))
        else:
            # Right-aligned switches keep the label readable and the target generous.
            self.create_text(2, height/2, anchor='w', text=self._text,
                             fill='#A4A9BB' if disabled else INK, font=(FONT, 9))
            track = '#B9B6DD' if disabled and selected else (BLUE if selected else '#D8DCE9')
            if self.hover and not disabled:
                track = '#554DE5' if selected else '#BFC3D7'
            x, y = width-43, height/2-11
            rounded(self, x, y, 40, 22, track, radius=11)
            center = x+29 if selected else x+11
            self.create_oval(center-8, y+3, center+8, y+19, fill='white', outline='')
        if self.focus_get() == self:
            self.create_rectangle(3, 2, width-3, height-2, outline='#AAA5FF', dash=(2, 3))
        self.configure(cursor='arrow' if disabled else 'hand2')


class SlimScrollbar(tk.Canvas):
    """Arrow-free rounded scrollbar with native scrolling fractions and page clicks."""
    def __init__(self, parent, command):
        super().__init__(parent, width=12, bg=parent.cget('bg'), highlightthickness=0, bd=0)
        self.command = command
        self.first, self.last = 0.0, 1.0
        self.hover, self.dragging = False, False
        self.grab_offset = 0
        self.bind('<Configure>', self._draw)
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<Button-1>', self._press)
        self.bind('<B1-Motion>', self._drag)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<MouseWheel>', self._wheel)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _geometry(self):
        length = max(1, self.winfo_height()-8)
        thumb = min(length, max(28, length*(self.last-self.first)))
        travel = length-thumb
        start = 4 + travel*self.first/max(.0001, 1-(self.last-self.first))
        return start, thumb, travel

    def _hover(self, value):
        self.hover = value
        self._draw()

    def _draw(self, event=None):
        self.delete('all')
        if self.last-self.first >= .9999:
            return
        start, thumb, _ = self._geometry()
        color = BLUE if self.dragging else ('#AAA4DD' if self.hover else '#D1D2E2')
        rounded(self, 3, start, 6, thumb, color, radius=3)

    def _press(self, event):
        if self.last-self.first >= .9999:
            return
        start, thumb, _ = self._geometry()
        if start <= event.y <= start+thumb:
            self.dragging = True
            self.grab_offset = event.y-start
            self._draw()
        else:
            self.command('scroll', -1 if event.y < start else 1, 'pages')

    def _drag(self, event):
        if self.dragging:
            _, _, travel = self._geometry()
            fraction = (event.y-4-self.grab_offset)/max(1, travel)*(1-(self.last-self.first))
            self.command('moveto', max(0, min(1, fraction)))

    def _release(self, event):
        self.dragging = False
        self._draw()

    def _wheel(self, event):
        if event.delta:
            self.command('scroll', -max(1, abs(event.delta)//120)*(1 if event.delta > 0 else -1), 'units')
        return 'break'
