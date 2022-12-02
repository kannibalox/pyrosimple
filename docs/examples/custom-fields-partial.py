# Add file checkers
from pyrosimple.torrent import engine


def _custom_partial_fields():
    from pyrosimple.torrent import engine
    from pyrosimple.util import fmt, matching

    # Fields for partial downloads
    def partial_info(obj, name):
        "Helper for partial download info"
        try:
            return obj._fields[name]
        except KeyError:
            f_attr = [
                "completed_chunks",
                "size_chunks",
                "range_first",
                "range_second",
            ]
            chunk_size = obj.rpc_call("d.chunk_size")
            prev_chunk = -1
            size, completed, chunks = 0, 0, 0
            for f in obj._get_files(f_attr):
                if f.prio:  # selected?
                    shared = int(f.range_first == prev_chunk)
                    size += f.size
                    completed += f.completed_chunks - shared
                    chunks += f.size_chunks - shared
                    prev_chunk = f.range_second - 1

            obj._fields["partial_size"] = size
            obj._fields["partial_missing"] = (chunks - completed) * chunk_size
            obj._fields["partial_done"] = 100.0 * completed / chunks if chunks else 0.0

            return obj._fields[name]

    yield engine.DynamicField(
        int,
        "partial_size",
        "bytes selected for download",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: partial_info(o, "partial_size"),
    )
    yield engine.DynamicField(
        int,
        "partial_missing",
        "bytes missing from selected chunks",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: partial_info(o, "partial_missing"),
    )
    yield engine.DynamicField(
        float,
        "partial_done",
        "percent complete of selected chunks",
        matcher=matching.FloatFilter,
        accessor=lambda o: partial_info(o, "partial_done"),
    )


# Register our custom fields to the proxy
for field in _custom_partial_fields():
    engine.TorrentProxy.add_field(field)
