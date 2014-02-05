# log.py - logging tools

__all__ = [
    'log_setup',
    'trace',
]

import sys, threading


# just in case, log_setup is thread-locked
_log_setup_lock = threading.Lock()

_DOMAIN = '<notset>'
_setup_done = False


# log_setup:
#
def log_setup (domain) :
    global _DOMAIN, _setup_done
    with _log_setup_lock :
        assert not _setup_done, _DOMAIN
        _setup_done = True
        _DOMAIN = domain


# trace:
#
def trace (msg) :
    sys.stderr.write("%s: %s\n" % (_DOMAIN, msg))
    
