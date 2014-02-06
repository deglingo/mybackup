#!/usr/bin/python3

__all__ = [
    'Table',
    'Frame',
]

import sys, os, collections, traceback


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


# debug
DEBUG = bool(os.environ.get('ASCIITABLE_DEBUG', ''))

def trace (msg) :
    if DEBUG :
        fn, ln, fc, co = traceback.extract_stack()[-2]
        fn = os.path.realpath(fn)
        sys.stderr.write('asciitable:%s:%d:%s: %s\n' %
                          (fn, ln, fc, msg))


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



# Direction:
#
class Direction :

    UP    = U = 1 << 0
    DOWN  = D = 1 << 1
    LEFT  = L = 1 << 2
    RIGHT = R = 1 << 3

    UD = VERTICAL = UP | DOWN
    LR = HORIZONTAL = LEFT | RIGHT
    ALL = VERTICAL | HORIZONTAL


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


# Margins:
#
_Margins = collections.namedtuple('_Margins', ('top',
                                               'left',
                                               'bottom',
                                               'right'))

class Margins (_Margins) :

    vertical = property(lambda s: s.top + s.bottom)
    horizontal = property(lambda s: s.left + s.right)


# Frame:
#
class Frame :

    TOP    = T = 1 << 0
    LEFT   = L = 1 << 1
    BOTTOM = B = 1 << 2
    RIGHT  = R = 1 << 3

    LR = LEFT | RIGHT
    TB = TOP | BOTTOM    
    BOX = LR | TB
    LR


# Justify:
#
class Justify :

    LEFT = 0
    CENTER = 1
    RIGHT = 2


# Table:
#
class Table :


    nrows = property(lambda s: s.__nrows)
    ncols = property(lambda s: s.__ncols)
    children = property(lambda s: s.__children.keys())

    
    # __init__:
    #
    def __init__ (self) :
        self.__nrows = 0
        self.__ncols = 0
        self.__cells = []
        self.__children = {}


    # __set_size:
    #
    def __set_size (self, nrows, ncols) :
        # expand columns
        if ncols > self.__ncols :
            for j in range(self.__nrows) :
                self.__cells[j] += [Cell() for i in range(self.__ncols, ncols)]
            self.__ncols = ncols
        # add lines
        if nrows > self.__nrows :
            self.__cells += [[Cell() for i in range(self.__ncols)]
                             for j in range(self.__nrows, nrows)]
            self.__nrows = nrows


    # get_child:
    #
    # [fixme] private ?
    #
    def get_child (self, name) :
        return self.__children[name]


    # add:
    #
    def add (self, text, row, col, height=1, width=1, **kwargs) :
        assert row >= 0, row
        assert col >= 0, col
        assert height >= 1, height
        assert width >= 1, width
        child = Child(text, row, col, height, width, **kwargs)
        assert child.name not in self.__children, child.name
        self.__children[child.name] = child
        self.__set_size(child.row2, child.col2)
        for j in range(child.row, child.row2) :
            for i in range(child.col, child.col2) :
                self.__cells[j][i].children.append(child)


    # getlines:
    #
    def getlines (self) :
        layout = self.layout()
        trace("creating TextBuf: %dx%d" %
              (layout.char_height, layout.char_width))
        textbuf = TextBuffer(layout.char_height, layout.char_width)
        for lchild in layout.children.values() :
            child = self.__children[lchild.name]
            child.draw(textbuf, lchild)
        for lframe in layout.lframes :
            textbuf.draw_frame(lframe.borders, lframe.y, lframe.x, lframe.y2, lframe.x2)
        # debug
        textbuf.draw_char(0, 0, '#')
        textbuf.draw_char(textbuf.height-1, textbuf.width-1, '#')
        return textbuf.getlines()


    # layout:
    #
    def layout (self) :
        layout = Layout(self)
        layout.request()
        layout.allocate()
        return layout


# Layout:
#
class Layout :


    nrows = property(lambda s: s.table.nrows)
    ncols = property(lambda s: s.table.ncols)

    
    # __init__:
    #
    def __init__ (self, table) :
        self.table = table
        self.children = dict((n, LChild(n)) for n in table.children)
        self.char_height = 0
        self.char_width = 0
        self.lrows = [LLine() for j in range(self.nrows)]
        self.lcols = [LLine() for i in range(self.ncols)]
        self.vpad = [0 for j in range(self.nrows+1)]
        self.hpad = [0 for i in range(self.ncols+1)]
        self.lframes = []
        trace("layout: init (%dx%d, %d children)" %
              (self.nrows, self.ncols, len(self.children)))


    # mapchildren:
    #
    def mapchildren (self) :
        for n, lc in self.children.items() :
            yield self.table.get_child(n), lc


    # vpad_span:
    #
    def vpad_span (self, row1, row2) :
        return sum(self.vpad[row1+1:row2])


    # hpad_span:
    #
    def hpad_span (self, col1, col2) :
        return sum(self.hpad[col1+1:col2])


    # request:
    #
    def request (self) :
        trace("layout: request")
        # borders padding
        for c, lc in self.mapchildren() :
            self._request_borders(c, lc)
        # children request
        for c, lc in self.mapchildren() :
            self._request_child(c, lc)


    # _request_borders:
    #
    def _request_borders (l, c, lc) :
        lc.borders = ((1 if c.frame & Frame.TOP else 0),
                      (1 if c.frame & Frame.LEFT else 0),
                      (1 if c.frame & Frame.BOTTOM else 0),
                      (1 if c.frame & Frame.RIGHT else 0))
        l.vpad[c.row]  = max(l.vpad[c.row],  lc.borders[0]) # top
        l.hpad[c.col]  = max(l.hpad[c.col],  lc.borders[1]) # left
        l.vpad[c.row2] = max(l.vpad[c.row2], lc.borders[2]) # bottom
        l.hpad[c.col2] = max(l.hpad[c.col2], lc.borders[3]) # right


    # _request_child:
    #
    def _request_child (l, c, lc) :
        # row/col request
        rh, rw = c.size_request()
        rh += c.margins.vertical - l.vpad_span(c.row, c.row2)
        rw += c.margins.horizontal - l.hpad_span(c.col, c.col2)
        for row, size in enumerate(split_size(rh, c.height)) :
            l.lrows[c.row+row].set_request(size)
        for col, size in enumerate(split_size(rw, c.width)) :
            l.lcols[c.col+col].set_request(size)
        # frame
        if c.frame != 0 :
            lf = LFrame(c.frame, c.row, c.col, c.height, c.width)
            l.lframes.append(lf)


    # allocate:
    #
    def allocate (l) :
        trace("layout: allocate")
        pos = 0
        for row in range(l.nrows) :
            h = l.lrows[row].size_request
            pos = l.lrows[row].allocate(pos, h, l.vpad[row])
        trace("%d rows: %s" %
              (l.nrows, ', '.join("%d/%d/%d" % (l.lrows[row].pos, l.vpad[row], l.lrows[row].size)
                                  for row in range(l.nrows))))
        pos = 0
        for col in range(l.ncols) :
            w = l.lcols[col].size_request
            pos = l.lcols[col].allocate(pos, w, l.hpad[col])
        trace("%d cols: %s" %
              (l.ncols, ', '.join("%d/%d/%d" % (l.lcols[col].pos, l.hpad[col], l.lcols[col].size)
                                  for col in range(l.ncols))))
        # allocate children
        for c, lc in l.mapchildren() :
            y = l.lrows[c.row].pos + l.vpad[c.row] + c.margins[0]
            x = l.lcols[c.col].pos + l.hpad[c.col] + c.margins[1]
            y2 = l.lrows[c.row2-1].pos2 - c.margins[2]
            x2 = l.lcols[c.col2-1].pos2 - c.margins[3]
            lc.allocate(y, x, y2-y, x2-x)
        # allocate frames
        for lf in l.lframes :
            l._alloc_frame(lf)
        # set buffer size
        l.char_height = l.lrows[-1].pos2 + l.vpad[-1]
        l.char_width = l.lcols[-1].pos2 + l.hpad[-1]


    # _alloc_frame:
    #
    def _alloc_frame (l, lf) :
        # alloc
        y = l.lrows[lf.row].pos + l.vpad[lf.row] - (1 + lf.ofs[0])
        x = l.lcols[lf.col].pos + l.hpad[lf.col] - (1 + lf.ofs[1])
        y2 = l.lrows[lf.row2-1].pos2 + lf.ofs[2]
        x2 = l.lcols[lf.col2-1].pos2 + lf.ofs[3]
        lf.allocate(y, x, y2-y, x2-x)


# LLine:
#
class LLine :


    # __init__:
    #
    def __init__ (self) :
        self.size_request = 0


    # set_request:
    #
    def set_request (self, size) :
        self.size_request = max(self.size_request, size)


    # allocate:
    #
    def allocate (self, pos, size, pad) :
        self.pos = pos
        self.size = size
        self.pos2 = self.pos + self.size + pad
        return self.pos2


# LChild:
#
class LChild :


    y2 = property(lambda s: s.y + s.h)
    x2 = property(lambda s: s.x + s.w)

    
    # __init__:
    #
    def __init__ (self, name) :
        self.name = name
        self.y = self.x = self.h = self.w = 0


    # allocate:
    #
    def allocate (self, y, x, h, w) :
        trace("allocating child: %d, %d, %dx%d" % (y, x, h, w))
        # allocation, global char coordinates
        self.y = y
        self.x = x
        self.h = h
        self.w = w


# LFrame:
#
class LFrame :


    row2 = property(lambda s: s.row + s.height)
    col2 = property(lambda s: s.col + s.width)
    y2 = property(lambda s: s.y + s.h)
    x2 = property(lambda s: s.x + s.w)

    
    # __init__:
    #
    def __init__ (self, borders, row, col, height, width) :
        self.borders = borders
        self.row = row
        self.col = col
        self.height = height
        self.width = width
        self.ofs = [0, 0, 0, 0]


    # allocate:
    #
    def allocate (self, y, x, h, w) :
        trace("allocating frame: %d, %d, %dx%d" % (y, x, h, w))
        self.y = y
        self.x = x
        self.h = h
        self.w = w


# Cell:
#
class Cell :


    # __init__:
    #
    def __init__ (self) :
        self.children = []


# Child:
#
class Child :


    __namecount = {}


    # __init__:
    #
    def __init__ (self, text, row, col, height, width, frame=0, name=None, justify=Justify.LEFT) :
        if isinstance(text, str) :
            self.text = text.split('\n')
        else :
            self.text = []
            for l in text :
                assert isinstance(l, str), l
                self.text.extend(l.split('\n'))
        if name is None :
            count = Child.__namecount.get(self.__class__, 1)
            name = '%s$%d' % (self.__class__.__name__, count)
            Child.__namecount[self.__class__] = count + 1
        self.name = name
        self.row = row
        self.col = col
        self.height = height
        self.width = width
        self.row2 = self.row + self.height
        self.col2 = self.col + self.width
        self.frame = frame
        self.justify = justify
        self.margins = Margins(0, 1, 0, 1)


    # size_request:
    #
    def size_request (self) :
        if self.text :
            return len(self.text), max(len(l) for l in self.text)
        else :
            return 0, 0


    # draw:
    #
    def draw (self, textbuf, lchild) :
        # debug
        # dbg = '%' * (lchild.w)
        # for y in range(lchild.y, lchild.y2) :
        #     textbuf.draw_text(y, lchild.x, dbg)
        # draw text
        if self.justify == Justify.LEFT :
            for row, line in enumerate(self.text) :
                textbuf.draw_text(lchild.y + row, lchild.x, line)
        elif self.justify == Justify.CENTER :
            for row, line in enumerate(self.text) :
                textbuf.draw_text(lchild.y + row,
                                  lchild.x + (lchild.w - len(line)) // 2,
                                  line)
        elif self.justify == Justify.RIGHT :
            for row, line in enumerate(self.text) :
                textbuf.draw_text(lchild.y + row,
                                  lchild.x + lchild.w - len(line),
                                  line)
        else :
            assert 0, self.justify


# TextBuffer:
#
class TextBuffer :


    # __init__:
    #
    def __init__ (self, height, width) :
        self.height = height
        self.width = width
        self.chars = [[[0, 0] for i in range(width)]
                      for j in range(height)]


    # getlines:
    #
    def getlines (self) :
        return [''.join((chr(ch) if ch else CMAP[li])
                        for ch, li in l)
                for l in self.chars]


    # clip:
    #
    def clip (self, y, x) :
        return not ((0 <= y < self.height) and (0 <= x < self.width))

    
    # draw_char:
    #
    def draw_char (self, y, x, char) :
        if self.clip(y, x) :
            trace("CLIP: '%c' (%d,%d <> %dx%d)" %
                  (char, y, x, self.height, self.width))
            return
        if isinstance(char, str) :
            assert len(char) == 1, char
            char = ord(char)
            assert char >= 0, char
        elif isinstance(char) :
            assert char >= 0, char
        else :
            assert 0, char
        self.chars[y][x][0] = char


    # draw_cline:
    #
    def draw_cline (self, y, x, dirs) :
        if self.clip(y, x) :
            trace("CLIP: '%x' (%d,%d <> %dx%d)" %
                  (dirs, y, x, self.height, self.width))
            return
        self.chars[y][x][1] |= dirs

        
    # draw_text:
    #
    def draw_text (self, y, x, text) :
        for i, c in enumerate(text) :
            self.draw_char(y, x+i, c)


    # draw_frame:
    #
    def draw_frame (self, borders, y1, x1, y2, x2) :
        if borders & Frame.TOP :
            self.draw_hline(y1, x1, x2) # T
        if borders & Frame.LEFT :
            self.draw_vline(y1, x1, y2) # L
        if borders & Frame.BOTTOM :
            self.draw_hline(y2, x1, x2) # B
        if borders & Frame.RIGHT :
            self.draw_vline(y1, x2, y2) # R


    # draw_box:
    #
    def draw_box (self, y1, x1, y2, x2) :
        self.draw_hline(y1, x1, x2) # T
        self.draw_vline(y1, x1, y2) # L
        self.draw_hline(y2, x1, x2) # B
        self.draw_vline(y1, x2, y2) # R


    # draw_hline:
    #
    def draw_hline (self, y1, x1, x2) :
        self.draw_cline(y1, x1, Direction.RIGHT)
        self.draw_cline(y1, x2, Direction.LEFT)
        for x in range(x1+1, x2) :
            self.draw_cline(y1, x, Direction.LR)


    # draw_vline:
    #
    def draw_vline (self, y1, x1, y2) :
        self.draw_cline(y1, x1, Direction.DOWN)
        self.draw_cline(y2, x1, Direction.UP)
        for y in range(y1+1, y2) :
            self.draw_cline(y, x1, Direction.UD)
