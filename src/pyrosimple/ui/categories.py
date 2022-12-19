""" Category management.

    Copyright (c) 2017 The PyroScope Project <pyroscope.project@gmail.com>
"""


from pyrosimple import error
from pyrosimple.scripts.base import ScriptBaseWithConfig
from pyrosimple.torrent import rtorrent
from pyrosimple.util import rpc


class CategoryManager(ScriptBaseWithConfig):
    """Rotate through category views."""

    PREFIX = "category_"
    PREFIX_LEN = len(PREFIX)

    # argument description for the usage information
    ARGS_HELP = ""

    def add_options(self):
        """Add program options."""
        super().add_options()

        self.add_bool_option("-l", "--list", help="list added category views")
        self.add_bool_option("-n", "--next", help="switch to next category view")
        self.add_bool_option("-p", "--prev", help="switch to previous category view")
        self.add_bool_option(
            "-u", "--update", help="filter the current category view again"
        )

    def mainloop(self):
        """Manage category views."""
        # Get client state
        proxy = rtorrent.RtorrentEngine().open()
        views = [x for x in sorted(proxy.view.list()) if x.startswith(self.PREFIX)]

        current_view = real_current_view = proxy.ui.current_view()
        if current_view not in views:
            if views:
                current_view = views[0]
            else:
                raise error.UserError(
                    f"There are no '{self.PREFIX}*' views defined at all!"
                )

        # Check options
        if self.options.list:
            for name in sorted(views):
                print(
                    "{} {:5d} {}".format(
                        "*" if name == real_current_view else " ",
                        proxy.view.size(rpc.NOHASH, name),
                        name[self.PREFIX_LEN :],
                    )
                )

        elif self.options.next or self.options.prev or self.options.update:
            # Determine next in line
            if self.options.update:
                new_view = current_view
            else:
                new_view = (views * 2)[
                    views.index(current_view) + (1 if self.options.next else -1)
                ]

            self.LOG.info(
                "{} category view '{}'.".format(
                    "Updating" if self.options.update else "Switching to", new_view
                )
            )

            # Update and switch to filtered view
            proxy.pyro.category.update(rpc.NOHASH, new_view[self.PREFIX_LEN :])
            proxy.ui.current_view.set(new_view)

        else:
            self.LOG.info(
                "Current category view is '%s'.", current_view[self.PREFIX_LEN :]
            )
            self.LOG.info("Use '--help' to get usage information.")


def run():  # pragma: no cover
    """The entry point."""
    CategoryManager().run()


if __name__ == "__main__":
    run()
