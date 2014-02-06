# log.py - logging tools

__all__ = [
    'log_setup',
    'log_domain',
    'trace',
    'info',
    'warning',
    'error',
    'critical',
    'exception',
    'LogLevelFilter',
    'LogFormatter',
    'LogBaseHandler',
    'LogConsoleHandler',
]

import sys, os, threading, logging, collections, traceback

from mybackup.base import *


# just in case, log_setup is thread-locked
_log_setup_lock = threading.Lock()

_DOMAIN = '<notset>'
_setup_done = False


# log_domain:
#
def log_domain () :
    return _DOMAIN


# log_setup:
#
def log_setup (domain) :
    global _DOMAIN, _setup_done
    with _log_setup_lock :
        assert not _setup_done, _DOMAIN
        _setup_done = True
        _DOMAIN = domain
        logger = logging.getLogger(_DOMAIN)
        logger.setLevel(1)
        logger.addFilter(_LogGlobalFilter())
        return logger


# log funcs:
#
_log_locations = bool(os.environ.get('MB_LOG_LOCATIONS', ''))

def _log (lvl, msg, depth=0, exc_info=None) :
    logger = logging.getLogger(_DOMAIN)
    fn, ln, fc, co = traceback.extract_stack()[-(depth+2)]
    fn = os.path.realpath(fn)
    r = logger.makeRecord(_DOMAIN, lvl, fn=fn, lno=ln,
                          msg=msg, args=(), exc_info=exc_info,
                          func=fn, extra=None, sinfo=None)
    logger.handle(r)
        
def trace (msg, depth=0, **kw) :   _log(logging.DEBUG, msg, depth=depth+1, **kw)
def info  (msg, depth=0, **kw) :   _log(logging.INFO,  msg, depth=depth+1, **kw)
def warning (msg, depth=0, **kw) : _log(logging.WARNING, msg, depth=depth+1, **kw)
def error (msg, depth=0, **kw) :   _log(logging.ERROR, msg, depth=depth+1, **kw)
def critical (msg, depth=0, **kw) :   _log(logging.CRITICAL, msg, depth=depth+1, **kw)
def exception (msg, depth=0, **kw) : critical(msg, depth=depth+1, exc_info=sys.exc_info(), **kw)


# _LOG_LEVEL_INFO:
#
_LogLevelInfo = collections.namedtuple('_LogLevelInfo',
                                       ('err', 'sym'))
_LOG_LEVEL_INFO = {
    logging.DEBUG:    _LogLevelInfo(False, '..'),
    logging.INFO:     _LogLevelInfo(False, '--'),
    logging.WARNING:  _LogLevelInfo(True, 'WW'),
    logging.ERROR:    _LogLevelInfo(True, 'EE'),
    logging.CRITICAL: _LogLevelInfo(True, 'FF'),
}


# _LogGlobalFilter:
#
class _LogGlobalFilter :


    # __call__:
    #
    def __call__ (s, r) :
        setattr(r, 'levelsym', _LOG_LEVEL_INFO[r.levelno].sym)
        return True


# LogLevelFilter:
#
class LogLevelFilter :


    # __init__:
    #
    def __init__ (self, levels=None) :
        if levels is None :
            levels = (logging.DEBUG, logging.INFO, logging.WARNING,
                      logging.ERROR, logging.CRITICAL)
        self.levels = set(levels)


    # enable:
    #
    def enable (self, lvl, enab=True) :
        if enab :
            self.levels.add(lvl)
        else :
            self.levels.discard(lvl)
            
        
    # __call__:
    #
    def __call__ (self, rec) :
        return rec.levelno in self.levels


# LogFormatter:
#
class LogFormatter (logging.Formatter) :


    # formatException:
    #
    def formatException (self, exc_info) :
        return ''.join(format_exception(exc_info))


# LogBaseHandler:
#
# Base for all handlers we define in the app.
#
class LogBaseHandler (logging.Handler) :
    

    raiseExceptions = True


    # handleError:
    #
    def handleError (self, *args) :
        assert 0, args


# LogConsoleHandler:
#
class LogConsoleHandler (LogBaseHandler) :


    # __init__:
    #
    def __init__ (self) :
        LogBaseHandler.__init__(self)
        if os.environ.get('MB_LOG_LOCS', '') :
            cfmt = '%(name)s:%(filename)s:%(lineno)d:%(funcName)s:%(levelname)s: %(message)s'
        else :
            cfmt = '%(name)s:%(levelname)s: %(message)s'
        self.setFormatter(LogFormatter(cfmt))


    # emit:
    #
    def emit (self, r) :
        msg = self.format(r)
        f = sys.stderr if _LOG_LEVEL_INFO[r.levelno].err else sys.stdout
        f.write(msg)
        f.write('\n')
        f.flush()


    # handleError:
    #
    def handleError (self, rec) :
        sys.stderr.write("** ERROR IN LOG HANDLER : %s **\n" % rec)
        print_exception()
