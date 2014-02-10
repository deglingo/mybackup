#

# [FIXME]
# __all__ = [
#     'FLockError',
#     'FLock',
# ]

import sys, os, fcntl, time, threading, weakref, re, types, copy
import codecs, traceback
from functools import partial


# FLockError:
#
class FLockError (Exception) :
    pass


# FLock:
#
class FLock :

    def __init__ (self, fname, block=True, timeout=0, delay=0.1) :
        # i guess that one FLock instance should never be used from
        # different threads, so let's check for that
        self.thread = weakref.ref(threading.current_thread())
        self.fname = fname
        self.block = block
        self.timeout = timeout
        self.delay = delay
        self.fd = 0

    def __enter__ (self) :
        if threading.current_thread() is not self.thread() :
            assert 0, "FLock instances can't be shared by different threads!"
        self.fd = os.open(self.fname, os.O_WRONLY | os.O_CREAT)
        start = time.time()
        while True :
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if self.timeout > 0 and (time.time() - start) >= self.timeout :
                    raise FLockError("could not lock '%s' after %d seconds" %
                                     (self.fname, self.timeout))
                time.sleep(self.delay)
                continue
            break

    def __exit__ (self, tp, exc, tb) :
        if self.fd != 0 :
            os.close(self.fd)
        return False


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


# exc_name:
#
def exc_name (exc=None) :
    if exc is None :
        tp, exc, tb = sys.exc_info()
    else :
        tp = exc.__class__
    return "%s: %s" % (tp.__name__, exc)


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


# enum:
#
class enumbase :

    @classmethod
    def check (cls, v) :
        if isinstance(v, int) :
            assert v in cls.byvalue, v
        elif isinstance(v, str) :
            assert v in cls.byname, v
        else :
            assert 0, v
        return True

    @classmethod
    def toint (cls, v) :
        if isinstance(v, int) :
            assert v in cls.byvalue, v
            return v
        elif isinstance(v, str) :
            assert v in cls.byname, v
            return cls.byname[v]
        else :
            assert 0, v

    @classmethod
    def tostr (cls, v, up=False) :
        if isinstance(v, int) :
            assert v in cls.byvalue, v
            v = cls.byvalue[v]
        elif isinstance(v, str) :
            v = v.lower()
            assert v in cls.byname, v
        else :
            assert 0, v
        return v.upper() if up else v

    @classmethod
    def cmp (cls, v, *a) :
        v = cls.toint(v)
        for v2 in a :
            if v == cls.toint(v2) :
                return True
        return False

        
def enum (tpname, fields) :
    byname, byvalue = {}, {}
    tpdict = {'byname': types.MappingProxyType(byname),
              'byvalue': types.MappingProxyType(byvalue)}
    for value, name in enumerate(fields) :
        byname[name] = value
        byvalue[value] = name
        uname = name.upper()
        tpdict[uname] = value
        tpdict['_'+uname] = name
    tp = type(tpname, (enumbase,), tpdict)
    return tp

    
# DumpState:
#
_DumpState = enum(
    '_DumpState',
    ('none', 'ok', 'partial', 'failed', 'broken',
     'selected', 'scheduled', 'started', 'empty'))

class DumpState (_DumpState) :

    @staticmethod
    def adapt (*args) :
        assert 0, args

    @staticmethod
    def convert (value) :
        # [fixme] is it normal to get bytes objects from sq3 ?
        return DumpState.tostr(value.decode())


# Plural forms handling
#
_plurals = {
    'dump': 'dumps',
    'DUMP': 'DUMPS',
    'error': 'errors',
    'warning': 'warnings',
    'strange line': 'strange lines',
}

def plural_register (single, plural) :
    assert single not in _plurals
    _plurals[single] = plural

def plural (n, single, plural=None, addn=True) :
    if plural is None :
        # [FIXME] be kind and only report an error if not found
        plural = _plurals[single]
    # [FIXME] does 'plural' mean >1 or !=1 ?
    if n > 1 :
        text = plural
    else :
        text = single
    if addn :
        text = '%d %s' % (n, text)
    return text


######################################################################



_JRunInfo = attrdict('_JRunInfo')
_JDumpInfo = attrdict('_JDumpInfo')

class JRunInfo (_JRunInfo) :

    def __init__ (self) :
        _JRunInfo.__init__(self,
                           config='X',
                           start_hrs='X',
                           end_hrs='X',
                           runid=0,
                           dumps={},
                           errors=[],
                           warnings=[],
                           stranges=[],
                           notes=[],
                           messages=[])

class JDumpInfo (_JDumpInfo) :

    def __init__ (self, disk) :
        _JDumpInfo.__init__(self,
                            disk=disk,
                            state='selected',
                            fname='',
                            prevrun=-1,
                            raw_size=-1,
                            comp_size=-1,
                            nfiles=-1,
                            nfixes=0)
    

# JState:
#
class JState :


    # analysis:
    #
    @staticmethod
    def analysis (state) :
        runinfo = JRunInfo()
        for session in state :
            op = session[0]
            assert op.key == '_OPEN', op
            if op.tool == 'dump' :
                JState._analysis_dump(runinfo, session)
            elif op.tool == 'clean' :
                JState._analysis_clean(runinfo, session)
            else :
                assert 0, op
        return runinfo

    @staticmethod
    def _analysis_dump (runinfo, ss) :
        for ent in ss[1:] :
            if ent.key == 'START' :
                assert runinfo.start_hrs == 'X'
                runinfo.update(config=ent.config, start_hrs=ent.hrs, runid=ent.runid)
            elif ent.key == 'SELECT' :
                runinfo.dumps = dict((n, JDumpInfo(disk=n))
                                     for n in ent.disks.split(','))
            elif ent.key == 'SCHEDULE' :
                assert runinfo.dumps[ent.disk].state == 'selected'
                runinfo.dumps[ent.disk].update(state='scheduled', prevrun=ent.prevrun)
            elif ent.key == 'DUMP-START' :
                assert runinfo.dumps[ent.disk].state == 'scheduled'
                runinfo.dumps[ent.disk].update(state='partial', fname=ent.fname)
            elif ent.key == 'DUMP-FINISHED' :
                assert runinfo.dumps[ent.disk].state == 'partial'
                runinfo.dumps[ent.disk].update(state=DumpState.tostr(ent.state),
                                               raw_size=ent.raw_size,
                                               comp_size=ent.comp_size,
                                               nfiles=ent.nfiles)
            elif ent.key == 'USER-MESSAGE' :
                runinfo.messages.append((ent.level, ent.message))
            elif ent.key == 'END' :
                assert runinfo.end_hrs == 'X'
                runinfo.update(end_hrs=ent.hrs)
            else :
                assert 0, ent


    # _analysis_clean:
    #
    @staticmethod
    def _analysis_clean (runinfo, ss) :
        for ent in ss[1:] :
            if ent.key == 'WARNING' :
                runinfo.warnings.append(ent.message)
            elif ent.key == 'DUMP-FIX' :
                dump = runinfo.dumps[ent.disk]
                if not DumpState.cmp(ent.state, 'none') :
                    dump.state = ent.state
                dump.nfixes += 1
            else :
                assert 0, ent
