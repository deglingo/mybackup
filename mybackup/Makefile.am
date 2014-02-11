#

PYCC = $(top_builddir)/tools/pycc

all-local: mb-modules.stamp-h sysconf.py

mb-modules.stamp-h: $(MB_MODULES_PY) $(PYCC)
	err=0; \
	for mod in $(MB_MODULES); do \
		test -e "$$mod.py" || $(LN_S) "$(abs_top_srcdir)/mybackup/$$mod.py" "$$mod.py"; \
		test "$$mod.pyc" -nt "$$mod.py" -a "$$mod.pyc" -nt "$(PYCC)" \
			|| $(PYCC) "$$mod.py" || err=`expr $$err + 1`; \
	done; \
	test $$err -eq 0 || { \
		echo "ERROR: some module(s) compilation failed!" >&2; \
		exit 1; }
	echo >$@

sysconf.py: sysconf.py.in sysconf.sed
	sed -f sysconf.sed <$< >$@.tmp
	mv -f $@.tmp $@

sysconf.sed: Makefile
	(   echo "s,%PACKAGE%,$(PACKAGE),g"; \
		echo "s,%pkgsysconfdir%,$(pkgsysconfdir),g"; \
		echo "s,%pkglocalstatedir%,$(pkglocalstatedir),g"; \
		echo "s,%pkgvardir%,$(pkgvardir),g"; \
		echo "s,%GNUTAR%,$(GNUTAR),g"; \
	) >$@.tmp
	mv -f $@.tmp $@

install-exec-hook:
	test -d "$(pkgpythondir)" || mkdir -p "$(pkgpythondir)"
	for mod in $(MB_MODULES_PY); do \
		rm -f "$(pkgpythondir)/$$mod"; \
		$(LN_S) "$(abs_top_srcdir)/mybackup/$$mod" "$(pkgpythondir)/$$mod"; \
	done
	rm -f "$(pkgpythondir)/sysconf.py"
	$(LN_S) "$(abs_top_builddir)/mybackup/sysconf.py" "$(pkgpythondir)/sysconf.py"
