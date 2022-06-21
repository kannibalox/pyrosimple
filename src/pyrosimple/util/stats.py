""" Statistics data.

    Copyright (c) 2014 The PyroScope Project <pyroscope.project@gmail.com>
"""


import time


def engine_data(engine):
    """Get important performance data and metadata from rTorrent."""
    views = (
        "default",
        "main",
        "started",
        "stopped",
        "complete",
        "incomplete",
        "seeding",
        "leeching",
        "active",
        "messages",
    )
    methods = [
        "throttle.global_up.rate",
        "throttle.global_up.max_rate",
        "throttle.global_down.rate",
        "throttle.global_down.max_rate",
    ]

    # Get data via multicall
    proxy = engine.open()
    calls = [dict(methodName=method, params=[]) for method in methods] + [
        dict(methodName="view.size", params=["", view]) for view in views
    ]
    result = proxy.system.multicall(calls, flatten=True)

    # Build result object
    data = dict(
        now=time.time(),
        engine_id=engine.engine_id,
        versions=engine.versions,
        uptime=engine.uptime,
        upload=[result[0], result[1]],
        download=[result[2], result[3]],
        views={name: result[4 + i] for i, name in enumerate(views)},
    )

    return data
