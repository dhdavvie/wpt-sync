_config = None
_bz = None
_gh_wpt = None
_phab = None

class Environment(object):
    @property
    def config(self):
        return _config

    @property
    def bz(self):
        return _bz

    @property
    def gh_wpt(self):
        return _gh_wpt

    @property
    def phab(self):
        return _phab


def set_env(config, bz, gh_wpt, phab):
    global _config, _bz, _gh_wpt, _phab
    _config = config
    _bz = bz
    _gh_wpt = gh_wpt
    _phab = phab


def clear_env():
    # Only tests should really do this
    global _config, _bz, _gh_wpt, _phab
    _config = None
    _bz = None
    _gh_wpt = None
    _phab = None
