"""UI utilities. This is mostly kept in a separate module to allow
deferring the load of prompt_toolkit until it's needed.
"""

from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import ProgressBar, ProgressBarCounter
from prompt_toolkit.shortcuts.progress_bar import formatters

from pyrosimple.util.fmt import human_size


class ByteProgress(formatters.Progress):
    """Displays the counnt in byte form."""

    def format(
        self,
        progress_bar: "ProgressBar",
        progress: "ProgressBarCounter[object]",
        width: int,
    ):
        """Format the counts into human-readable sizes."""
        return HTML(self.template).format(
            current=human_size(progress.items_completed),
            total=human_size(progress.total or -1),
        )


class HashProgressBar(ProgressBar):
    """Custom progress bar for showing the hash progress"""

    BYTE_FORMATTER = [
        formatters.Label(),
        formatters.Text(" "),
        formatters.Percentage(),
        formatters.Text(" "),
        formatters.Bar(),
        formatters.Text(" "),
        ByteProgress(),
        formatters.Text(" "),
        formatters.Text("ETA [", style="class:time-left"),
        formatters.TimeLeft(),
        formatters.Text("]", style="class:time-left"),
        formatters.Text(" "),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, formatters=self.BYTE_FORMATTER, **kwargs)

    def __call__(
        self,
        data=None,
        label="",
        remove_when_done=False,
        total=None,
    ):
        """Override the default counter."""
        counter = HashProgressBarCounter(
            self, data, label=label, remove_when_done=remove_when_done, total=total
        )
        self.counters.append(counter)
        return counter


class HashProgressBarCounter(ProgressBarCounter):
    """Custom progress bar counter to provide methods to match metafile.Metafile's callbacks"""

    def progress_callback(self, totalhashed, totalsize):
        """Bump the progress for each piece"""
        self.total = totalsize
        self.items_completed = totalhashed
        self.progress_bar.invalidate()
