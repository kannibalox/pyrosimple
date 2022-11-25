# pylint: disable=attribute-defined-outside-init
""" rTorrent queue manager & daemon.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""

import logging
import os
import signal
import sys
import time

from pathlib import Path
from typing import Dict

from apscheduler.schedulers.background import BackgroundScheduler
from daemon import DaemonContext
from daemon.pidfile import TimeoutPIDLockFile
from dynaconf.utils.boxing import DynaBox

from pyrosimple import config, error
from pyrosimple.scripts.base import ScriptBase, ScriptBaseWithConfig
from pyrosimple.util import logutil, pymagic


class RtorrentQueueManager(ScriptBaseWithConfig):
    """
    rTorrent queue manager & daemon.
    """

    # argument description for the usage information
    ARGS_HELP = ""

    POLL_TIMEOUT = 1.0

    RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR") or "~/.pyrosimple/run/"

    def add_options(self):
        """Add program options."""
        super().add_options()
        self.jobs: Dict = {}

        # basic options
        self.add_bool_option(
            "-n",
            "--dry-run",
            help="advise jobs not to do any real work, just tell what would happen",
        )
        self.add_bool_option(
            "--no-fork",
            "--fg",
            help="Don't fork into background (stay in foreground and log to console)",
        )
        self.add_value_option(
            "--run-once", "JOB", help="run the specified job once in the foreground"
        )
        self.add_bool_option("--stop", help="stop running daemon")
        self.add_bool_option(
            "--restart",
            help="stop any existing daemon, then start the process in the backgrounds",
        )
        self.add_bool_option("-?", "--status", help="Check daemon status")
        self.add_value_option(
            "--pid-file",
            "PATH",
            help="file holding the process ID of the daemon, when running in background",
        )

    # pylint: disable=no-self-use
    def parse_schedule(self, schedule):
        """Parse a job schedule."""
        result = {}

        for param in schedule.split():
            param = param.strip()
            try:
                key, val = param.split("=", 1)
                if key == "jitter":
                    val = int(val)
            except (TypeError, ValueError) as exc:
                raise error.ConfigurationError(
                    f"Bad param '{param}' in job schedule '{schedule}'"
                ) from exc
            else:
                result[key] = val

        return result

    def validate_config(self):
        """Handle and check configuration."""

        for name, params in config.settings.TORQUE.items():
            # Skip non-dictionary keys
            if not isinstance(params, DynaBox):
                continue
            for key in ("handler", "schedule"):
                if key not in params:
                    raise error.ConfigurationError(
                        f"Job '{name}' is missing the required '{key}' parameter"
                    )
            self.jobs[name] = dict(params)
            if self.options.dry_run:
                self.jobs[name]["dry_run"] = True
            if params.get("active", True):
                self.jobs[name]["handler"] = pymagic.import_name(params.handler)
            self.jobs[name]["schedule"] = self.parse_schedule(params.get("schedule"))

    def add_jobs(self):
        """Add configured jobs."""
        for name, params in self.jobs.items():
            if params.get("active", True):
                params.setdefault("__job_name", name)
                self.sched.add_job(
                    params["handler"](params).run,
                    name=name,
                    id=name,
                    trigger="cron",
                    **params["schedule"],
                )

    def reload_jobs(self):
        """Reload the configured jobs gracefully."""
        try:
            config.settings.configure()
            if self.running_config != dict(config.settings.TORQUE):
                self.LOG.info("Config change detected, reloading jobs")
                self.validate_config()
                self.sched.remove_all_jobs()
                self.add_jobs()
                self.running_config = dict(config.settings.TORQUE)
        except (Exception) as exc:  # pylint: disable=broad-except
            self.LOG.error("Error while checking config: %s", exc)

    def run_forever(self):
        """Run configured jobs until termination request."""
        self.running_config = dict(config.settings.TORQUE)
        while True:
            try:
                time.sleep(self.POLL_TIMEOUT)
                if config.settings.TORQUE.get("autoreload", False):
                    self.reload_jobs()
            except KeyboardInterrupt as exc:
                self.LOG.info("Termination request received (%s)", exc)
                break
            except SystemExit as exc:
                self.return_code = exc.code or 0
                self.LOG.info("System exit (RC=%r)", self.return_code)
                break

    def mainloop(self):
        """The main loop."""
        try:
            self.validate_config()
        except (error.ConfigurationError) as exc:
            self.fatal(exc)

        # Defaults for process control paths
        if not self.options.pid_file:
            self.options.pid_file = TimeoutPIDLockFile(
                Path(self.RUNTIME_DIR, "pyrotorque.pid").expanduser()
            )

        # Process control
        if self.options.status or self.options.stop or self.options.restart:
            if self.options.pid_file.is_locked():
                running, pid = True, self.options.pid_file.read_pid()
            else:
                running, pid = False, 0

            if self.options.status:
                if running:
                    print(f"Pyrotorque is running (PID {pid}).")
                    sys.exit(0)
                else:
                    print("No pyrotorque process found.")
                    sys.exit(1)

            if self.options.stop or self.options.restart:
                if running:
                    os.kill(pid, signal.SIGTERM)
                    self.LOG.debug("Process #%d sent SIGTERM.", pid)

                    # Wait for termination (max. 10 secs)
                    for _ in range(100):
                        if not self.options.pid_file.is_locked():
                            running = False
                            break
                        time.sleep(0.1)

                    self.LOG.info("Process #%d stopped.", pid)
                elif pid:
                    self.LOG.info("Process #%d NOT running anymore.", pid)
                else:
                    self.LOG.info(
                        "No pid file '%s'", (self.options.pid_file or "<N/A>")
                    )
            else:
                self.LOG.info(
                    "Process #%d %s running.", pid, "UP and" if running else "NOT"
                )

            if self.options.stop:
                self.return_code = error.EX_OK if running else error.EX_UNAVAILABLE
                return

        # Check if we only need to run once
        if self.options.run_once:
            params = self.jobs[self.options.run_once]
            if self.options.dry_run:
                params["dry_run"] = True
            params["handler_copy"] = params.get("handler")(params)
            params["handler_copy"].run()
            sys.exit(0)

        dcontext = DaemonContext(
            detach_process=False,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        # Detach, if not disabled via option
        if (
            not self.options.no_fork
        ):  # or getattr(sys.stdin, "isatty", lambda: False)():
            dcontext.detach_process = True
            dcontext.stdin = None
            dcontext.stderr = logutil.get_logfile()
            dcontext.stdout = logutil.get_logfile()
            dcontext.pidfile = self.options.pid_file
            self.LOG.info(
                "Writing pid to %s and detaching process...", self.options.pid_file
            )
            self.LOG.info("Logging stderr/stdout to %s", logutil.get_logfile())

        # Change logging format
        logging.basicConfig(
            force=True, format="%(asctime)s %(levelname)5s %(name)s: %(message)s"
        )

        with dcontext:
            # Set up services
            self.sched = BackgroundScheduler()

            # Run services
            self.sched.start()
            try:
                self.add_jobs()
                self.run_forever()
            finally:
                self.sched.shutdown()


def run():  # pragma: no cover
    """The entry point."""
    ScriptBase.setup()
    RtorrentQueueManager().run()


if __name__ == "__main__":
    run()
