#

import sys, getopt

from mybackup.base import *
from mybackup.log import *
from mybackup import mbapp


# USAGE:
#
USAGE = """\
USAGE: mbcheck [OPTIONS] CONFIG

OPTIONS:

  -q, --quiet      be less verbose
  -v, --verbose    be more verbose
  -h, --help       print this message and exit
"""


# MBCheckApp:
#
class MBCheckApp (mbapp.MBAppBase) :


    LOG_DOMAIN = 'mbcheck'


    # app_run:
    #
    def app_run (self) :
        # parse the command line
        shortopts = 'hqv'
        longopts = ['help']
        opts, args = getopt.gnu_getopt(sys.argv[1:], shortopts, longopts)
        for o, a in opts :
            if o in ('-h', '--help') :
                sys.stdout.write(USAGE)
                sys.exit(0)
            elif o in ('-q', '--quiet') :
                self.quiet()
            elif o in ('-v', '--verbose') :
                self.verbose()
            else :
                assert 0, (o, a)
        # init the config
        assert len(args) >= 1, args
        self.init_config(args.pop(0))
        # open the logfile and say something
        self.open_logfile()
        # acquire the config lock
        try:
            with FLock(self.config.cfglockfile, block=False) :
                self.__main_L(args)
        except FLockError as exc:
            error(exc, exc_info=sys.exc_info())
            error("(this probably means that another mb* process is running)")
            sys.exit(1)


    # __main_L:
    #
    def __main_L (self, args) :
        # [FIXME] try to open the db and journal ?
        info("config '%s' seems clean" % self.config.cfgname)


# exec
if __name__ == '__main__' :
    MBCheckApp.main()
