#

all-local: mb-modules.stamp-h sysconf.py

mb-modules.stamp-h: $(MB_MODULES_PY)
	for mod in $(MB_MODULES_PY); do \
		test -e "$$mod" || $(LN_S) "$(abs_top_srcdir)/mybackup/$$mod" "$$mod"; \
	done
	echo >$@

sysconf.py: sysconf.py.in sysconf.sed
	sed -f sysconf.sed <$< >$@.tmp
	mv -f $@.tmp $@

sysconf.sed: Makefile
	(   echo "s,%PACKAGE%,$(PACKAGE),g"; \
		echo "s,%pkgsysconfdir%,$(pkgsysconfdir),g"; \
		echo "s,%pkglocalstatedir%,$(pkglocalstatedir),g"; \
		echo "s,%pkgvardir%,$(pkgvardir),g"; \
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
