"""Generic collections set to ease work with dicts"""
from collections import defaultdict


class Bunch(dict):
    """Generic attribute container that also is a dict."""

    def __getattr__(self, name):
        try:
            return dict.__getattribute__(self, name)
        except AttributeError:
            try:
                return self[name]
            except KeyError:
                # pylint: disable=raise-missing-from
                raise AttributeError(
                    "Bunch has no attribute %r in %s"
                    % (name, ", ".join([repr(i) for i in self.keys()]))
                )

    def __setattr__(self, name, value):
        self[name] = value

    def __repr__(self):
        return "Bunch(%s)" % ", ".join(sorted("%s=%r" % attr for attr in self.items()))


class DefaultBunch(Bunch, defaultdict):
    """Generic attribute container that also is a dict."""
