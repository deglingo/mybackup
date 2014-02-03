#

import sys, os, getopt, traceback, subprocess, copy, codecs, fnmatch, weakref, sqlite3, time
from mybackup import mbuidlg

# [todo]
def _(m) : return m


# [fixme]
MBDUMP = subprocess.check_output(['which', 'mbdump'],
                                 universal_newlines=True)
MBDUMP = os.path.realpath(MBDUMP.strip())


# trace:
#
def trace (msg, depth=0) :
    fn, ln, fc, co = traceback.extract_stack()[-(depth+2)]
    fn = os.path.realpath(fn)
    loc = '%s:%d:%s:' % (fn, ln, fc)
    sys.stderr.write('mbui:%s: %s\n' % (loc, msg))


# format_exception:
#
def format_exception (exc_info=None) :
    tp, exc, tb = \
      sys.exc_info() if exc_info is None \
      else exc_info
    lines = [('%s:%d:%s:' % (os.path.realpath(fn), ln, fc), co)
             for fn, ln, fc, co in traceback.extract_tb(tb)]
    cw = [max(len(l[c]) for l in lines) for c in range(2)]
    msg = '%s: %s\n' % (tp.__name__, exc)
    if len(msg) > 200 : msg = msg[:197] + '...'
    sep1 = ('=' * max(len(msg) - 1, (sum(cw) + 4))) + '\n'
    sep2 = ('-' * max(len(msg) - 1, (sum(cw) + 4))) + '\n'
    plines = [sep1, msg, sep2]
    plines.extend('%s%s -- %s\n' %
                  (l[0], (' ' * (cw[0] - len(l[0]))), l[1])
                  for l in reversed(lines))
    plines.append(sep1)
    return plines


# print_exception:
#
def print_exception (exc_info=None, f=None) :
    if f is None : f = sys.stderr
    f.writelines(format_exception(exc_info))


# Dialog:
#
class Dialog :


    owner = property(lambda s: None if s.__wr_owner is None
                     else s.__wr_owner())

    
    # __init__:
    #
    def __init__ (self, owner=None, name='', text='') :
        self.__wr_owner = None if owner is None \
          else weakref.ref(owner)
        self.__name = name
        self.__text = text


    # handlers:
    #
    def on_init (self) : pass


    # get_name:
    #
    def get_name (self) :
        return self.__name


    # set_text:
    #
    def set_text (self, text) :
        self.__text = text


    # get_text:
    #
    def get_text (self) :
        return self.__text


    # run:
    #
    def run (self) :
        pout = os.pipe()
        self.on_init()
        cmd = ['dialog', '--output-fd', str(pout[1])]
        cmd.extend(['--title', 'TITLE'])
        cmd.extend(self.get_widget())
        trace("> %s" % ' '.join(cmd))
        pid = os.fork()
        if pid == 0 :
            # child
            os.close(pout[0])
            proc = subprocess.Popen(cmd, close_fds=False)
            r = proc.wait()
            os.close(pout[1])
            sys.exit(r)
        else :
            # parent
            os.close(pout[1])
            dc = codecs.getincrementaldecoder('utf-8')(errors='replace')
            out = ''
            while True :
                data = os.read(pout[0], 4096)
                if not data :
                    out += dc.decode(b'', True)
                    break
                out += dc.decode(data, False)
            os.close(pout[0])
            rpid, r = os.waitpid(pid, 0)
            trace(">> %d: '%s'" % (r, out))
            return r, out


# DMsgBox:
#
class DMsgBox (Dialog) :


    # get_widget:
    #
    def get_widget (self) :
        return ['--msgbox', self.get_text(), '0', '0']
            

# DMenu:
#
class DMenu (Dialog) :


    # __init__:
    #
    def __init__ (self, menu=(), **kw) :
        Dialog.__init__(self, **kw)
        self.__menu = None
        self.set_menu(menu)


    # get_widget:
    #
    def get_widget (self) :
        menu = self.get_menu()
        mh = min(20, len(menu))
        wid = ['--menu', self.get_text(), '0', '0', str(mh)]
        for i in menu :
            wid.extend(i)
        return wid


    # set_menu:
    #
    def set_menu (self, menu) :
        self.__menu = tuple(copy.deepcopy(menu))


    # get_menu:
    #
    def get_menu (self) :
        return self.__menu


    # get_entry:
    #
    def get_entry (self, tag) :
        for mtag, item in self.__menu :
            if mtag == tag :
                return item
        return None


# DMenuMain:
#
class DMenuMain (DMenu) :


    # on_init:
    #
    def on_init (self) :
        text = (_("Current configuration: '%(config)s'") + "\n\n" +
                _("What do you want to do ?")) \
                % {'config': self.owner.config}
        self.set_text(text)


# DialogManager:
#
class DialogManager :


    # __init__:
    #
    def __init__ (self, driver, dlgspecs) :
        self.__driver = driver
        self.__dialogs = {}
        for dname, dspec in dlgspecs.items() :
            dtype = globals()[dspec['type']]
            dlg = dtype(name=dname, **dspec.get('args', {}))
            self.__dialogs[dname] = dlg


    # __getitem__:
    #
    def __getitem__ (self, name) :
        return self.__dialogs[name]


    # run:
    #
    def run (self, name) :
        dlg = self.__dialogs[name]
        self.broadcast(dlg, 'init')
        r, out = dlg.run()
        return r, out


    # broadcast:
    #
    def broadcast (self, dlg, event) :
        n = 'd_%s_%s' % (dlg.get_name().replace('-', '_'), event)
        h = getattr(self.__driver, n, None)
        if h is not None :
            h(dlg, event)


# MBUIApp:
#
class MBUIApp :


    # main:
    #
    def main (self) :
        # parse the command line
        logfile = ''
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'l:')
        for o, a in opts :
            if o in ('-l',) :
                logfile = a
            else :
                assert 0, (o, a)
        assert not args, args
        # redirect and run
        if logfile :
            flog = open(logfile, 'wt')
            os.dup2(flog.fileno(), sys.stderr.fileno())
        exc = None
        try:
            self.real_main()
        except Exception:
            exc = sys.exc_info()
        if exc :
            fexc = format_exception(exc)
            sys.stderr.writelines(fexc)
            text = _("Sorry, something terrible just happened:") + "\n\n"
            text += ''.join(fexc)
            DMsgBox(text=text).run()
            r = 1
        else :
            r = 0
        if logfile :
            flog.close()
        return r


    # getconf:
    #
    def getconf (self, name, config='') :
        cmd = [MBDUMP, '-c', name]
        if config : cmd.append(config)
        value = subprocess.check_output(cmd, universal_newlines=True)
        return value.strip()


    # real_main:
    #
    def real_main (self) :
        global CONFIGDIR
        trace("HELLO")
        self.config = None
        CONFIGDIR = self.getconf('system.pkgsysconfdir')
        trace("CONFIGDIR: '%s'" % CONFIGDIR)
        self.dm = DialogManager(self, mbuidlg.DIALOG)
        # main loop
        while True :
            if self.config is None :
                r, out = self.dm.run('select-config')
                if r != 0 :
                    break
                self.config = self.dm['select-config'].get_entry(out)
                self.dbfile = self.getconf('dbfile', config=self.config)
                trace("CONFIG set: '%s'" % self.config)
                continue # just in case get_entry() returned '' ?
            else :
                r, out = self.dm.run('main')
                if r != 0 :
                    break
                if out == '1' :
                    self.__inspect()
                else :
                    assert 0, out


    # __inspect:
    #
    def __inspect (self) :
        while True :
            r, out = self.dm.run('select-disk')
            if r != 0 :
                return
            self.disk = self.dm['select-disk'].get_entry(out)
            while True :
                r, out = self.dm.run('select-dump')
                if r != 0 :
                    break
                self.dump = int(out, 10)
                self.__inspect_dump()


    # __inspect_dump:
    #
    def __inspect_dump (self) :
        assert 0, (self.config, self.disk, self.dump)


    # d_select_config_init:
    #
    def d_select_config_init (self, dlg, e) :
        menu = []
        for child in os.listdir(CONFIGDIR) :
            full = os.path.join(CONFIGDIR, child)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, 'mybackup.conf')) :
                menu.append((str(len(menu)+1), child))
        dlg.set_menu(menu)


    # d_main_init:
    #
    def d_main_init (self, dlg, e) :
        dlg.set_text((_('Current configuration: %(config)s') + '\n\n' +
                      _('What do you want to do ?')
                      % {'config': self.config}))


    # d_select_disk_init:
    #
    def d_select_disk_init (self, dlg, e) :
        db = sqlite3.connect(self.dbfile)
        c = db.cursor()
        c.execute('select disk from dumps group by disk')
        menu = [(str(n+1), d[0]) for n, d in enumerate(c.fetchall())]
        c.close()
        dlg.set_menu(menu)


    # d_select_dump_init:
    #
    def d_select_dump_init (self, dlg, e) :
        db = sqlite3.connect(self.dbfile)
        c = db.cursor()
        c.execute('select runid, fname from dumps where disk == ? order by runid desc', (self.disk,))
        dumps = list(c.fetchall())
        menu = []
        for d in dumps :
            c.execute('select hrs from runs where runid == ?', (str(d[0]),))
            sel = list(c.fetchall())
            assert len(sel) == 1, (sel, d)
            sel = sel[0]
            date = time.strftime('%Y/%m/%d %H:%M:%S', time.strptime(sel[0], '%Y%m%d%H%M%S'))
            menu.append(('%04d' % d[0], date))
        dlg.set_menu(menu)


# exec
if __name__ == '__main__' :
    app = MBUIApp()
    sys.exit(app.main())
    
