# tools.py - |fixme] anything which needs logging should go here
# instead of base

__all__ = [
    'CMDPIPE',
    'cmdexec',
    'mkdir',
    'numbered_backup',
    'StrangeParser',
    'DumperTar',
]

import os, subprocess, shutil, re
CMDPIPE = subprocess.PIPE

from mybackup.log import *


# cmdexec:
#
def cmdexec (cmd, wait=False, check=True, depth=0, **kw) :
    cwd = kw.pop('cwd', None)
    if cwd is None : cwd = os.getcwd()
    trace("%s> %s" % (cwd, ' '.join(cmd)), depth=depth+1)
    proc = subprocess.Popen(cmd, cwd=cwd, **kw)
    trace("process %s running with pid %d" %
          (os.path.basename(cmd[0]), proc.pid))
    if not wait :
        return proc
    r = proc.wait()
    if check and r != 0 :
        assert 0, "[todo] process failed : %s (%s)" % (cmd[0], r)
    return r


# mkdir:
#
def mkdir (d) :
    if os.path.isdir(d) :
        return
    mkdir(os.path.dirname(d))
    #trace("creating directory '%s'" % d)
    os.mkdir(d)


# numbered_backup:
#
def numbered_backup (fname) :
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
        #trace("STRANGE:%s: %s" % (self.name, line))
        self.journal.record('STRANGE', source=self.name, line=line)


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
