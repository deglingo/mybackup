#

AC_INIT([mybackup], [0.0.0])
AM_INIT_AUTOMAKE

# some default paths
AC_SUBST([pkgsysconfdir], '${sysconfdir}/${PACKAGE}')
AC_SUBST([vardir], '${prefix}/var')
AC_SUBST([pkgvardir], '${vardir}/${PACKAGE}')

AC_PROG_LN_S

# [FIXME] couldn't use AM_PATH_PYTHON with py3
#AM_PATH_PYTHON
AC_SUBST([PYTHON])
AC_SUBST([PYTHON_VERSION])
AC_SUBST([pythondir], '${libdir}/python${PYTHON_VERSION}/site-packages')
AC_SUBST([pkgpythondir], '${pythondir}/${PACKAGE}')
AC_MSG_CHECKING([for python3])
if PYTHON=`which python3`; then
	AC_MSG_RESULT([$PYTHON])
else
	AC_MSG_RESULT([no])
	AC_ERROR([python 3 required])
fi
AC_MSG_CHECKING([for python version])
if PYTHON_VERSION=`$PYTHON -c 'import sys; print("%d.%d" % (sys.version_info.major, sys.version_info.minor))'`; then
	AC_MSG_RESULT([$PYTHON_VERSION])
else
	AC_MSG_RESULT([error])
	AC_ERROR([could not get python version])
fi

m4_define([mb_modules], [ \
  __init__ \
  mbdump \
])

AC_SUBST([MB_MODULES],    "m4_map_args_w(mb_modules, [], [], [ ])")
AC_SUBST([MB_MODULES_PY], "m4_map_args_w(mb_modules, [], [.py], [ ])")

m4_define([mb_systest_modules], [ \
  test_base \
])

AC_SUBST([MB_SYSTEST_MODULES], "m4_map_args_w(mb_systest_modules, [], [], [ ])")

AC_CONFIG_FILES([ \
	Makefile \
	bin/Makefile \
	mybackup/Makefile \
	systest/Makefile \
])
AC_CONFIG_FILES([bin/mbdump], [chmod +x bin/mbdump])
AC_CONFIG_FILES([systest/mybackup-systest], [chmod +x systest/mybackup-systest])
AC_CONFIG_FILES(m4_map_args_w(mb_systest_modules, [systest/], [], [ ]))
AC_OUTPUT
