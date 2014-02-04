#!/usr/bin/python3

__all__ = [
    'Table',
    'Frame',
]

import sys, collections


COW = r"""
 (    )
  \__/
  |Oo|\            __
  |  | \--_____---/  \
  \++/\           \  *
       \          /
        ||\___/\ \
        ||      ||
       / \     / \
""".replace('\t', '@#%!').strip('\n')


# split_size:
#
def split_size (size, num) :
    ofs = 0
    for i in range(1, num+1) :
        s = (size * i // num)
        yield s - ofs
        ofs = s

# test_split_size
# for s in (0, 1, 2, 5, 10, 100, 200, 1000) :
#     for n in range(1, 20) :
#         r = list(split_size(s, n))
#         assert len(r) == n, (s, n, r)
#         assert sum(r) == s, (s, n, r)
#         print("split(%2d, %2d) -> %s" % (s, n, ', '.join('%2d' % c for c in r)))


# Margins:
#
_Margins = collections.namedtuple('_Margins', ('top', 'left', 'bottom', 'right'))

class Margins (_Margins) :
    vertical = property(lambda s: s.top + s.bottom)
    horizontal = property(lambda s: s.left + s.right)


# Table:
#
class Table :


    # __init__:
    #
    def __init__ (self, nrows, ncols, vpad=0, hpad=0) :
        self.nrows = nrows
        self.ncols = ncols
        self.cells = [[Cell() for i in range(ncols)]
                      for j in range(nrows)]
        # note: add 1 row/col constraint for the last separator
        self.rparams = [LineParams(pad=vpad) for j in range(nrows+1)]
        self.cparams = [LineParams(pad=hpad) for i in range(ncols+1)]
        self.items = []


    # add:
    #
    def add (self, text, row, col, height=1, width=1, **kwargs) :
        assert 0 <= row < self.nrows, row
        assert 0 <= col < self.ncols, col
        assert 0 < height <= (self.nrows-row), height
        assert 0 < width <= (self.ncols-col), width
        item = Item(text, row, col, height, width, **kwargs)
        for j in range(row, row+height) :
            for i in range(col, col+width) :
                assert self.cells[j][i].item is None
                self.cells[j][i].item = item
        self.items.append(item)


    # vpad_span:
    #
    def vpad_span_ (self, row, height) :
        return sum(p.pad for p in self.rparams[row+1:row+height])


    # hpad_span:
    #
    def hpad_span_ (self, col, width) :
        return sum(p.pad for p in self.cparams[col+1:col+width])


    # set_vpad:
    #
    def set_vpad (self, row, pad) :
        self.rparams[row].pad = pad


    # set_hpad:
    #
    def set_hpad (self, col, pad) :
        self.cparams[col].pad = pad


    # getlines:
    #
    def getlines (self, debug=False) :
        lrows = [CLayout() for j in range(self.nrows)]
        lcols = [CLayout() for i in range(self.ncols)]
        # apply all item size requests
        for item in self.items :
            rh = item.height_request \
              - self.vpad_span_(item.row, item.height)
            rw = item.width_request \
              - self.hpad_span_(item.col, item.width)
            if rh > 0 :
                for j, s in enumerate(split_size(rh, item.height)) :
                    lrows[item.row+j].request_size(s)
            if rw > 0 :
                for i, s in enumerate(split_size(rw, item.width)) :
                    lcols[item.col+i].request_size(s)
        # apply row/col constraints
        pos = 0
        for r in range(self.nrows) :
            pos = lrows[r].apply(pos) + self.rparams[r].pad
        pos = 0
        for c in range(self.ncols) :
            pos = lcols[c].apply(pos) + self.cparams[c].pad
        # [fixme] shrink/expand items if necessary
        # for item in self.items :
        #     rh = item.height_request - ((item.height-1) * self.vpad)
        #     rw = item.width_request - ((item.width-1) * self.hpad)
        #     ah = sum(r.size for r in lrows[item.row:item.row2])
        #     aw = sum(c.size for c in lcols[item.col:item.col2])
        #     if ah < rh :
        #         print("[TODO] shrink item height %s" % item)
        #     elif ah > rh :
        #         print("[TODO] expand item height %s" % item)
        #     if aw < rw :
        #         print("[TODO] shrink item width %s" % item)
        #     elif aw > rw :
        #         print("[TODO] expand item width %s" % item)
        # dump
        char_height = sum(r.size for r in lrows) \
          + self.vpad_span_(-1, self.nrows+2)
        char_width = sum(c.size for c in lcols) \
          + self.hpad_span_(-1, self.ncols+2)
        print("final size: %dx%d" % (char_height, char_width))
        buf = TextBuffer(char_height, char_width)
        for item in self.items :
            for l, line in enumerate(item.lines) :
                buf.text(lrows[item.row+l].pos + self.rparams[item.row+l].pad + item.margins.top,
                         lcols[item.col].pos + self.cparams[item.col].pad + item.margins.left,
                         item.justify_line(line,
                                           lcols[item.col2-1].pos2 \
                                           - lcols[item.col].pos \
                                           - item.margins.horizontal))
        # [fixme] borders
        for item in self.items :
            r1 = lrows[item.row].pos + self.rparams[item.row].pad - 1
            c1 = lcols[item.col].pos + self.cparams[item.col].pad - 1
            r2 = lrows[item.row2-1].pos2 + 1 # why +1 !?
            c2 = lcols[item.col2-1].pos2 + 1
            if item.frame & Frame.TOP :
                buf.hline(r1, c1, c2)
            if item.frame & Frame.BOTTOM :
                buf.hline(r2, c1, c2)
            if item.frame & Frame.LEFT :
                buf.vline(r1, c1, r2)
            if item.frame & Frame.RIGHT :
                buf.vline(r1, c2, r2)
            # print("item %s: box(%d, %d, %d, %d)" %
            #       (item, r1, c1, r2, c2))
            # buf.box(r1, c1, r2, c2)
        # debug
        if debug :
            for row in range(self.nrows) :
                buf.text_hline(lrows[row].pos, 0, buf.width-1, '#')
            for col in range(self.ncols) :
                buf.text_vline(0, lcols[col].pos, buf.height-1, '#')
        # ok
        return buf.getlines()


# LineParams:
#
class LineParams :


    # __init__:
    #
    def __init__ (self, pad=0) :
        self.pad = pad


# Border:
#
class Border :

    UP    = 1 << 0
    DOWN  = 1 << 1
    LEFT  = 1 << 2
    RIGHT = 1 << 3

    VLINE = UP | DOWN
    HLINE = LEFT | RIGHT

    # CMAP = (
    #     #      RLDU
    #     ' ', # 0000
    #     '|', # 0001
    #     '|', # 0010
    #     '|', # 0011
    #     '-', # 0100
    #     '+', # 0101
    #     '+', # 0110
    #     '+', # 0111
    #     '-', # 1000
    #     '+', # 1001
    #     '+', # 1010
    #     '+', # 1011
    #     '-', # 1100
    #     '+', # 1101
    #     '+', # 1110
    #     '+', # 1111
    # )

    CMAP = (
        #      RLDU
        ' ', # 0000
        '|', # 0001
        '|', # 0010
        '|', # 0011
        '-', # 0100
        '+', # 0101
        '+', # 0110
        '|', # 0111
        '-', # 1000
        '+', # 1001
        '+', # 1010
        '|', # 1011
        '-', # 1100
        '-', # 1101
        '-', # 1110
        '+', # 1111
    )


# Frame:
#
class Frame :

    TOP    = 1 << 0
    LEFT   = 1 << 1
    BOTTOM = 1 << 2
    RIGHT  = 1 << 3

    LR = LEFT | RIGHT
    TB = TOP | BOTTOM
    FULL = TOP | LEFT | BOTTOM | RIGHT

    
# TextBuffer:
#
class TextBuffer :


    # __init__:
    #
    def __init__ (self, height, width) :
        self.height = height
        self.width = width
        self.chars = [[' ' for i in range(self.width)]
                      for j in range(self.height)]
        self.borders = [[0 for i in range(self.width)]
                        for j in range(self.height)]


    # getlines:
    #
    def getlines (self) :
        # update borders
        for j in range(self.height) :
            for i in range(self.width) :
                b = self.borders[j][i]
                if b == 0 or self.chars[j][i] != ' ' :
                    continue
                self.chars[j][i] = Border.CMAP[b]
        return [(''.join(l)) for l in self.chars]


    # text:
    #
    def text (self, row, col, text) :
        for i, c in enumerate(text) :
            self.chars[row][col+i] = c


    # text_hline:
    #
    def text_hline (self, row, col, col2, char='+') :
        self.text(row, col, char * (col2-col))


    # text_vline:
    #
    def text_vline (self, row, col, row2, char='+') :
        for r in range(row, row2) :
            self.chars[r][col] = char


    # box:
    #
    def box (self, row1, col1, row2, col2) :
        self.hline(row1, col1, col2)
        self.hline(row2, col1, col2)
        self.vline(row1, col1, row2)
        self.vline(row1, col2, row2)


    # vline:
    #
    def vline (self, row, col, row2) :
        for r in range(row+1, row2) :
            self.border(r, col, Border.VLINE)
        self.border(row, col, Border.DOWN)
        self.border(row2, col, Border.UP)


    # hline:
    #
    def hline (self, row, col, col2) :
        for c in range(col+1, col2) :
            self.border(row, c, Border.HLINE)
        self.border(row, col, Border.RIGHT)
        self.border(row, col2, Border.LEFT)


    # border:
    #
    def border (self, row, col, mask) :
        self.borders[row][col] |= mask


# Cell:
#
class Cell :


    # __init__:
    #
    def __init__ (self) :
        self.item = None


# CLayout:
#
class CLayout :


    # __init__:
    #
    def __init__ (self) :
        self.req_size = 0
        self.size = -1
        self.pos = -1
        self.pos2 = -1


    # request_size:
    #
    def request_size (self, size) :
        self.req_size = max(self.req_size, size)


    # apply:
    #
    def apply (self, pos) :
        # [todo] row/col constraints
        self.size = self.req_size
        self.pos = pos
        self.pos2 = self.pos + self.size
        return self.pos2


# Item:
#
class Item :


    # __init__:
    #
    def __init__ (self, text, row, col, height, width, margins=None,
                  justify='left', frame=0) :
        if margins is None :
            self.margins = Margins(0, 1, 0, 1)
        else :
            self.margins = Margins(*margins)
        self.lines = text.split('\n')
        self.nlines = len(self.lines)
        self.height_request = self.nlines + self.margins.vertical
        self.width_request = max(len(l) for l in self.lines) + self.margins.horizontal
        self.row = row
        self.col = col
        self.height = height
        self.width = width
        self.justify = justify
        self.frame = frame
        # note: these are outside item's box!
        self.row2 = self.row + self.height
        self.col2 = self.col + self.width


    # justify_line:
    #
    def justify_line (self, line, width) :
        line = line[:width]
        if self.justify == 'left' :
            return line
        elif self.justify == 'center' :
            return (' ' * ((width - len(line)) // 2)) + line
        elif self.justify == 'right' :
            return (' ' * (width - len(line))) + line
        else :
            assert 0, self.justify
