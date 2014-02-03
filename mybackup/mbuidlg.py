#

# [todo]
def _(m) : return m


# DIALOG:
#
DIALOG = {
    # main menu
    'main': {
        'type': 'DMenu',
        'args': {
            'menu': ((_('1'), _('Inspect your backups')),
                     (_('2'), _('Switch to another configuration')),
                     (_('3'), _('Quit'))),
        },
    },
    # configuration selection menu
    'select-config': {
        'type': 'DMenu',
        'args': {
            'text': _('Please choose a configuration'),
        },
    },
    # disk selection menu
    'select-disk': {
        'type': 'DMenu',
        'args': {
            'text': _('Please select a disk'),
        },
    },
    # dump selection menu
    'select-dump': {
        'type': 'DMenu',
        'args': {
            'text': _('Please select a dump to inspect'),
        },
    },
}
