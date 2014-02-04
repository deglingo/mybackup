#!/usr/bin/python3

__all__ = [
    'Table',
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
    def __init__ (self, nrows, ncols, vpad=1, hpad=1, margins=(1, 1, 1, 1)) :
        self.nrows = nrows
        self.ncols = ncols
        self.vpad = vpad
        self.hpad = hpad
        self.margins = Margins(*margins)
        self.cells = [[Cell() for i in range(ncols)]
                      for j in range(nrows)]
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


    # getlines:
    #
    def getlines (self) :
        lrows = [CLayout() for j in range(self.nrows)]
        lcols = [CLayout() for i in range(self.ncols)]
        # apply all item size requests
        for item in self.items :
            rh = item.height_request - ((item.height-1) * self.vpad)
            rw = item.width_request - ((item.width-1) * self.hpad)
            if rh > 0 :
                for j, s in enumerate(split_size(rh, item.height)) :
                    lrows[item.row+j].request_size(s)
            if rw > 0 :
                for i, s in enumerate(split_size(rw, item.width)) :
                    lcols[item.col+i].request_size(s)
        # apply row/col constraints
        pos = self.margins.top
        for r in lrows :
            pos = r.apply(pos) + self.vpad
        pos = self.margins.left
        for c in lcols :
            pos = c.apply(pos) + self.hpad
        # shrink/expand items if necessary
        for item in self.items :
            rh = item.height_request - ((item.height-1) * self.vpad)
            rw = item.width_request - ((item.width-1) * self.hpad)
            ah = sum(r.size for r in lrows[item.row:item.row2])
            aw = sum(c.size for c in lcols[item.col:item.col2])
            if ah < rh :
                print("[TODO] shrink item height %s" % item)
            elif ah > rh :
                print("[TODO] expand item height %s" % item)
            if aw < rw :
                print("[TODO] shrink item width %s" % item)
            elif aw > rw :
                print("[TODO] expand item width %s" % item)
        # dump
        char_height = sum(r.size for r in lrows) \
          + (self.nrows-1) * self.vpad \
          + self.margins.vertical
        char_width = sum(c.size for c in lcols) \
          + (self.ncols-1) * self.hpad \
          + self.margins.horizontal
        print("final size: %dx%d" % (char_height, char_width))
        buf = TextBuffer(char_height, char_width)
        for item in self.items :
            for l, line in enumerate(item.lines) :
                buf.text(lrows[item.row+l].pos + item.margins.top,
                         lcols[item.col].pos + item.margins.left,
                         item.justify_line(line,
                                           lcols[item.col2-1].pos2 \
                                           - lcols[item.col].pos \
                                           - item.margins.horizontal))
        # [fixme] borders
        for item in self.items :
            r1 = lrows[item.row].pos - 1
            c1 = lcols[item.col].pos - 1
            r2 = lrows[item.row2-1].pos2
            c2 = lcols[item.col2-1].pos2
            # print("item %s: box(%d, %d, %d, %d)" %
            #       (item, r1, c1, r2, c2))
            buf.box(r1, c1, r2, c2)
        # ok
        return buf.getlines()


# Border:
#
class Border :

    UP    = 1 << 0
    DOWN  = 1 << 1
    LEFT  = 1 << 2
    RIGHT = 1 << 3

    VLINE = UP | DOWN
    HLINE = LEFT | RIGHT

    CMAP = (
        #      RLDU
        ' ', # 0000
        '|', # 0001
        '|', # 0010
        '|', # 0011
        '-', # 0100
        '+', # 0101
        '+', # 0110
        '+', # 0111
        '-', # 1000
        '+', # 1001
        '+', # 1010
        '+', # 1011
        '-', # 1100
        '+', # 1101
        '+', # 1110
        '+', # 1111
    )

    
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
        return [(''.join(l)+'\n') for l in self.chars]


    # text:
    #
    def text (self, row, col, text) :
        for i, c in enumerate(text) :
            self.chars[row][col+i] = c


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
    def __init__ (self, text, row, col, height, width, margins=None, justify='left') :
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
        else :
            assert 0, self.justify
