#

__all__ = [
    'FLockError',
    'FLock',
]

import os, fcntl, time, threading, weakref


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
