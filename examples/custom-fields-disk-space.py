from pyrosimple.torrent import engine


def _custom_disk_fields():
    import os

    import pyrosimple

    from pyrosimple.torrent import engine

    def has_room(obj):
        diskspace_threshold_mb = int(
            pyrosimple.config.settings.get("diskspace_threshold_mb", 500)
        )
        path = Path(obj.path)
        if not path.exists():
            path = Path(path.parent)
        if path.exists():
            stats = os.statvfs(path)
            return stats.f_bavail * stats.f_frsize - int(
                diskspace_threshold_mb
            ) * 1024**2 > obj.size * (1.0 - obj.done / 100.0)

    yield engine.DynamicField(
        engine.untyped,
        "has_room",
        "check whether the download will fit on its target device",
        matcher=matching.BoolFilter,
        accessor=has_room,
        formatter=lambda val: "OK" if val else "??" if val is None else "NO",
    )


# Register our custom fields to the proxy
for field in _custom_disk_fields():
    engine.TorrentProxy.add_field(field)
