#

import sys, getopt, logging

from mybackup.log import *
from mybackup.config import Config


# USAGE:
#
USAGE = """\
USAGE: mbclean [OPTIONS] CONFIG

OPTIONS:

  -q, --quiet   be less verbose
  -v, --verbose be more verbose
  -h, --help    print this message and exit
"""


# MBCleanApp:
#
class MBCleanApp :


    # main:
    #
    def main (self) :
        self.__log_setup()
        self.config = Config()
        # parse the command line
        shortopts = 'qvh'
        longopts = ['quiet', 'verbose', 'help']
        opts, args = getopt.gnu_getopt(sys.argv[1:], shortopts, longopts)
        for o, a in opts :
            if o in ('-h', '--help') :
                sys.stdout.write(USAGE)
                sys.exit(0)
            elif o in ('-q', '--quiet') :
                self.config.verb_level -= 1
            elif o in ('-v', '--verbose') :
                self.config.verb_level += 1
            else :
                assert 0, (o, a)
        # fix log level
        self.log_cfilter.enable(logging.DEBUG,    self.config.verb_level >= 3)
        self.log_cfilter.enable(logging.INFO,     self.config.verb_level >= 2)
        self.log_cfilter.enable(logging.WARNING,  self.config.verb_level >= 1)
        self.log_cfilter.enable(logging.ERROR,    self.config.verb_level >= 1)
        self.log_cfilter.enable(logging.CRITICAL, self.config.verb_level >= 0)
        # init the config
        assert len(args) == 1, args
        self.config.init(args.pop(0))


    # __log_setup:
    #
    def __log_setup (self) :
        logger = log_setup('mbclean')
        self.log_cfilter = LogLevelFilter()
        hdlr = LogConsoleHandler()
        hdlr.addFilter(self.log_cfilter)
        logger.addHandler(hdlr)


# exec
if __name__ == '__main__' :
    app = MBCleanApp()
    app.main()
