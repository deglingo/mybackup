#

__all__ = [
    'FLockError',
    'FLock',
]

import os, fcntl, time


# FLockError:
#
class FLockError (Exception) :
    pass


# FLock:
#
class FLock :

    def __init__ (self, fname, block=True, timeout=0, delay=0.1) :
        self.fname = fname
        self.block = block
        self.timeout = timeout
        self.delay = delay
        self.fd = 0

    def __enter__ (self) :
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
