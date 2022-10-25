---
title: Integrate with Conky
---

You can use `rtcontrol`'s templating features to easily integrate
rTorrent in `conky`, a well-known desktop system monitor for Linux.

1. Ensure the [rtorstat template](https://github.com/kannibalox/pyrosimple/tree/main/docs/examples/rtorstat) is installed in your templates directory (`~/.config/pyrosimple/templates/`)
2. Integrate the [example conky.rc](https://github.com/kannibalox/pyrosimple/tree/main/docs/examples/conky.rc) into your local conky config.
3. Start conky

You should see rTorrent statistics showing up in your conky display after a brief delay. You can modify the `rtcontrol` command in `conky.rc` to control which individual torrents are displayed.
