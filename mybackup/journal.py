# journal.py - operations journalization

__all__ = [
    'Journal',
]

import logging
from collections import namedtuple

from mybackup.base import *
from mybackup.log import *


# Errors:
#
class JournalNotFoundError (Exception) :
    def __init__ (self, fname) :
        Exception.__init__(self, "journal file not found: '%s'" % fname)

class JournalRollError (Exception) :
    pass

        
# JournalState:
#
_JournalState = attrdict (
    '_JournalState', 
    (),
    defo={'hrs': 'X',
          'endhrs': 'X',
          'config': '',
          'state': 'init',
          'dumps': {},
          'notes': [],
          'stranges': [],
          'warnings': [],
          'errors': [],
          'postprocs': [],
          'current_postproc': None})


class JournalState (_JournalState) :
    nstranges = property(lambda s: len(s.stranges))
    nwarnings = property(lambda s: len(s.warnings))
    nerrors = property(lambda s: len(s.errors))
    

# DumpInfo:
#
_DumpInfo = attrdict (
    '_DumpInfo',
    (),
    defo={'state': DumpState.SELECTED,
          'prevrun': -1,
          'raw_size': -1,
          'comp_size': -1,
          'nfiles': -1,
          'fname': ''})

class DumpInfo (_DumpInfo) :
    upstate = property(lambda s: DumpState.tostr(s.state).upper())
    raw_hsize = property(lambda s: human_size(s.raw_size))
    comp_hsize = property(lambda s: human_size(s.comp_size))
    comp_ratio = property(lambda s: (s.comp_size * 100.0 / s.raw_size)
                          if s.raw_size > 0 else 0.0)


# PostProcInfo:
#
PostProcInfo = attrdict(
    'PostProcInfo',
    (),defo={'hrs': 'X',
             'endhrs': 'X',
             'panics': []})



# LogJournalHandler:
#
# [FIXME] very strange
#
class LogJournalHandler (LogBaseHandler) :


    KEYMAP = {
        logging.WARNING:  'WARNING',
        logging.ERROR:    'ERROR',
        logging.CRITICAL: 'ERROR',
    }

    
    # __init__:
    #
    def __init__ (self, journal) :
        LogBaseHandler.__init__(self, 1)
        self.addFilter(LogLevelFilter((logging.WARNING,
                                       logging.ERROR,
                                       logging.CRITICAL)))
        self.journal = weakref.ref(journal, self._notify)
        self.frozen = False


    def _notify (self, *args) :
        pass #assert 0, args


    # emit:
    #
    def emit (self, rec) :
        j = self.journal()
        if j is None :
            return
        if not j.isopen() :
            assert 0
        key = LogJournalHandler.KEYMAP[rec.levelno]
        j.record(key, message=rec.message)


# Journal:
#
class Journal :


    KEYSPECS = {
        '_OPEN': (('app', 'str'),
                  ('hrs', 'hrs'),
                  ('mode', 'str')),

        '_CLOSE': (('app', 'str'),
                   ('hrs', 'hrs')),
                  
        'START':  (('config', 'str'),
                   ('runid',  'uint'),
                   ('hrs',    'hrs')),

        'END': (('hrs', 'hrs'),),
                   
        'SELECT': (('disks', 'str'),),

        'SCHEDULE': (('disk',    'str'),
                     ('prevrun', 'int')),

        'DUMP-START':    (('disk',  'str'),
                          ('fname', 'str')),
        
        'DUMP-FINISHED': (('disk',  'str'),
                          ('state', 'dumpstate'),
                          ('raw_size', 'int'),
                          ('comp_size', 'int'),
                          ('nfiles',    'int')),

        'STRANGE': (('source', 'str'),
                    ('line', 'str')),

        'WARNING': (('message', 'str'),),

        'ERROR': (('message', 'str'),),

        # mbclean only
        'CLEAN-START': (('hrs', 'hrs'),),

        'CLEAN-END': (('hrs', 'hrs'),),

        'CLEAN-PANIC': (('message', 'str'),),

        'DUMP-FIX': (('disk', 'str'),
                     ('state', 'dumpstate')),
    }


    KEYTYPES = dict((n, namedtuple('JournalKey_'+n.replace('-', '_'),
                                   tuple(p[0] for p in kspecs)))
                    for n, kspecs in KEYSPECS.items())


    flock = property(lambda s: FLock(s.lockfile))


    # adapt:
    #
    # Adapt a string value to the type 't'.
    #
    @staticmethod
    def adapt (t, v) :
        assert isinstance(v, str), v
        u = Journal.__unescape(v)
        n = '_Journal__adapt_' + t
        h = getattr(Journal, n)
        return h(u)


    # convert:
    #
    # Convert a type 't' instance to a string
    #
    @staticmethod
    def convert (t, v) :
        n = '_Journal__convert_' + t
        h = getattr(Journal, n)
        r = h(v)
        assert isinstance(r, str), v
        return Journal.__escape(r)


    # converters:
    #
    @staticmethod
    def __adapt_str (v) :
        return v
    
    @staticmethod
    def __convert_str (v) :
        assert isinstance(v, str), v
        return v

    @staticmethod
    def __adapt_int (v) :
        return int(v)

    @staticmethod
    def __convert_int (v) :
        assert isinstance(v, int), v
        return str(v)

    @staticmethod
    def __adapt_uint (v) :
        r = int(v)
        assert r > 0, v
        return r

    @staticmethod
    def __convert_uint (v) :
        assert isinstance(v, int), v
        assert v > 0, v
        return str(v)

    @staticmethod
    def __adapt_hrs (v) :
        return check_hrs(v)

    @staticmethod
    def __convert_hrs (v) :
        return check_hrs(v)

    @staticmethod
    def __adapt_dumpstate (v) :
        return DumpState.tostr(v)

    @staticmethod
    def __convert_dumpstate (v) :
        return DumpState.tostr(v)


    # (un)escaping:
    #
    @staticmethod
    def __escape (line) :
        chars = "\\:\n"
        out = ''
        for c in line :
            if c in chars :
                out += "\\x%02x" % ord(c)
            else :
                out += c
        return out

    @staticmethod
    def __unescape (line) :
        out, pos = '', 0
        while True :
            i = line.find("\\", pos)
            if i < 0 :
                out += line[pos:]
                return out
            out += line[pos:i]
            assert line[i+1] == 'x'
            char = int(line[i+2:i+4], 16)
            out += chr(char)
            pos = i + 4


    # __init__:
    #
    # [FIXME] LOCKING IS WRONG!
    #
    def __init__ (self, fname, mode, app_name, lockfile, skip_postproc=False) :
        self.lockfile = lockfile
        self.tlock = threading.Lock() # useless ?
        self.fname = fname
        self.mode = mode
        self.app_name = app_name
        self.skip_postproc = skip_postproc
        self.log_handler = None
        self.__open = False
        self.__doopen()


    def __del__ (self) :
        #sys.stderr.write("Journal.__del__(%s)\n" % self)
        self.close()


    # __doopen:
    #
    def __doopen (self) :
        logger = logging.getLogger(log_domain())
        assert not self.isopen()
        self.state = JournalState()
        self.__open = True
        # new style
        self.state2 = []
        self.curss = None
        #
        if self.mode == 'w' :
            # [FIXME] !!
            trace("opening journal '%s' for writing" % self.fname)
            with self.flock :
                fd = os.open(self.fname, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                os.close(fd)
            # captures all log errors and warnings
            self.__install_log_handler()
            # record open
            self.record('_OPEN', app=self.app_name, hrs=stamp2hrs(int(time.time())), mode='w')
        elif self.mode == 'a' :
            trace("opening journal '%s' for (append) writing" % self.fname)
            with self.flock :
                self.__read_file()
            # captures all log errors and warnings
            self.__install_log_handler()
            self.record('_OPEN', app=self.app_name, hrs=stamp2hrs(int(time.time())), mode='a')
        elif self.mode == 'r' :
            with self.flock :
                self.__read_file()
            self.__open = False # ?
        else :
            assert 0, self.mode


    # __install_log_handler:
    #
    def __install_log_handler (self) :
        assert self.log_handler is None
        self.log_handler = LogJournalHandler(self)
        logger = logging.getLogger(log_domain())
        logger.addHandler(self.log_handler)


    # isopen:
    #
    def isopen (self) :
        with self.tlock :
            return self.__open


    # reopen:
    #
    def reopen (self, mode, skip_postproc=False) :
        self.close()
        self.mode = mode
        self.skip_postproc = skip_postproc
        self.__doopen()


    # close:
    #
    def close (self) :
        # [FIXME] bad bad bad
        if self.isopen() :
            self.record('_CLOSE', app=self.app_name, hrs=stamp2hrs(int(time.time())))
        with self.tlock :
            self.__open = False
            if self.log_handler is not None :
                logger = logging.getLogger(log_domain())
                logger.removeHandler(self.log_handler)
                self.log_handler = None


    # summary:
    #
    def summary (self) :
        with self.tlock :
            return copy.deepcopy(self.state)


    # roll:
    #
    # [FIXME] we should have a 'closed' flag to make sure we don't
    # read/write after a roll!
    #
    def roll (self, dirname, hrs) :
        with self.flock :
            self.__roll(dirname, hrs)


    # __read_file:
    #
    def __read_file (self) :
        try:
            f = open(self.fname, 'rt')
        except FileNotFoundError:
            raise JournalNotFoundError(self.fname)
        try:
            self.__read(f, self.fname)
        finally:
            f.close()


    # __read:
    #
    def __read (self, f, fname) :
        trace("parsing journal lines")
        for lno, line in enumerate(f) :
            line = line.strip()
            if not line : continue
            try:
                self.__read_line(line)
            except Exception:
                exception("%s:%d: invalid journal line: '%s'" %
                          (fname, lno+1, line))
                continue

    def __read_line (self, line) :
        trace("<< `%s'" % line)
        argv = line.split(':')
        trace(">> %s" % ', '.join("`%s'" % w for w in argv))
        key = argv.pop(0)
        kspecs = Journal.KEYSPECS[key]
        assert len(argv) == len(kspecs), (key, argv)
        kwargs = {}
        for i, (pname, ptype) in enumerate(kspecs) :
            kwargs[pname] = self.adapt(ptype, argv[i])
        self.__update(key, kwargs)


    # __roll:
    #
    def __roll (self, dirname, hrs) :
        self.close()
        # first make sure the dest is OK
        base, ext = os.path.splitext(os.path.basename(self.fname))
        dest = os.path.join(dirname, base + '.' + hrs + ext)
        trace("rolling journal to '%s'" % dest)
        try:
            fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            # it can exist but must be empty
            st = os.stat(dest)
            if not (stat.S_ISREG(st.st_mode) and st.st_size == 0) :
                msg = ("could not roll journal '%s' : " +
                       "file '%s' exists and is not empty!") \
                       % (self.fname, dest)
                raise JournalRollError(msg)
        else:
            os.close(fd)
        # ok, go
        self.close()
        os.rename(self.fname, dest)


    # __update:
    #
    def __update (self, key, kw) :
        s = self.state
        # skip postproc messages
        if key != 'CLEAN-END' and self.skip_postproc and s.current_postproc is not None :
            # trace ?
            return
        # choose your key
        if key == '_OPEN' :
            info("[TODO] JOURNAL OPEN: %s" % repr(kw))
        elif key == '_CLOSE' :
            info("[TODO] JOURNAL CLOSE: %s" % repr(kw))
        elif key == 'START' :
            s.update(state='started',
                     config=kw['config'],
                     runid=kw['runid'],
                     hrs=kw['hrs'])
        elif key == 'END' :
            s.update(endhrs=kw['hrs'])
        elif key == 'SELECT' :
            for d in kw['disks'].split(',') :
                s.dumps[d] = DumpInfo(disk=d)
        elif key == 'SCHEDULE' :
            s.dumps[kw['disk']].update(state=DumpState._SCHEDULED,
                                       prevrun=kw['prevrun'])
        elif key == 'DUMP-START' :
            s.dumps[kw['disk']].update(state=DumpState._STARTED,
                                       fname=kw['fname'])
        elif key == 'DUMP-FINISHED' :
            s.dumps[kw['disk']].update(state=kw['state'],
                                       raw_size=kw['raw_size'],
                                       comp_size=kw['comp_size'],
                                       nfiles=kw['nfiles'])
        elif key == 'STRANGE' :
            s.stranges.append((kw['source'], kw['line']))
        elif key == 'WARNING' :
            s.warnings.append((kw['message'],))
        elif key == 'ERROR' :
            s.errors.append((kw['message'],))
        elif key == 'CLEAN-START' :
            assert kw['hrs'] not in s.postprocs
            pp = PostProcInfo(hrs=kw['hrs'])
            s.postprocs.append(pp)
            s.current_postproc = pp
        elif key == 'CLEAN-END' :
            assert s.current_postproc is not None
            s.current_postproc.update(endhrs=kw['hrs'])
            s.current_postproc = None
        elif key == 'DUMP-FIX' :
            assert s.current_postproc is not None
        else :
            assert 0, (key, kw)
        # trace("JOURNAL UPDATE: %s\n%s" %
        #       (key, pprint.pformat(s.asdict())))


    # record:
    #
    def record (self, key, **kwargs) :
        assert self.mode in ('w', 'a')
        assert self.isopen()
        with self.flock :
            self.__record(key, **kwargs)

    def __record (self, key, **kwargs) :
        entry = self.make_entry(key, kwargs)
        # [removeme]
        self.__oldrecord(key, kwargs)
        #
        if key == '_OPEN' :
            if self.curss is not None :
                trace("journal: session was not closed: %s" % repr(self.curss[0]))
            self.curss = [entry]
            self.state2.append(self.curss)
        elif key == '_CLOSE' :
            assert self.curss is not None
            assert self.curss[0].app == entry.app
            self.curss = None
        else :
            assert self.curss is not None
            self.curss.append(entry)


    # [removeme]
    def __oldrecord (self, key, kwargs) :
        keyspec = Journal.KEYSPECS[key]
        assert len(kwargs) == len(keyspec), kwargs
        line = [key]
        for pname, ptype in keyspec :
            pval = Journal.convert(ptype, kwargs[pname])
            line.append(pval)
        # the new session handler
        # update state
        self.__update(key, kwargs)
        # write
        # [FIXME] probably some sync needed here
        trace("JOURNAL:%s: %s" % (key, ', '.join("'%s'" % w for w in line[1:])))
        tmp = self.fname + '.tmp'
        f = open(tmp, 'wt')
        # file must exist!
        f.write(open(self.fname, 'rt').read())
        f.write(':'.join(line))
        f.write('\n')
        f.flush()
        f.close()
        os.rename(tmp, self.fname)


    # make_entry:
    #
    def make_entry (self, key, kwargs) :
        kwargs = copy.deepcopy(kwargs) # [fixme] ?
        kspec = Journal.KEYSPECS[key]
        assert len(kspec) == len(kwargs), kwargs
        ktype = Journal.KEYTYPES[key]
        for pname, ptype in kspec :
            kwargs[pname] = self.convert(ptype, kwargs[pname])
        return ktype(**kwargs)
