#

import sys, getopt, logging, os

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
        try:
            self.__main()
        except Exception as exc:
            error("unhandled exception: %s" % exc,
                  exc_info=sys.exc_info())


    # __main:
    #
    def __main (self) :
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
        # open the logfile and say something
        self.__log_openfile()
        trace("started at %s (with pid %d/%d)" %
              (self.config.start_date, os.getpid(), os.getppid()))


    # __log_setup:
    #
    def __log_setup (self) :
        logger = log_setup('mbclean')
        self.log_cfilter = LogLevelFilter()
        hdlr = LogConsoleHandler()
        hdlr.addFilter(self.log_cfilter)
        logger.addHandler(hdlr)


    # __log_openfile:
    #
    def __log_openfile (self) :
        logger = logging.getLogger('mbclean')
        n, sfx = 0, ''
        while True :
            logfile = os.path.join(self.config.logdir, 'mbclean.%s.%s%s.log' %
                                   (self.config.cfgname, self.config.start_hrs, sfx))
            try:
                fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                n += 1
                sfx = '.%d' % n
                continue
            os.close(fd)
            break
        fhdlr = logging.FileHandler(logfile)
        fhdlr.setLevel(1)
        ffmt = LogFormatter(fmt='%(asctime)s %(process)5d [%(levelsym)s] %(message)s',
                            datefmt='%Y/%m/%d %H:%M:%S')
        fhdlr.setFormatter(ffmt)
        logger.addHandler(fhdlr)


# exec
if __name__ == '__main__' :
    app = MBCleanApp()
    app.main()
