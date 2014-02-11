# config.py - app configuration

__all__ = [
    'Config',
]

import os, json, collections

from mybackup.base import *
from mybackup.log import *
from mybackup.tools import *
from mybackup.sysconf import SYSCONF


# Config:
#
class Config :


    start_date = property(lambda self: stamp2date(self.start_stamp))
    start_hrs = property(lambda self: stamp2hrs(self.start_stamp))

    
    # __init__:
    #
    def __init__ (self) :
        self.system = CfgSystem()
        # [fixme] runtime
        self.verb_level = 2
        self.force = False
        self.user_notes = []

        
    # init:
    #
    def init (self, cfgname) :
        # starting date
        dt = os.environ.get('_MB_SYSTEST_DATE')
        self.start_stamp = int(time.time()) if dt is None \
          else date2stamp(dt)
        # init
        self.cfgname = cfgname
        self.cfgdir = os.path.join(self.system.pkgsysconfdir, self.cfgname)
        self.vardir = self.system.pkgvardir
        self.cfgvardir = os.path.join(self.vardir, self.cfgname)
        self.lockdir = os.path.join(self.vardir, 'lock') # note global!
        self.cfglockfile = os.path.join(self.lockdir, self.cfgname + '.lock')
        self.dbdir = os.path.join(self.cfgvardir, 'db')
        self.dbfile = os.path.join(self.dbdir, self.cfgname + '.db') 
        self.journaldir = os.path.join(self.cfgvardir, 'journal')
        self.journalfile = os.path.join(self.journaldir, 'journal.txt')
        self.journallock = os.path.join(self.lockdir, '%s.journal.lock' % self.cfgname)
        self.dumpdir = os.path.join(self.cfgvardir, 'dumps')
        self.partdir = os.path.join(self.dumpdir, 'partial')
        self.logdir = os.path.join(self.cfgvardir, 'log')
        self.scriptsvardir = os.path.join(self.cfgvardir, 'scripts')
        # read the config file
        self.cfgfile = os.path.join(self.cfgdir, 'mybackup.conf')
        trace("reading config file: '%s'" % self.cfgfile)
        try:
            conf = json.load(open(self.cfgfile, 'rt'))
        except:
            exception("error in config file:\n%s" %
                  ('\n'.join('%4d %s' % (i+1, l.rstrip())
                             for i, l in enumerate(open(self.cfgfile, 'rt').readlines()))))
            raise
        self.configure(conf)


    # configure:
    #
    def configure (self, conf_) :
        conf = copy.deepcopy(conf_)
        self.mailto = conf.pop('mailto', '')
        self.report_columns = tuple(conf.pop('report_columns',
                                       (r'\title=DISK\%(disk)s',
                                        r'\title=STATE\center\%(upstate)s',
                                        r'\title=RAW SIZE\right\%(raw_hsize)s',
                                        r'\title=COMP SIZE\right\%(comp_hsize)s',
                                        r'\title=RATIO\right\%(comp_ratio).2f%%',
                                        r'\title=FILES\right\%(nfiles)d')))
        self.scripts = dict(
            (n, CfgScript(self, n, sconf))
            for n, sconf in conf.pop('scripts', {}).items())
        self.disks = collections.OrderedDict(
            (n, CfgDisk(self, n, dconf))
            for n, dconf in conf.pop('disks').items())

        assert not conf, conf

        # create some directories
        # [fixme] not the right place for this !?
        mkdir(self.lockdir)
        mkdir(self.dbdir)
        mkdir(self.journaldir)
        mkdir(self.dumpdir)
        mkdir(self.partdir)
        mkdir(self.logdir)


    # list_disks:
    #
    def list_disks (self) :
        return list(self.disks.values())


# CfgSystem:
#
class CfgSystem :

    def __getattr__ (self, name) :
        return SYSCONF[name]


# CfgDisk:
#
class CfgDisk :


    config = property(lambda self: self._wr_config())

    
    # __init__:
    #
    def __init__ (self, config, name, dconf) :
        self._wr_config = weakref.ref(config)
        self.name = name
        self.configure(dconf)


    # __repr__:
    #
    def __repr__ (self) :
        return '<%s %s:%s>' % (self.__class__.__name__,
                               self.config.cfgname,
                               self.name)


    # configure:
    #
    def configure (self, conf_) :
        conf = copy.deepcopy(conf_)
        self.path = conf.pop('path')
        self.orig = conf.pop('orig', '')
        self.hooks = conf.pop('hooks', [])
        assert not conf, conf
        # [removeme]
        # for n, v in dconf.items() :
        #     setattr(self, n, v)


    # get_dumper:
    #
    def get_dumper (self) :
        # [fixme]
        return DumperTar()


    # get_dumpname:
    #
    def get_dumpname (self, runid, level, prevrun, hrs, state) :
        state = '' if DumpState.cmp(state, 'ok') \
          else ('.' + DumpState.tostr(state).upper())
        return 'mbdump.%(config)s.%(disk)s.%(runid)03d.%(level)d-%(prevrun)03d.%(hrs)s%(state)s' % {
            'config': self.config.cfgname,
            'disk': self.name,
            'runid': runid,
            'level': level,
            'prevrun': prevrun,
            'hrs': hrs,
            'state': state }

    
    # get_dumpext:
    #
    def get_dumpext (self) :
        # [fixme]
        return '.tgz'


    # [fixme] should be elsewhere
    def _match_trigger (self, trigger, spec) :
        for t in spec.split(',') :
            t = t.strip()
            if not t : continue
            if re.match(t, trigger, re.IGNORECASE) :
                return True
        return False

        
    # run_hooks:
    #
    def run_hooks (self, trigger, journal) :
        for hook in self.hooks :
            if not self._match_trigger(trigger, hook['triggers']) :
                continue
            script = self.config.scripts[hook['script']]
            trace("%s: '%s' hook: %s" % (self.name, trigger, script.name))
            vardir = os.path.join(self.config.scriptsvardir, script.name)
            mkdir(vardir)
            cmd = [script.prog]
            a = {'config': self.config.cfgname,
                 'disk': self.name,
                 'orig': self.orig,
                 'path': self.path,
                 'vardir': vardir,
                 'trigger': trigger}
            cmd.extend(o % a for o in script.options + hook['options'])
            proc = cmdexec(cmd, cwd=self.config.cfgdir,
                           stdout=CMDPIPE, stderr=CMDPIPE)
            name = 'hook.%s.%s.%s' % (self.name, trigger, script.name)
            parser = StrangeParser(name, journal)
            pout = PipeThread(name, proc.stdout, (),
                              line_handler=parser, started=True)
            perr = PipeThread(name, proc.stderr, (),
                              line_handler=parser, started=True)
            pout.join()
            perr.join()
            r = proc.wait()
            assert r == 0, (self.config.start_hrs, r, self, hook)


# CfgScript:
#
class CfgScript :


    config = property(lambda self: self._wr_config())

    
    # __init__:
    #
    def __init__ (self, config, name, dconf) :
        self._wr_config = weakref.ref(config)
        self.name = name
        self.configure(dconf)


    # __repr__:
    #
    def __repr__ (self) :
        return '<%s %s:%s>' % (self.__class__.__name__,
                               self.config.cfgname,
                               self.name)


    # configure:
    #
    def configure (self, conf_) :
        conf = copy.deepcopy(conf_)
        self.prog = conf.pop('prog')
        self.options = conf.pop('options', [])
        assert not conf, conf
        # for n, v in dconf.items() :
        #     setattr(self, n, v)
