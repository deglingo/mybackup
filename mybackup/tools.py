# tools.py - |fixme] anything which needs logging should go here
# instead of base

__all__ = [
    'CMDPIPE',
    'cmdexec',
    'mkdir',
    'create_file_nc',
    'numbered_backup',
    'sendmail',
    'StrangeParser',
    'DumperTar',
]

import os, subprocess, shutil, re, threading, itertools
CMDPIPE = subprocess.PIPE

from mybackup.sysconf import SYSCONF
from mybackup.log import *


# cmdexec:
#
def cmdexec (cmd, wait=False, check=True, lang='', depth=0, **kw) :
    cwd = kw.pop('cwd', None)
    if cwd is None : cwd = os.getcwd()
    if lang is None : lang = os.environ.get('LANG', '')
    env = dict(kw.pop('env', os.environ))
    env['LANG'] = lang
    trace("%s> %s" % (cwd, ' '.join(cmd)), depth=depth+1)
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, **kw)
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


# create_file_nc:
#
# Create a file with the noclobber flag, trying numbered variations
# until it succeeds. Returns the filename.
#
def create_file_nc (dirname, base, ext) :
    n, sfx = 0, ''
    while True :
        fname = os.path.join(dirname, base + sfx + ext)
        try:
            fd = os.open(fname, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            n += 1
            sfx = '.%d' % n
            continue
        os.close(fd)
        return fname


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


# sendmail:
#
def sendmail (addrs, subject, body) :
    mailer = 'Mail' # [fixme]
    addrlist = [a for a in addrs.split(':') if a]
    if not addrlist :
        warning("mailto no set, no mail will be sent")
        return 0
    trace("sending mail to %d address(es)" % len(addrlist))
    h_content = "Content-Type: text/plain; charset=utf-8"
    proc = cmdexec([mailer, '-a', h_content, '-s', subject] + addrlist,
                   stdin=CMDPIPE, universal_newlines=True)
    proc.stdin.write(body)
    proc.stdin.close()
    r = proc.wait()
    if r != 0 :
        error("sendmail (%s) failed: %s" % (mailer, r))
    return r


# StrangeParser:
#
class StrangeParser :


    # __init__:
    #
    def __init__ (self, name, journal, rules) :
        self.name = name
        self.journal = journal
        self.rules = tuple((rname, re.compile("(?P<ALL>"+reg+")"), rcmd, rmsg)
                           for rname, reg, rcmd, rmsg in rules)
        # lock it so we can use the same instance for multiple pipes
        # (not necessary for now, but maybe later)
        self.lock = threading.Lock()


    # match:
    #
    def match (self, line) :
        for rname, reg, rcmd, rmsg in self.rules :
            m = reg.match(line)
            if m is None :
                continue
            if rmsg :
                line = rmsg % m.groupdict()
            return rname, rcmd, line
        return '<nomatch>', 'strange', line

            
    # __call__:
    #
    def __call__ (self, line) :
        line = line.strip()
        if not line : return
        rname, cmd, line = self.match(line)
        if cmd == 'discard' :
            trace("%s: line discarded: '%s'" % (self.name, line))
        elif cmd == 'strange' :
            self.journal.record('STRANGE', source=self.name, message=line)
        elif cmd == 'note' :
            info("NOTE: %s" % line)
            self.journal.record('NOTE', message=line)
        elif cmd == 'warning' :
            warning(line)
        elif cmd == 'error' :
            error(line)
        else :
            assert 0, (rname, cmd, line)


# DumperTar:
#
class DumperTar :


    # [FIXME]
    GNUTAR = SYSCONF['GNUTAR']

    
    # start:
    #
    def start (self, path) :
        cmd = [self.GNUTAR, '--create', '--file', '-',
               '--totals', '--directory', path, '.']
        proc = cmdexec(cmd, stdout=CMDPIPE, stderr=CMDPIPE)
        return proc


    # start_index:
    #
    def start_index (self) :
        cmd = [self.GNUTAR, '--list', '--verbose',
               '--file', '-']
        proc = cmdexec(cmd, stdin=CMDPIPE, stdout=CMDPIPE)
        return proc
