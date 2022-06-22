""" Python Utility Functions.

    Copyright (c) 2009, 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""


import json
import logging


def import_name(module_spec, name=None):
    """Import identifier C{name} from module C{module_spec}.

    If name is omitted, C{module_spec} must contain the name after the
    module path, delimited by a colon (like a setuptools entry-point).

    @param module_spec: Fully qualified module name, e.g. C{x.y.z}.
    @param name: Name to import from C{module_spec}.
    @return: Requested object.
    @rtype: object
    """
    # Hijack requests for pyrocore
    if "pyrocore" in module_spec or "pyrobase" in module_spec:
        module_spec = module_spec.replace("pyrocore", "pyrosimple")
        module_spec = module_spec.replace("pyrobase", "pyrosimple")
    # Load module
    module_name = module_spec
    if name is None:
        try:
            module_name, name = module_spec.split(":", 1)
        except ValueError:
            # pylint: disable=raise-missing-from
            raise ValueError(
                "Missing object specifier in %r (syntax: 'package.module:object.attr')"
                % (module_spec,)
            )

    try:
        module = __import__(module_name, globals(), {}, [name])
    except ImportError as exc:
        raise ImportError(f"Bad module name in {module_spec!r} ({exc})") from exc

    # Resolve the requested name
    result = module
    for attr in name.split("."):
        result = getattr(result, attr)

    return result


def get_class_logger(obj):
    """Get a logger specific for the given object's class."""
    return logging.getLogger(obj.__class__.__module__ + "." + obj.__class__.__name__)


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder."""

    def default(self, o):
        """Support more object types."""
        if isinstance(o, set):
            return list(sorted(o))
        if hasattr(o, "as_dict"):
            return o.as_dict()
        return super().default(o)
