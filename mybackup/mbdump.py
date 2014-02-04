#

import sys, os, traceback, getopt, json, weakref, collections, time
import re, sqlite3, shutil, copy, pprint, subprocess, threading
import logging, codecs, types
from subprocess import PIPE as CMDPIPE
from functools import partial

from mybackup.base import *
from mybackup import asciitable

# debug
# import mybackup as _debug_mybackup
# sys.stderr.write("MYBACKUP: %s\n" % _debug_mybackup)

from mybackup.sysconf import SYSCONF


# USAGE:
#
USAGE = """\
USAGE: mbdump [OTPIONS] CONFIG [DISK...]

OPTIONS:

  -h, --help  print this message and exit
"""


# trace:
#
_log_locations = bool(os.environ.get('MB_LOG_LOCATIONS', ''))

def _log (lvl, msg, depth=0) :
    logger = logging.getLogger('mbdump')
    fn, ln, fc, co = traceback.extract_stack()[-(depth+2)]
    fn = os.path.realpath(fn)
    r = logger.makeRecord('mbdump', lvl, fn=fn, lno=ln,
                          msg=msg, args=(), exc_info=None,
                          func=fn, extra=None, sinfo=None)
    logger.handle(r)
        
def trace (msg, depth=0) : _log(logging.DEBUG, msg, depth=depth+1)
def error (msg, depth=0) : _log(logging.ERROR, msg, depth=depth+1)


# Log levels:
#
class LogLevel :


    __levels = {}
    __byname = {}

    
    # register:
    #
    @staticmethod
    def register (lvl, name, iserr) :
        assert lvl not in LogLevel.__levels, lvl
        assert name not in LogLevel.__byname, name
        linfo = types.MappingProxyType({'level': lvl,
                                        'name': name,
                                        'iserr': iserr})
        LogLevel.__levels[lvl] = LogLevel.__byname[name] = linfo


    # list_levels:
    #
    @staticmethod
    def list_levels () :
        return [l['level'] for l in LogLevel.__levels.values()]


    # by_level:
    #
    @staticmethod
    def by_level (lvl) :
        return LogLevel.__levels[lvl]


# Register levels
LogLevel.register(logging.DEBUG, 'DEBUG', False)
LogLevel.register(logging.INFO, 'INFO', False)
LogLevel.register(logging.WARNING, 'WARNING', True)
LogLevel.register(logging.ERROR, 'ERROR', True)
LogLevel.register(logging.CRITICAL, 'CRITICAL', True)


# LogLevelFilter:
#
class LogLevelFilter :


    # __init__:
    #
    def __init__ (self) :
        self.levels = set(LogLevel.list_levels())


    # enable:
    #
    def enable (self, lvl, enab=True) :
        assert LogLevel.by_level(lvl)
        if enab :
            self.levels.add(lvl)
        else :
            self.levels.remove(lvl)
            
        
    # __call__:
    #
    def __call__ (self, rec) :
        return rec.levelno in self.levels


# LogConsoleHandler:
#
class LogConsoleHandler (logging.Handler) :


    # emit:
    #
    def emit (self, r) :
        msg = self.format(r)
        sys.stderr.write(msg)
        sys.stderr.write('\n')
        sys.stderr.flush()


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


# _mkdir:
#
def _mkdir (d) :
    if os.path.isdir(d) :
        return
    _mkdir(os.path.dirname(d))
    #trace("creating directory '%s'" % d)
    os.mkdir(d)


# _numbered_backup:
#
def _numbered_backup (fname) :
    tmp = fname + '.tmp'
    shutil.copyfile(fname, tmp)
    n = 1
    r = re.compile(r"^%s\.~(?P<N>[0-9]+)~$" \
                   % os.path.basename(fname))
    for f in os.listdir(os.path.dirname(fname)) :
        m = r.match(f)
        if m is None :
            continue
        n = max(n, int(m.group('N')))
    while True :
        bak = fname + '.~%d~' % n
        try:
            fd = os.open(bak, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            n = n + 1
            continue
        os.close(fd)
        os.rename(tmp, bak)
        trace("backup: '%s' -> '%s'" % (fname, bak))
        break


# human_size:
#
def human_size (s) :
    if s < 0 :
        return '?'
    for i, u in enumerate(('B', 'K', 'M', 'G')) :
        if s < (1000 * (1024 ** i)) :
            break
    return (('%d' % s) if i == 0 \
      else ('%.2f' % (s / (1024**i)))) + u


# cmdexec:
#
def cmdexec (cmd, wait=False, check=True, **kw) :
    cwd = kw.pop('cwd', None)
    if cwd is None : cwd = os.getcwd()
    trace("%s> %s" % (cwd, ' '.join(cmd)))
    proc = subprocess.Popen(cmd, cwd=cwd, **kw)
    if not wait :
        return proc
    r = proc.wait()
    if check and r != 0 :
        assert 0, "[todo] process failed : %s (%s)" % (cmd[0], r)
    return r


# Dates and time stamps
#
RE_HRS = re.compile(r'^\d{14}$')
RE_DATE = re.compile(r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$')


# check_stamp:
#
def check_stamp (stamp) :
    assert isinstance(stamp, int)
    # [fixme] check range ?
    return stamp


# check_hrs:
#
def check_hrs (hrs) :
    assert isinstance(hrs, str)
    assert RE_HRS.match(hrs)
    return hrs


# check_date:
#
def check_date (date) :
    assert isinstance(date, str)
    assert RE_DATE.match(date)
    return date


# stamp2hrs:
#
def stamp2hrs (stamp) :
    check_stamp(stamp)
    return check_hrs(time.strftime('%Y%m%d%H%M%S',
                                   time.localtime(stamp)))


# stamp2date:
#
def stamp2date (stamp) :
    check_stamp(stamp)
    return check_date(time.strftime('%Y/%m/%d %H:%M:%S',
                                    time.localtime(stamp)))


# date2stamp:
#
def date2stamp (date) :
    check_date(date)
    return check_stamp(int(time.mktime(time.strptime(date, '%Y/%m/%d %H:%M:%S'))))


# hrs2date:
#
def hrs2date (hrs) :
    check_hrs(hrs)
    d = '%s/%s/%s %s:%s:%s' % \
      (hrs[0:4], hrs[4:6], hrs[6:8],
       hrs[8:10], hrs[10:12], hrs[12:14])
    return check_date(d)


# attrdict:
#
def attrdict (tpname, attrs=None, defo=None) :
    tpbases = (object,)
    tpdict = {
        '_atd__names': (set(attrs) if attrs else ()),
        '_atd__defo': (copy.deepcopy(defo) if defo else {}),
        '__init__': _atd_init,
        '__repr__': _atd_repr,
        '__getattr__': _atd_getattr,
        '__setattr__': _atd_setattr,
        '__getitem__': _atd_getitem,
        '__deepcopy__': _atd_deepcopy,
        'asdict': _atd_asdict,
        'update': _atd_update,
    }
    return type(tpname, tpbases, tpdict)

def _atd_init (s, **kw) :
    k = copy.deepcopy(s._atd__defo)
    s.__d = {}
    s.update(copy.deepcopy(s._atd__defo))
    s.update(kw)

def _atd_asdict (s) :
    return copy.deepcopy(s.__d)

def _atd_update (s, d=None, **k) :
    if d is not None :
        for n, v in d.items() :
            setattr(s, n, v)
    for n, v in k.items() :
        setattr(s, n, v)
        
def _atd_repr (s) :
    return '<%s %s>' % (s.__class__.__name__, s.__d)

def _atd_getattr (s, n) :
    if n[0] == '_' :
        return object.__dict__[n]
    assert (not s._atd__names) or n in s._atd__names, n
    return s.__d[n]

def _atd_getitem (s, n) :
    assert n[0] != '_' # ?
    return getattr(s, n)

def _atd_setattr (s, n, v) :
    if n[0] == '_' :
        return object.__setattr__(s, n, v)
    assert (not s._atd__names) or n in s._atd__names, n
    s.__d[n] = v

def _atd_deepcopy (s, m) :
    kw = dict((n, copy.deepcopy(v, m))
              for n, v in s.__d.items())
    return s.__class__(**kw)


# DumpSched:
#
DumpSched = attrdict('DumpSched', ())


# JournalState:
#
JournalState = attrdict (
    'JournalState', 
    (),
    defo={'hrs': 'X',
          'config': '',
          'state': 'init',
          'dumps': {},
          'stranges': []})


# DumpInfo:
#
_DumpInfo = attrdict (
    '_DumpInfo',
    (),
    defo={'state': 'selected',
          'prevrun': -1,
          'raw_size': -1,
          'comp_size': -1,
          'nfiles': -1})

class DumpInfo (_DumpInfo) :
    raw_hsize = property(lambda s: human_size(s.raw_size))
    comp_hsize = property(lambda s: human_size(s.comp_size))
    comp_ratio = property(lambda s: s.comp_size * 100.0 / s.raw_size)


# DumpEstimate:
#
DumpEstimate = collections.namedtuple(
    'DumpEstimate',
    ('prev', 'raw', 'comp', 'est'))


# PipeThread:
#
class PipeThread :


    # __init__:
    #
    def __init__ (self, name, fin, fout, started=False, line_handler=None) :
        self.name = name
        self.fin = fin
        self.fout = list(fout)
        if line_handler is None :
            self.line_handler = None
            self.decoder = None
        else :
            self.line_handler = line_handler
            # [fixme]
            codec = codecs.getincrementaldecoder('utf-8')
            self.decoder = codec(errors='replace')

        self.start_lock = threading.Lock() # just in case ?
        self.thread = threading.Thread(target=self.run)
        self.alive = True
        self.started = False
        if started : self.start()


    # plug_output:
    #
    def plug_output (self, f) :
        with self.start_lock :
            assert self.alive and not self.started
            self.fout.append(f)


    # start:
    #
    def start (self) :
        with self.start_lock :
            assert not self.started
            self.started = True
            self.thread.start()


    # join:
    #
    def join (self) :
        with self.start_lock :
            assert self.started
            assert self.alive
            #trace("%s: join" % self.name)
            self.thread.join()
            #trace("%s: dead" % self.name)
            self.started = False
            self.alive = False
            

    # run:
    #
    def run (self) :
        try:
            self._run()
        except Exception:
            error("%s: exception:" % self.name)
            print_exception()
            sys.exit(1)

    def _run (self) :
        #trace("%s: start" % self.name)
        self.data_size = 0
        if self.line_handler is not None :
            self.line_buffer = ''
        while True :
            data = self.fin.read(65536)
            if not data : break
            self.data_size += len(data)
            for f in self.fout :
                f.write(data)
            if self.line_handler is not None :
                ldata = self.decoder.decode(data, False)
                self._process_lines(ldata, False)
        # flush the line handler
        if self.line_handler is not None :
            ldata = self.decoder.decode(b'', True)
            self._process_lines(ldata, True)
        #trace("%s: EOF" % self.name)
        for f in self.fout :
            f.close()


    def _process_lines (self, ldata, final) :
        lpos = 0
        while True :
            i = ldata.find('\n', lpos)
            if i < 0 :
                self.line_buffer += ldata[lpos:]
                break
            self.line_handler(self.line_buffer + ldata[lpos:i+1])
            self.line_buffer = ''
            lpos = i + 1
        if final and self.line_buffer :
            self.line_handler(self.line_buffer)
            self.line_buffer = ''


# Config:
#
class Config :


    start_date = property(lambda self: stamp2date(self.start_stamp))
    start_hrs = property(lambda self: stamp2hrs(self.start_stamp))

    
    # __init__:
    #
    def __init__ (self) :
        self.system = CfgSystem()

        
    # init:
    #
    def init (self, cfgname) :
        # starting date
        dt = os.environ.get('_MB_SYSTEST_DATE')
        self.start_stamp = int(time.time()) if dt is None \
          else date2stamp(dt)
        # init
        self.cfgname = cfgname
        self.cfgdir = os.path.join(self.system.pkgsysconfdir, self.cfgname)
        self.vardir = self.system.pkgvardir
        self.cfgvardir = os.path.join(self.vardir, self.cfgname)
        self.lockdir = os.path.join(self.vardir, 'lock') # note global!
        self.cfglockfile = os.path.join(self.lockdir, self.cfgname + '.lock')
        self.dbdir = os.path.join(self.cfgvardir, 'db')
        self.dbfile = os.path.join(self.dbdir, self.cfgname + '.db') 
        self.journaldir = os.path.join(self.cfgvardir, 'journal')
        self.journalfile = os.path.join(self.journaldir, 'journal.txt')
        self.dumpdir = os.path.join(self.cfgvardir, 'dumps')
        self.partdir = os.path.join(self.dumpdir, 'partial')
        self.logdir = os.path.join(self.cfgvardir, 'log')
        self.scriptsvardir = os.path.join(self.cfgvardir, 'scripts')
        # read the config file
        self.cfgfile = os.path.join(self.cfgdir, 'mybackup.conf')
        trace("reading config file: '%s'" % self.cfgfile)
        conf = json.load(open(self.cfgfile, 'rt'))
        self.configure(conf)


    # configure:
    #
    def configure (self, conf_) :
        conf = copy.deepcopy(conf_)
        self.mailto = conf.pop('mailto', '')
        self.report_columns = conf.pop('report_columns',
                                       (r'\title=DISK\%(disk)s',
                                        r'\title=STATE\center\%(state)s',
                                        r'\title=RAW SIZE\right\%(raw_hsize)s',
                                        r'\title=COMP SIZE\right\%(comp_hsize)s',
                                        r'\title=RATIO\right\%(comp_ratio).2f%%',
                                        r'\title=FILES\right\%(nfiles)d'))
        self.scripts = dict(
            (n, CfgScript(self, n, sconf))
            for n, sconf in conf.get('scripts', {}).items())
        self.disks = collections.OrderedDict(
            (n, CfgDisk(self, n, dconf))
            for n, dconf in conf.pop('disks').items())


    # list_disks:
    #
    def list_disks (self) :
        return list(self.disks.values())


# CfgSystem:
#
class CfgSystem :

    def __getattr__ (self, name) :
        return SYSCONF[name]


# CfgDisk:
#
class CfgDisk :


    config = property(lambda self: self._wr_config())

    
    # __init__:
    #
    def __init__ (self, config, name, dconf) :
        self._wr_config = weakref.ref(config)
        self.name = name
        self.configure(dconf)


    # __repr__:
    #
    def __repr__ (self) :
        return '<%s %s:%s>' % (self.__class__.__name__,
                               self.config.cfgname,
                               self.name)


    # configure:
    #
    def configure (self, dconf) :
        for n, v in dconf.items() :
            setattr(self, n, v)


    # get_dumper:
    #
    def get_dumper (self) :
        # [fixme]
        return DumperTar()


    # get_dumpname:
    #
    def get_dumpname (self, runid, level, prevrun, hrs) :
        return 'mbdump.%(config)s.%(disk)s.%(runid)03d.%(level)d-%(prevrun)03d.%(hrs)s' % {
            'config': self.config.cfgname,
            'disk': self.name,
            'runid': runid,
            'level': level,
            'prevrun': prevrun,
            'hrs': hrs }

    
    # get_dumpext:
    #
    def get_dumpext (self) :
        # [fixme]
        return '.tgz'


    # run_hooks:
    #
    def run_hooks (self, trigger, journal) :
        for hook in self.hooks :
            if trigger not in hook['triggers'].split(',') :
                continue
            script = self.config.scripts[hook['script']]
            vardir = os.path.join(self.config.scriptsvardir, script.name)
            _mkdir(vardir)
            cmd = [script.prog]
            a = {'config': self.config.cfgname,
                 'disk': self.name,
                 'orig': self.orig,
                 'path': self.path,
                 'vardir': vardir}
            cmd.extend(o % a for o in script.options + hook['options'])
            proc = cmdexec(cmd, cwd=self.config.cfgdir,
                           stdout=CMDPIPE, stderr=CMDPIPE)
            name = 'hook:%s:%s' % (trigger, self.name)
            parser = StrangeParser(name, journal)
            pout = PipeThread(name, proc.stdout, (),
                              line_handler=parser, started=True)
            perr = PipeThread(name, proc.stderr, (),
                              line_handler=parser, started=True)
            pout.join()
            perr.join()
            r = proc.wait()
            assert r == 0, (r, self, hook)


# CfgScript:
#
class CfgScript :


    config = property(lambda self: self._wr_config())

    
    # __init__:
    #
    def __init__ (self, config, name, dconf) :
        self._wr_config = weakref.ref(config)
        self.name = name
        self.configure(dconf)


    # __repr__:
    #
    def __repr__ (self) :
        return '<%s %s:%s>' % (self.__class__.__name__,
                               self.config.cfgname,
                               self.name)


    # configure:
    #
    def configure (self, dconf) :
        for n, v in dconf.items() :
            setattr(self, n, v)


# StrangeParser:
#
class StrangeParser :


    # __init__:
    #
    def __init__ (self, name, journal) :
        self.name = name
        self.journal = journal


    # __call__:
    #
    def __call__ (self, line) :
        line = line.strip()
        if not line : return
        trace("STRANGE:%s: %s" % (self.name, line))
        self.journal.record('STRANGE', source=self.name, line=line)


# Journal:
#
class Journal :


    KEYSPECS = {
        'START':  (('config', 's'),
                   ('runid',  'i+'),
                   ('hrs',    'h')),
                   
        'SELECT': (('disks', 's'),),

        'SCHEDULE': (('disk',    's'),
                     ('prevrun', 'i')),

        'DUMP-START':    (('disk',  's'),
                          ('fname', 's')),
        
        'DUMP-FINISHED': (('disk',  's'),
                          ('state', 's'),
                          ('raw_size', 'i'),
                          ('comp_size', 'i'),
                          ('nfiles',    'i')),

        'STRANGE': (('source', 's'),
                    ('line', 's')),
    }

    
    # __init__:
    #
    def __init__ (self, fname, mode) :
        self.lock = threading.Lock()
        self.fname = fname
        self.mode = mode
        self.state = JournalState()
        if mode == 'w' :
            # [FIXME] !!
            open(self.fname, 'wt').close()
        else :
            assert 0, mode # [todo]


    # summary:
    #
    def summary (self) :
        return copy.deepcopy(self.state)


    # _update:
    #
    def _update (self, key, kw) :
        s = self.state
        if key == 'START' :
            s.update(state='started',
                     config=kw['config'],
                     runid=kw['runid'],
                     hrs=kw['hrs'])
        elif key == 'SELECT' :
            for d in kw['disks'].split(',') :
                s.dumps[d] = DumpInfo(disk=d)
        elif key == 'SCHEDULE' :
            s.dumps[kw['disk']].update(state='scheduled',
                                       prevrun=kw['prevrun'])
        elif key == 'DUMP-START' :
            s.dumps[kw['disk']].update(state='started',
                                       fname=kw['fname'])
        elif key == 'DUMP-FINISHED' :
            s.dumps[kw['disk']].update(state=kw['state'],
                                       raw_size=kw['raw_size'],
                                       comp_size=kw['comp_size'],
                                       nfiles=kw['nfiles'])
        elif key == 'STRANGE' :
            s.stranges.append((kw['source'], kw['line']))
        else :
            assert 0, (key, kw)
        # trace("JOURNAL UPDATE: %s\n%s" %
        #       (key, pprint.pformat(s.asdict())))


    # escape:
    #
    def escape (self, line) :
        chars = "\\:\n"
        out = ''
        for c in line :
            if c in chars :
                out += "\\x%02x" % ord(c)
            else :
                out += c
        return out


    # record:
    #
    def record (self, key, **kwargs) :
        with self.lock :
            self.__record(key, **kwargs)

    def __record (self, key, **kwargs) :
        keyspec = Journal.KEYSPECS[key]
        assert len(kwargs) == len(keyspec), kwargs
        line = [key]
        for pname, ptype in keyspec :
            pval = kwargs[pname]
            if ptype == 's' :
                assert isinstance(pval, str)
                pval = self.escape(pval)
            elif ptype == 'h' :
                assert check_hrs(pval)
            elif ptype == 'i' :
                assert isinstance(pval, int)
                pval = str(pval)
            elif ptype == 'i+' :
                assert isinstance(pval, int) and pval > 0, pval
                pval = str(pval)
            else :
                assert 0, ptype
            line.append(pval)
        # update state
        self._update(key, kwargs)
        # write
        # [FIXME] probably some sync needed here
        trace("JOURNAL: %s: '%s'" % (key, ', '.join("'%s'" % w for w in line)))
        tmp = self.fname + '.tmp'
        f = open(tmp, 'wt')
        if os.path.exists(self.fname) :
            f.write(open(self.fname, 'rt').read())
        f.write(':'.join(line))
        f.write('\n')
        f.flush()
        f.close()
        os.rename(tmp, self.fname)


# DB:
#
class DB :


    __TABLES = (
        ('runs', (('runid', 'integer primary key autoincrement'),
                  ('hrs',   'text unique'))),

        ('dumps', (('dumpid', 'integer primary key autoincrement'),
                   ('disk', 'text'),
                   ('runid', 'references runs(runid)'),
                   ('prevrun', 'references runs(runid)'),
                   ('state', 'text'),
                   ('fname', 'text'),
                   ('raw_size', 'int'),
                   ('comp_size', 'int'),
                   ('nfiles',    'int'))),
    )


    __tpcache = {}


    # __row:
    #
    def __row (self, cur, row) :
        key = tuple(d[0] for d in cur.description)
        tp = self.__tpcache.get(key)
        if tp is None :
            tp = self.__tpcache[key] = collections.namedtuple('Row%d' % len(self.__tpcache), key)
        return tp(*row)

    
    # __init__:
    #
    def __init__ (self, fname) :
        self.fname = fname
        if os.path.exists(fname) :
            _numbered_backup(fname)
        else :
            open(fname, 'wt').close()
        self.con = sqlite3.connect(self.fname)
        self.con.row_factory = self.__row
        self._init()


    # _init:
    #
    def _init (self) :
        sel = self._execute('select * from sqlite_master')
        if sel :
            trace("[todo] update db")
            return
        for tname, tcols in DB.__TABLES :
            sql = 'create table %s (' % tname
            sql += ', '.join('%s %s' % c for c in tcols)
            sql += ')'
            self._execute(sql)
        self._commit()


    # dump:
    #
    def dump (self, depth=0) :
        lines = []
        lines.append(("  DB DUMP: %s  " % self).center(120, '*') + '\n')
        for tname, tcols in DB.__TABLES :
            sel = self._execute('select * from %s order by %s' %
                                (tname, tcols[0][0]))
            lines.append("%s: %d records\n" % (tname.upper(), len(sel)))
            if sel :
                lines.append(("  [ %s ]" % ', '.join(sel[0]._fields)) + '\n')
            for row in sel :
                lines.append(("  ( %s )" % ', '.join(str(c) for c in row)) + '\n')
        lines.append(''.center(120, '*') + '\n')
        trace("\n%s" % ''.join(lines), depth=depth+1)
                

    # _execute:
    #
    def _execute (self, sql, args=(), commit=True) :
        cur = self.con.cursor()
        #trace("SQL: %s" % sql)
        cur.execute(sql, args)
        r = list(cur.fetchall())
        if commit :
            self._commit()
        cur.close()
        return r


    # _commit:
    #
    def _commit (self) :
        self.con.commit()


    # record_run:
    #
    def record_run (self, hrs) :
        self._execute('insert into runs (hrs) values (?)',
                      (hrs,), commit=True)
        sel = self._execute('select * from runs where hrs == ?', (hrs,))
        assert len(sel) == 1
        trace("run recorded: %d (%s)" % (sel[0].runid, sel[0].hrs))
        return sel[0].runid


    # select_run:
    #
    def select_run (self, runid) :
        sel = self._execute('select * from runs where runid == ?', (runid,))
        return sel[0] if sel else None


    # record_dump:
    #
    def record_dump (self, disk, runid, prevrun, state, fname, raw_size, comp_size, nfiles) :
        self._execute('insert into dumps ' +
                      '(disk, runid, prevrun, state, fname, raw_size, comp_size, nfiles) ' +
                      'values (?, ?, ?, ?, ?, ?, ?, ?)',
                      (disk, runid, prevrun, state, fname, raw_size, comp_size, nfiles))
        trace("dump recorded: %s" % disk)


    # select_last_dump:
    #
    def select_last_dump (self, disk) :
        sel = self._execute('select * from dumps order by runid desc')
        return sel[0] if sel else None


    # get_current_cycle:
    #
    def get_current_cycle (self, disk) :
        sel = self._execute('select * from dumps ' +
                            'where disk == ? ' +
                            'order by runid desc',
                            (disk,))
        trace("get_cycle(%s) -> %s" % (disk, sel))
        return sel


# DumperTar:
#
class DumperTar :


    # [FIXME]
    GNUTAR = os.environ.get('GNUTAR', '/bin/false')

    
    # start:
    #
    def start (self, path) :
        cmd = [self.GNUTAR, '--create', '--file', '-',
               '--directory', path, '.']
        proc = cmdexec(cmd, stdout=CMDPIPE)
        return proc


    # start_index:
    #
    def start_index (self) :
        cmd = [self.GNUTAR, '--list', '--verbose',
               '--file', '-']
        proc = cmdexec(cmd, stdin=CMDPIPE, stdout=CMDPIPE)
        return proc


# Index:
#
class Index :


    # __init__:
    #
    def __init__ (self, fname) :
        self.fname = fname
        self.f = open(self.fname, 'wt')
        self.count = 0


    # __call__:
    #
    def __call__ (self, line) :
        trace("INDEX: %s" % line.rstrip())
        self.f.write(line)
        self.count += 1


    # close:
    #
    def close (self) :
        self.f.close()


# MBDumpApp:
#
class MBDumpApp :


    # main:
    #
    def main (self) :
        try:
            self.__main()
        except Exception:
            print_exception()
            sys.exit(1)


    # __main:
    #
    def __main (self) :
        self.__setup_logger()
        self.config = Config()
        # parse the command line
        # [fixme] -c should be elsewhere
        _cfgparam = ''
        shortopts = 'c:h'
        longopts = ['help']
        opts, args = getopt.gnu_getopt(sys.argv[1:], shortopts, longopts)
        for o, a in opts :
            if o in ('-h', '--help') :
                sys.stdout.write(USAGE)
                sys.exit(0)
            elif o in ('-c',) :
                _cfgparam = a
            else :
                assert 0, (o, a)
        # [REMOVEME]
        if _cfgparam :
            if len(args) >= 1 :
                self.config.init(args[0])
            o = self.config
            for n in _cfgparam.split('.') :
                o = getattr(o, n)
            sys.stdout.write('%s\n' % str(o))
            sys.exit(0)
        # init the config
        assert len(args) >= 1, args
        self.config.init(args.pop(0))
        # create some directories
        _mkdir(self.config.lockdir)
        _mkdir(self.config.dbdir)
        _mkdir(self.config.journaldir)
        _mkdir(self.config.dumpdir)
        _mkdir(self.config.partdir)
        _mkdir(self.config.logdir)
        # open the logfile and say something
        self.__open_logfile()
        trace("started at %s" % self.config.start_date)
        # acquire the config lock
        try:
            with FLock(self.config.cfglockfile, block=False) :
                self.__main_L(args)
        except FLockError as exc:
            error(exc)
            error("(this probably means that another mbdump process is running)")
            sys.exit(1)


    # __main_L:
    #
    def __main_L (self, args) :
        # open the DB
        self.db = DB(self.config.dbfile)
        # [fixme] select disks
        sched = self.__select_disks(args)
        if not sched :
            trace("no disk selected, bye")
            return
        # go
        self.__process(sched)
        # cleanup
        self.__post_process(self.journal.summary())
        # report
        title, body = self.__report(self.journal.summary())
        trace("**  %s  **\n%s" % (title, '\n'.join(body)))
        # mail
        for addr in self.config.mailto.split(':') :
            addr = addr.strip()
            if not addr : continue
            trace("sending mail report to '%s'" % addr)
            proc = cmdexec(["Mail", "-s", title, addr], stdin=CMDPIPE,
                           universal_newlines=True)
            proc.stdin.write('\n'.join(body))
            proc.stdin.write('\n')
            proc.stdin.close()
            r = proc.wait()
            assert r == 0, r


    # __setup_logger:
    #
    def __setup_logger (self) :
        logger = logging.getLogger('mbdump')
        logger.setLevel(1)
        # console handler
        chdlr = LogConsoleHandler(1)
        self.log_cfilter = LogLevelFilter()
        chdlr.addFilter(self.log_cfilter)
        logger.addHandler(chdlr)
        # set defaults from env vars
        self.log_cfilter.enable(logging.DEBUG, bool(os.environ.get('MB_DEBUG')))
        self.log_cfilter.enable(logging.INFO, bool(os.environ.get('MB_VERBOSE')))


    # __open_logfile:
    #
    def __open_logfile (self) :
        logger = logging.getLogger('mbdump')
        n, sfx = 0, ''
        while True :
            logfile = os.path.join(self.config.logdir, 'mbdump.%s.%s%s.log' %
                                   (self.config.cfgname, self.config.start_hrs, sfx))
            try:
                fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                n += 1
                sfx = '.%d' % n
                continue
            os.close(fd)
            break
        fhdlr = logging.FileHandler(logfile)
        fhdlr.setLevel(1)
        logger.addHandler(fhdlr)


    # __select_disks:
    #
    def __select_disks (self, args) :
        if args :
            disklist = [self.config.disks[d] for d in args]
        else :
            disklist = list(self.config.disks.values())
        sched = []
        for disk in disklist :
            dump = self.db.select_last_dump(disk)
            if dump is None :
                trace("%s: no last dump found, selected" % disk)
            else :
                hrs = self.db.select_run(dump.runid).hrs
                # [TODO]
                if hrs[:8] > self.config.start_hrs[:8] :
                    error("%s: last dump is in the future!!" % disk.name)
                    # force run ?
                    continue
                elif hrs[:8] < self.config.start_hrs[:8] :
                    trace("%s: last dump older than 1 day, selected" % disk.name)
                else :
                    trace("%s: already dumped today, skipped" % disk.name)
                    continue
            sched.append(DumpSched(disk=disk.name, cfgdisk=disk))
        return sched


    # __process:
    #
    def __process (self, sched) :
        # record the run now so we get a runid
        self.runid = self.db.record_run(self.config.start_hrs)
        # open the journal
        self.journal = Journal(self.config.journalfile, 'w')
        self.journal.record('START', config=self.config.cfgname, runid=self.runid, hrs=self.config.start_hrs)
        self.journal.record('SELECT', disks=','.join(s.disk for s in sched))
        # schedule the dumps
        for dsched in sched :
            dsched.cfgdisk.run_hooks('schedule', self.journal)
        for dsched in sched :
            self.__schedule_dump(dsched)
        # run
        for dsched in sched :
            self.__process_dump(dsched)


    # __schedule_dump:
    #
    def __schedule_dump (self, dsched) :
        trace("schedule %s" % dsched)
        cycle = self.db.get_current_cycle(dsched.disk)
        trace("current cycle: %d dumps:" % len(cycle))
        for d in cycle : trace(" - %s" % repr(d))
        if cycle :
            estims = [self.__estim_dump(dsched, None)]
            estims.extend(self.__estim_dump(dsched, d)
                          for d in cycle)
            select = None
            for e in estims :
                if select is None or select.est > e.est :
                    select = e
            trace("selected best estimate: %s" % repr(select))
            dsched.update(prevrun=select.prev)
        else :
            trace("no cycle found, forcing full dump")
            dsched.update(prevrun=0)
            
        self.journal.record('SCHEDULE', disk=dsched.disk, prevrun=dsched.prevrun)


    # __estim_dump:
    #
    def __estim_dump (self, dsched, prev) :
        trace("[TODO] estim(%s, %s)" % (dsched.disk, prev))
        prevrun = (0 if prev is None else prev.runid)
        return DumpEstimate(prev=prevrun, raw=100, comp=100, est=prevrun*10)
            

    # __process_dump:
    #
    def __process_dump (self, dsched) :
        trace("process: %s" % dsched)
        # make a filename
        destbase = 'mbdump.%s.%s.%s' % (self.config.cfgname, dsched.disk,
                                        self.config.start_hrs)
        destext = dsched.cfgdisk.get_dumpext() + '.part'
        destfull = os.path.join(self.config.partdir, destbase+destext)
        # instantiate a dumper
        dumper = dsched.cfgdisk.get_dumper()
        # looks like we're ready
        self.journal.record('DUMP-START', disk=dsched.disk, fname=destbase+destext)
        procs = []
        pipes = []
        # open dest file and index
        fdest = open(destfull, 'wb')
        index = Index('/dev/null')
        # filters
        filters = [cmdexec(['gzip'], stdin=CMDPIPE, stdout=CMDPIPE)]
        # start the dumper
        proc_dump = dumper.start(dsched.cfgdisk.path)
        procs.append(proc_dump)
        p_dump = PipeThread('dumper', proc_dump.stdout, ())
        pipes.append(p_dump)
        # start the index
        proc_index = dumper.start_index()
        procs.append(proc_index)
        p_dump.plug_output(proc_index.stdin)
        p_index = PipeThread('index', proc_index.stdout, (), line_handler=index)
        pipes.append(p_index)
        # plug the filters
        data_plug = p_dump
        for n, filt in enumerate(filters) :
            data_plug.plug_output(filt.stdin)
            data_plug = PipeThread('filter[%d]' % n, filt.stdout, ())
            procs.append(filt)
            pipes.append(data_plug)
        # plug output
        data_plug.plug_output(fdest)
        # start all pipes
        for p in pipes :
            p.start()
        # then wait...
        for p in pipes :
            p.join()
            #trace("%s: OK (%d bytes)" % (p.name, p.data_size))
        # wait processes
        for p in procs :
            #trace("wait proc: %s" % p)
            r = p.wait()
            #trace("process %d: %s" % (p.pid, r))
            assert r == 0, r # [todo]
        # close files
        fdest.close()
        index.close()
        # collect datas about the dump
        raw_size = p_dump.data_size
        comp_size = data_plug.data_size
        nfiles = index.count
        # all done
        self.journal.record('DUMP-FINISHED',
                            disk=dsched.disk, state='ok',
                            raw_size=raw_size, comp_size=comp_size,
                            nfiles=nfiles)
        trace("dump OK: %s (%s/%s, %d files)" % (dsched.disk,
                                                 human_size(raw_size),
                                                 human_size(comp_size),
                                                 nfiles))


    # __post_process:
    #
    def __post_process (self, info) :
        info = self.journal.summary()
        trace("[TODO] post process:\n%s" % repr(info))
        # process the dumps
        for dump in info.dumps.values() :
            cfgdisk = self.config.disks[dump.disk]
            # rename the dump file
            destbase = cfgdisk.get_dumpname(runid=info.runid, level=9,
                                            prevrun=dump.prevrun, hrs=info.hrs)
            destext = cfgdisk.get_dumpext()
            destfull = os.path.join(self.config.dumpdir, destbase+destext)
            partfull = os.path.join(self.config.partdir, dump.fname)
            trace("dump: '%s' -> '%s'" % (partfull, destfull))
            os.rename(partfull, destfull)
            # record the dump in db
            self.db.record_dump(disk=cfgdisk.name, runid=info.runid,
                                prevrun=dump.prevrun, state=dump.state,
                                fname=destbase+destext, raw_size=dump.raw_size,
                                comp_size=dump.comp_size, nfiles=dump.nfiles)
        # debug
        self.db.dump()


    # __report:
    #
    def __report (self, info, width=70) :
        title = self.__report_title(info)

        header = ['HEADER']

        # dumps table
        dumps = [l.center(70) for l in self.__report_dumps(info)]

        body = header + dumps
        return title, body


    # __report_dumps:
    #
    def __report_dumps (self, info) :
        cols = self.__parse_columns(self.config.report_columns)                
        table = asciitable.Table(len(info.dumps)+3, len(cols),
                                 vpad=0, hpad=1)
        table.set_vpad(0, 1)
        table.set_vpad(1, 1)
        table.set_vpad(2, 1)
        table.set_vpad(len(info.dumps)+2, 1)
        table.set_vpad(len(info.dumps)+3, 1)
        # table title
        table_title = 'DUMP RUN %04d' % info.runid
        table.add(table_title, 0, 0, 1, len(cols),
                  frame=asciitable.Frame.FULL, justify='center',)
        # column titles
        for col, (title, cfmt, kwargs) in enumerate(cols) :
            table.add(title, 1, col, margins=(0, 1, 0, 1),
                      frame=asciitable.Frame.FULL, justify='center')
        # dump lines
        nfiles_total, raw_total, comp_total = 0, 0, 0
        for row, (disk, dump) in enumerate(info.dumps.items()) :
            nfiles_total += dump.nfiles
            raw_total += dump.raw_size
            comp_total += dump.comp_size
            for col, (t, cfmt, kwargs) in enumerate(cols) :
                table.add(cfmt % dump, row+2, col,
                          frame=asciitable.Frame.LR, **kwargs)
        # total lines (if more than one dump)
        if len(info.dumps) > 1 :
            attr_total = {'disk': '',
                          'state': '',
                          'nfiles': nfiles_total,
                          'raw_size': raw_total,
                          'raw_hsize': human_size(raw_total),
                          'comp_size': comp_total,
                          'comp_hsize': human_size(comp_total),
                          'comp_ratio': comp_total * 100.0 / raw_total}
            for col, (t, f, k) in enumerate(cols) :
                text = (f % attr_total).strip()
                table.add(text, row+3, col,
                          frame=asciitable.Frame.FULL, **k)
        # ok
        return table.getlines(debug=0)


    # __parse_columns:
    #
    def __parse_columns (self, colspecs) :
        cols = []
        for cspec in colspecs :
            #trace("CSPEC: '%s'" % cspec)
            title = ''
            kwargs = {}
            while cspec and cspec[0] == "\\" :
                end = cspec.find("\\", 1)
                if end < 0 :
                    cspec = cspec[1:]
                    break
                attr = cspec[1:end]
                cspec = cspec[end:]
                eq = attr.find('=')
                if eq >= 0 :
                    atname, atval = attr[:eq], attr[eq+1:]
                else :
                    atname, atval = attr, ''
                if atname == 'title' :
                    title = atval
                elif atname == 'left' :
                    kwargs['justify'] = left
                elif atname == 'right' :
                    kwargs['justify'] = 'right'
                elif atname == 'center' :
                    kwargs['justify'] = 'center'
                else :
                    assert 0, (atname, atval)
            cols.append((title, cspec, kwargs))
            #trace(" -> %s" % repr(cols[-1]))
        return cols
        

    # __report_title:
    #
    def __report_title (self, info) :
        mark = '--'
        title = "%(package)s '%(config)s' REPORT %(status_mark)s %(date)s" \
          % {'package': self.config.system.PACKAGE.upper(),
             'config': info.config,
             'status_mark': mark,
             'date': hrs2date(info.hrs)}
        return title


# exec
if __name__ == '__main__' :
    app = MBDumpApp()
    app.main()
