# journal.py - operations journalization

__all__ = [
    'Journal',
]

import logging

from mybackup.base import *
from mybackup.log import *


# JournalState:
#
_JournalState = attrdict (
    '_JournalState', 
    (),
    defo={'hrs': 'X',
          'config': '',
          'state': 'init',
          'dumps': {},
          'stranges': [],
          'warnings': [],
          'errors': []})

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
          'nfiles': -1})

class DumpInfo (_DumpInfo) :
    raw_hsize = property(lambda s: human_size(s.raw_size))
    comp_hsize = property(lambda s: human_size(s.comp_size))
    comp_ratio = property(lambda s: (s.comp_size * 100.0 / s.raw_size)
                          if s.raw_size > 0 else 0.0)


# LogJournalHandler:
#
class LogJournalHandler (logging.Handler) :


    KEYMAP = {
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR',
        logging.CRITICAL: 'ERROR',
    }

    
    # __init__:
    #
    def __init__ (self, journal) :
        logging.Handler.__init__(self, 1)
        self.addFilter(LogLevelFilter((logging.WARNING,
                                       logging.ERROR,
                                       logging.CRITICAL)))
        self.journal = weakref.ref(journal, self._notify)


    def _notify (self, *args) :
        assert 0, args
        

    # emit:
    #
    def emit (self, rec) :
        j = self.journal()
        if j is None :
            assert 0
        key = LogJournalHandler.KEYMAP[rec.levelno]
        j.record(key, message=rec.message)


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

        'WARNING': (('message', 's'),),

        'ERROR': (('message', 's'),),
    }


    flock = property(lambda s: FLock(s.lockfile))

    
    # __init__:
    #
    def __init__ (self, fname, mode, lockfile, logger) :
        self.lockfile = lockfile
        self.fname = fname
        self.mode = mode
        self.state = JournalState()
        if mode == 'w' :
            # [FIXME] !!
            trace("opening journal '%s' for writing" % self.fname)
            with self.flock :
                fd = os.open(self.fname, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                os.close(fd)
            # captures all log errors and warnings
            logger.addHandler(LogJournalHandler(self))
        else :
            error("[TODO] read journal")


    # summary:
    #
    def summary (self) :
        return copy.deepcopy(self.state)


    # roll:
    #
    # [FIXME] we should have a 'closed' flag to make sure we don't
    # read/write after a roll!
    #
    def roll (self, dirname, hrs) :
        n, sfx = 0, ''
        base, ext = os.path.splitext(os.path.basename(self.fname))
        while True :
            dest = os.path.join(dirname, base + sfx + ext)
            try:
                fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                n += 1
                sfx = '.%d' % n
                continue
            os.close(fd)
            trace("rolling journal file: '%s'" % dest)
            os.rename(self.fname, dest)
            return


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
            s.dumps[kw['disk']].update(state=DumpState.SCHEDULED,
                                       prevrun=kw['prevrun'])
        elif key == 'DUMP-START' :
            s.dumps[kw['disk']].update(state=DumpState.STARTED,
                                       fname=kw['fname'])
        elif key == 'DUMP-FINISHED' :
            s.dumps[kw['disk']].update(state=DumpState.check(kw['state']),
                                       raw_size=kw['raw_size'],
                                       comp_size=kw['comp_size'],
                                       nfiles=kw['nfiles'])
        elif key == 'STRANGE' :
            s.stranges.append((kw['source'], kw['line']))
        elif key == 'WARNING' :
            s.warnings.append((kw['message'],))
        elif key == 'ERROR' :
            s.errors.append((kw['message'],))
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
        with self.flock :
            self.__record(key, **kwargs)

    def __record (self, key, **kwargs) :
        keyspec = Journal.KEYSPECS[key]
        assert len(kwargs) == len(keyspec), kwargs
        line = [key]
        for pname, ptype in keyspec :
            pval = kwargs[pname]
            if ptype == 's' :
                assert isinstance(pval, str), (key, pname, pval)
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
