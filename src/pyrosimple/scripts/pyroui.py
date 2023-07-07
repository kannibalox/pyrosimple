import pyrosimple
from pyrosimple.util import fmt
from typing import Any

from textual import work, on
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Grid
from textual.reactive import reactive
from textual.widgets import Header, Footer, DataTable, Static, TabbedContent, TabPane, Button, Input, Label, Tree, LoadingIndicator
from textual.screen import Screen, ModalScreen

class PeerTable(DataTable):
    def __init__(self, key):
        self.key = key
        super().__init__()
        self.cursor_type = "row"

    def on_mount(self):
        self.add_columns("IP", "Up", "Down","Peer")

class FilterEdit(ModalScreen):
    def compose(self):
        yield Grid(
            Input(value=self.app.rtorrent_filter, id="filter_input"),
            Button("Apply", variant="primary", id="apply"),
            Button("Cancel", variant="error", id="cancel"),
            id="filter_dialog",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.app.rtorrent_filter = self.query_one(Input).value
        self.app.load_data()
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply":
            self.app.rtorrent_filter = self.query_one(Input).value
            self.app.load_data()
        self.dismiss(False)


class TorrentInfoScreen(ModalScreen):
    BINDINGS = [
        ("escape", "escape", "Return to main screen")
    ]
    def __init__(self, key):
        self.key = key
        super().__init__()

    def compose(self) -> ComposeResult:
        name = self.app.rtorrent_engine.open().d.name(self.key.value)
        yield Static(f"*** {name} ***", id="torrent_info_header")
        with TabbedContent(id="torrent_info_tabs"):
            with TabPane("Info"):
                yield Static(f"hi {self.key.value}: {name}")
            with TabPane("Peers", id="peers"):
                yield PeerTable(self.key)
            with TabPane("Files", id="files"):
                yield Label(name)
                yield Tree("hi")
        yield Footer()

    @on(TabbedContent.TabActivated, "#torrent_info_tabs", tab="#peers")
    @work(exclusive=True)
    def load_peer_data(self) -> None:
        fields = []
        proxy = self.app.rtorrent_engine.open()
        table = self.query_one(PeerTable)
        fields = ["address","up_rate", "down_rate", "client_version"]
        result = proxy.p.multicall(self.key.value, '', *[f"p.{f}=" for f in fields])
        table.clear()
        for peer in result:
            data = dict(zip(fields, peer))
            if int(data["up_rate"]) != 0:
                up = fmt.human_size(data["up_rate"])+"/s"
            table.add_row(
                data["address"],
                fmt.human_size(data["up_rate"])+"/s" if int(data["up_rate"]) !=	0 else "-",
                fmt.human_size(data["down_rate"])+"/s" if int(data["down_rate"]) != 0 else "-",
                data["client_version"]
            )
        
    def on_mount(self):
        #self.load_peer_data()
        pass


    def action_escape(self):
        self.app.pop_screen()
        
class CollapsedTorrentTable(DataTable):
    COLUMNS = [
        ("❢", {"key": "error", "width": 1}, "{% if d.message %}[bold red reverse]!{%endif%}"),
        ("☢", {"key": "state", "width": 1}, "{% if d.is_open and d.is_active %}▹{% else %}▪{%endif%}"),
        ("☍ ", {"key": "tied", "width": 1}, "{% if d.metafile %}⚯{%endif%}"),
        ("⌘", {"key": "ignored"}, "{% if d.is_ignored %}⚒{%else%}◌{%endif%}"),
        ("☇", {"key": "xfer", "width": 1}, "{% if d.up and d.down.rate%}⇅{%elif d.up %}↟{%elif d.down %}↡{%endif%}"),
        ("℞", {"key": "peers_connected"}, "{{d.d_peers_connected}}"),
        ("⣿", {"key": "progress", "width": 1}, "{% if d.is_complete %}❚{%elif d.done == 0%} {%else%}{{ '⠁⠉⠋⠛⠟⠿⡿⣿'[d.done|int//8]}}{%endif%}"),
        ("⛁", {"key": "size"}, "{{d.size|sz}}"),
        ("T", {"key": "alias"}, "{{d.alias}}"),
        ("Name", {"key": "name"}, "{%set rich='magenta'%}{%if d.is_complete%}{%set rich='green'%}{%endif%}[{{rich}}]{{d.name}}"),
    ]
    def __init__(self, engine) -> None:
        self.rtorrent_engine = engine
        super().__init__(zebra_stripes=True)
        self.cursor_type = "row"
        self.styles.height = "100%"

    def on_mount(self):
        for c in self.COLUMNS:
            if isinstance(c, str):
                self.sadd_column(c)
            else:
                self.add_column(c[0], **c[1])

    def on_data_table_row_selected(self, event) -> None:
        self.app.push_screen(TorrentInfoScreen(event.row_key))

class MainScreen(Screen):
    pass

class DownloadHeader(Static):
    view = reactive("main")
    filter = reactive("//")

    def render(self):
        return f"\[View: {self.view}] [Filter: {self.filter}]"


class PyroUIApp(App):
    """A Textual app to manage stopwatches."""

    CSS_PATH = "pyroui.css"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("Enter", "view_torrent", "View torrent"),
        ("!", "show_errors", "Show errors"),
        ("/", "edit_filter", "Edit filter"),
        ("r", "refresh", "Refresh"),
        ("v", "switch_view", "Edit view"),
    ]

    def __init__(self):
        self.rtorrent_engine = pyrosimple.connect()
        self.rtorrent_filter = "//"
        self.previous_prev_filter = "//"
        self.rtorrent_view = "main"
        super().__init__()

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Static("rtorrent", id="rtorrent_info")
        yield DownloadHeader("\[View: default] [None of None]", id="pyroui_header")
        yield ScrollableContainer(CollapsedTorrentTable(self.rtorrent_engine))
        yield Footer()

    def on_mount(self):
        self.load_engine()
        self.load_data()

    def load_engine(self) -> None:
        self.rtorrent_engine.open()
        props = self.rtorrent_engine.properties
        self.query_one("#rtorrent_info").renderable = f"*** rTorrent {props['system.client_version']}/{props['system.library_version']} - {props['session.name']} ***"
        header = self.query_one("#pyroui_header")
        header.view = self.rtorrent_view
        header.filter = self.rtorrent_filter

    @work(exclusive=True)
    def load_data(self) -> None:
        if not self.rtorrent_filter:
            self.rtorrent_filter = "//"
        table = self.query_one(CollapsedTorrentTable)
        prefetch = []
        template_str = "\t".join([c[2] for c in table.COLUMNS])
        for p in pyrosimple.torrent.rtorrent.get_fields_from_template(template_str):
            prefetch.extend(pyrosimple.torrent.engine.field_lookup(p).requires)
        matcher = pyrosimple.util.matching.create_matcher(self.rtorrent_filter)
        view = self.rtorrent_engine.view(self.rtorrent_view, matcher=matcher)
        template = pyrosimple.torrent.rtorrent.env.from_string(template_str)
        items = list(self.rtorrent_engine.items(view, prefetch=prefetch))
        # This shouldn't change wildly
        if self.rtorrent_filter == self.previous_prev_filter:
            hashes = list([i.hash for i in items])
            table_hashes = list([r.value for r in table.rows])
            # Delete
            for row in list(table.rows):
                if row.value not in hashes:
                    table.remove_row(row)
            for item in items:
                data = list(pyrosimple.torrent.rtorrent.format_item(template, item).split("\t"))
                # Create
                if item.hash not in table_hashes:
                    table.add_row(*data, key=item.hash)
                else:
                    # Update
                    for i, c in enumerate(table.columns.keys()):
                        table.update_cell(item.hash, c.value, data[i])
        else:
            table.disabled = True
            table.clear()
            for item in items:
                data = pyrosimple.torrent.rtorrent.format_item(template, item).split("\t")
                table.add_row(*data, key=item.hash)
            self.previous_prev_filter = self.rtorrent_filter
            table.disabled = False
        table.focus()
        header = self.query_one("#pyroui_header")
        header.view = self.rtorrent_view
        header.filter = self.rtorrent_filter

    def action_show_errors(self) -> None:
        self.rtorrent_filter = "message=/.+/"
        self.load_data()

    def action_switch_view(self) -> None:
        self.rtorrent_view = "name"
        self.load_data()

    def action_refresh(self) -> None:
        self.load_data()
        
    def action_edit_filter(self) -> None:
        self.push_screen(FilterEdit())
        
    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

        

def run():
    import sys
    app = PyroUIApp()
    if sys.argv[1]:
        app.rtorrent_filter = sys.argv[1]
        app.rtorrent_prev_filter = sys.argv[1]
    app.run()

if __name__ == "__main__":
    run()
