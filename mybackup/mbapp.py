# mbapp.py - a base class for all the mb* applications

__all__ = [
    'MBAppBase',
]

import logging, os, sys

from mybackup.log import *
from mybackup import config


# MBAppBase:
#
class MBAppBase :


    # main:
    #
    @classmethod
    def main (cls) :
        r = 0
        try:
            try:
                app = cls()
                app.__init()
                app.__run()
            except Exception as exc:
                exception("unhandled exception: %s: %s" %
                          (exc.__class__.__name__, exc))
                r = 1
        finally:
            logging.shutdown()
        sys.exit(r)
                


    # [fixme] log level adjustment
    #
    def quiet (self) :
        self.set_verb_level(self.config.verb_level - 1)
        
    def verbose (self) :
        self.set_verb_level(self.config.verb_level + 1)

    def set_verb_level (self, l) :
        self.config.verb_level = l # [fixme]
        self.__confilter.enable(logging.DEBUG, l > 3)
        self.__confilter.enable(logging.INFO, l > 2)
        self.__confilter.enable(logging.WARNING, l > 1)
        self.__confilter.enable(logging.ERROR, l > 1)
        self.__confilter.enable(logging.CRITICAL, l > 0)


    # init_config:
    #
    # Call this once to set the config name and read all files
    #
    def init_config (self, cfgname) :
        self.config.init(cfgname)


    # open_logfile:
    #
    def open_logfile (self) :
        logger = logging.getLogger(self.LOG_DOMAIN)
        n, sfx = 0, ''
        while True :
            logfile = os.path.join(self.config.logdir, '%s.%s.%s%s.log' %
                                   (self.LOG_DOMAIN, self.config.cfgname, self.config.start_hrs, sfx))
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
        trace("logfile opened at %s '%s'" %
              (self.config.start_date, logfile))


    # __log_setup:
    #
    def __log_setup (self) :
        logger = log_setup(self.LOG_DOMAIN)
        self.__confilter = LogLevelFilter()
        self.set_verb_level(3)
        hdlr = LogConsoleHandler()
        hdlr.addFilter(self.__confilter)
        logger.addHandler(hdlr)


    # __init:
    #
    def __init (self) :
        # create a config
        self.config = config.Config()
        # initialize the logger
        self.__log_setup()
        # run the user handler
        hdlr = getattr(self, 'app_init', None)
        if hdlr is not None :
            hdlr()


    # __run:
    #
    def __run (self) :
        self.app_run()
