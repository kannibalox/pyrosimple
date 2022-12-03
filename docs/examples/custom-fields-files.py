from pyrosimple.torrent import engine


def _custom_file_fields():
    import fnmatch
    import re

    from pyrosimple.torrent import engine
    from pyrosimple.util import fmt, matching

    def has_glob(glob):
        regex = re.compile(fnmatch.translate(glob))  # Pre-compile regex for performance

        # Return a function containing the compiled regex to match against
        def _has_glob_accessor(obj):
            return any([f for f in obj._get_files() if regex.match(f.path)])

        return _has_glob_accessor

    yield engine.DynamicField(
        engine.untyped,
        "has_nfo",
        "does download have a .NFO file?",
        matcher=matching.BoolFilter,
        accessor=has_glob("*.nfo"),
        formatter=lambda val: "NFO" if val else "!DTA" if val is None else "----",
    )
    yield engine.DynamicField(
        engine.untyped,
        "has_thumb",
        "does download have a folder.jpg file?",
        matcher=matching.BoolFilter,
        accessor=has_glob("folder.jpg"),
        formatter=lambda val: "THMB" if val else "!DTA" if val is None else "----",
    )


# Register our custom fields to the proxy
for field in _custom_file_fields():
    engine.TorrentProxy.add_field(field)
