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
        '_OPEN': (('tool', 'str'),
                  ('hrs', 'hrs'),
                  ('mode', 'str')),

        '_CLOSE': (('tool', 'str'),
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
                          ('nfiles',    'int'),
                          ('hashtype', 'str'),
                          ('hashsum', 'str')),

        'DUMP-ABORT': (('disk', 'str'),),

        'STRANGE': (('source', 'str'),
                    ('message', 'str')),

        'NOTE': (('message', 'str'),),

        'WARNING': (('message', 'str'),),

        'ERROR': (('message', 'str'),),

        'USER-MESSAGE': (('level', 'int'),
                         ('message', 'str')),

        # mbclean only
        'CLEAN-START': (('hrs', 'hrs'),),

        'CLEAN-END': (('hrs', 'hrs'),),

        'CLEAN-PANIC': (('message', 'str'),),

        'DUMP-FIX': (('disk', 'str'),
                     ('state', 'dumpstate'),
                     ('hashsum', 'str')),
    }


    KEYTYPES = dict((n, namedtuple('JournalKey_'+n.replace('-', '_'),
                                   ('key',) + tuple(p[0] for p in kspecs)))
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
    def __init__ (self, fname, mode, tool_name, lockfile) :
        self.lockfile = lockfile
        self.tlock = threading.Lock() # useless ?
        self.fname = fname
        self.mode = mode
        self.tool_name = tool_name
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
            self.record('_OPEN', tool=self.tool_name, hrs=stamp2hrs(int(time.time())), mode='w')
        elif self.mode == 'a' :
            trace("opening journal '%s' for (append) writing" % self.fname)
            with self.flock :
                self.__read_file()
            # captures all log errors and warnings
            self.__install_log_handler()
            self.record('_OPEN', tool=self.tool_name, hrs=stamp2hrs(int(time.time())), mode='a')
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


    # get_state:
    #
    def get_state (self) :
        with self.tlock :
            return self.state2[:]


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
            self.record('_CLOSE', tool=self.tool_name, hrs=stamp2hrs(int(time.time())))
        with self.tlock :
            self.__open = False
            if self.log_handler is not None :
                logger = logging.getLogger(log_domain())
                logger.removeHandler(self.log_handler)
                self.log_handler = None


    # delete:
    #
    def delete (self) :
        warning("[FIXME] Journal.delete()")
        os.unlink(self.fname)

        
    # roll:
    #
    # [FIXME] we should have a 'closed' flag to make sure we don't
    # read/write after a roll!
    #
    def roll (self, dirname, sfx) :
        assert sfx
        with self.flock :
            self.__roll(dirname, sfx)


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
                self.__read_line2(line)
            except Exception:
                exception("%s:%d: invalid journal line: '%s'" %
                          (fname, lno+1, line))
                continue

    def __read_line2 (self, line) :
        trace("<< `%s'" % line)
        argv = line.split(':')
        key = argv.pop(0)
        kspec = Journal.KEYSPECS[key]
        assert len(argv) == len(kspec), (key, argv)
        kw = {}
        for i, (pname, ptype) in enumerate(kspec) :
            kw[pname] = self.adapt(ptype, argv[i])
        entry = self.make_entry(key, kw)
        self.__update2(entry)
        
        trace(">> %s" % ', '.join("`%s'" % w for w in argv))


    # __roll:
    #
    def __roll (self, dirname, sfx) :
        self.close()
        # first make sure the dest is OK
        base, ext = os.path.splitext(os.path.basename(self.fname))
        dest = os.path.join(dirname, base + sfx + ext)
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


    # record:
    #
    def record (self, key, **kwargs) :
        assert self.mode in ('w', 'a')
        assert self.isopen()
        with self.flock :
            self.__record(key, **kwargs)

    def __record (self, key, **kwargs) :
        entry = self.make_entry(key, kwargs)
        self.__update2(entry)
        # write file
        line = [key] + list(Journal.convert(ptype, getattr(entry, pname))
                            for pname, ptype in Journal.KEYSPECS[key])
        trace("JOURNAL: %s" % line)
        # atomic update - [fixme] looks ugly but i don't know a better
        # way ; maybe the file should be chunked if it becomes too big
        # ?
        tmp = self.fname + '.tmp'
        f = open(tmp, 'wt')
        # file must exist!
        f.write(open(self.fname, 'rt').read())
        f.write(':'.join(line))
        f.write('\n')
        f.flush()
        os.fsync(f.fileno()) # fdatasync ?
        f.close()
        os.rename(tmp, self.fname)


    def __update2 (self, entry) :
        with self.tlock :
            if entry.key == '_OPEN' :
                if self.curss is not None :
                    trace("journal: session was not closed: %s" % repr(self.curss[0]))
                self.curss = [entry]
                self.state2.append(self.curss)
            elif entry.key == '_CLOSE' :
                assert self.curss is not None
                assert self.curss[0].tool == entry.tool
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


    # make_entry:
    #
    def make_entry (self, key, kwargs) :
        #kwargs = copy.deepcopy(kwargs) # [fixme] ?
        kspec = Journal.KEYSPECS[key]
        assert len(kspec) == len(kwargs), kwargs
        ktype = Journal.KEYTYPES[key]
        for pname, ptype in kspec :
            self.convert(ptype, kwargs[pname]) # [fixme] just to check validity
        return ktype(key=key, **kwargs)
