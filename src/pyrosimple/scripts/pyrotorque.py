# pylint: disable=attribute-defined-outside-init
""" rTorrent queue manager & daemon.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""

import errno
import logging
import os
import signal
import sys
import time

from pathlib import Path
from typing import Dict

from apscheduler.schedulers.background import BackgroundScheduler
from box.box import Box
from daemon import DaemonContext
from daemon.pidfile import TimeoutPIDLockFile
from lockfile.pidlockfile import AlreadyLocked, LockFailed

from pyrosimple import config, error
from pyrosimple.scripts.base import ScriptBaseWithConfig
from pyrosimple.util import pymagic


def pid_exists(pid):
    """Check whether pid exists in the current process table."""
    if pid == 0:
        return True
    try:
        os.kill(pid, 0)
    except OSError as err:
        if err.errno == errno.ESRCH:
            # ESRCH == No such process
            return False
        elif err.errno == errno.EPERM:
            # EPERM clearly means there's a process to deny access to
            return True
        raise
    return True


class RtorrentQueueManager(ScriptBaseWithConfig):
    """
    rTorrent queue manager & daemon.
    """

    POLL_TIMEOUT = 1.0

    RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR") or "~/.pyrosimple/run/"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.classes = {}
        self.jobs: Dict = {}
        self.running_config = {}

    def add_options(self):
        """Add program options."""
        super().add_options()

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
            type=Path,
        )
        self.add_bool_option(
            "--adopt-stale-pid-file",
            help="if the pid file exists but appears to be stale, adopt it",
        )
        self.add_value_option(
            "--log-file",
            "PATH",
            type=Path,
            help="file for logging stderr/stdout of the forked process (only used when running the daemon in the background)",
        )

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
            result[key] = val

        return result

    def validate_config(self):
        """Handle and check configuration."""

        for name, params in config.settings.TORQUE.items():
            # Skip non-dictionary keys
            if not isinstance(params, Box) or name == "_settings":
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
                self.jobs[name]["__handler"] = pymagic.import_name(params.handler)
            self.jobs[name]["schedule"] = self.parse_schedule(params.get("schedule"))

    def add_jobs(self):
        """Add configured jobs."""
        for name, params in self.jobs.items():
            if params.get("active", True):
                params.setdefault("__job_name", name)
                # Keep track of the instantiated class for cleanup later
                self.classes[name] = params["__handler"](params)
                self.sched.add_job(
                    self.classes[name].run,
                    name=name,
                    id=name,
                    trigger="cron",
                    **params["schedule"],
                )

    def unload_jobs(self):
        """Allows jobs classes to clean up any global resources if the
        cleanup() method exists.

        This should be called only once the jobs have finished
        running, so that a successive run doesn't re-create the
        resources.
        """
        for _, cls in self.classes.items():
            if hasattr(cls, "cleanup") and callable(cls.cleanup):
                cls.cleanup()

    def reload_jobs(self):
        """Reload the configured jobs gracefully."""
        try:
            config.load_settings()
            if self.running_config != dict(config.settings.TORQUE):
                self.log.info("Config change detected, reloading jobs")
                self.validate_config()
                self.sched.pause()
                self.sched.remove_all_jobs()
                self.unload_jobs()
                self.sched.resume()
                self.add_jobs()
                self.running_config = dict(config.settings.TORQUE)
        except Exception as exc:  # pylint: disable=broad-except
            self.log.error("Error while reloading config: %s", exc)
        else:
            self.sched.resume()

    def run_forever(self):
        """Run configured jobs until termination request."""
        self.running_config = dict(config.settings.TORQUE)
        reload_config = config.settings.TORQUE.get(
            "autoreload", False
        ) or config.settings.TORQUE._settings.get("autoreload", False)
        while True:
            try:
                time.sleep(self.POLL_TIMEOUT)
                if reload_config:
                    self.reload_jobs()
            except KeyboardInterrupt as exc:
                self.log.info("Termination request received (%r)", exc)
                self.sched.shutdown()
                self.unload_jobs()
                break
            except SystemExit as exc:
                if isinstance(exc.code, int):
                    self.return_code = exc.code
                else:
                    self.return_code = 0
                self.log.info("System exit (RC=%r)", self.return_code)
                break

    def mainloop(self):
        """The main loop."""
        try:
            self.validate_config()
        except error.ConfigurationError as exc:
            self.fatal(exc)

        # Defaults for process control paths
        pid_file = TimeoutPIDLockFile(
            Path(
                self.options.pid_file
                or config.settings.TORQUE._settings.get(
                    "pid_file", Path(self.RUNTIME_DIR, "pyrotorque.pid")
                )
            )
        )
        log_file = self.options.log_file or config.settings.TORQUE._settings.get(
            "log_file", None
        )
        log_level = (
            config.settings.TORQUE._settings.get("log_level", None)
            or self.options.log_level
        )

        # Process control
        if pid_file.is_locked():
            running, pid = True, pid_file.read_pid()
        else:
            running, pid = False, 0
        if self.options.status or self.options.stop or self.options.restart:
            if self.options.status:
                if running:
                    if pid_exists(pid):
                        self.log.info("Pyrotorque is running (PID %d).", pid)
                        sys.exit(0)
                    else:
                        self.log.error(
                            "PID file exist, but process %d appears stale", pid
                        )
                        sys.exit(1)
                else:
                    self.log.error("No pyrotorque process found.")
                    sys.exit(1)

            if self.options.stop or self.options.restart:
                if running:
                    os.kill(pid, signal.SIGTERM)
                    self.log.debug("Process %d sent SIGTERM.", pid)

                    # Wait for termination (max. 10 secs)
                    for _ in range(100):
                        if not pid_file.is_locked():
                            running = False
                            break
                        time.sleep(0.1)

                    self.log.info("Process %d stopped.", pid)
                elif pid:
                    self.log.info("Process %d NOT running anymore.", pid)
                else:
                    self.log.info("No pid file '%s'", (pid_file.path or "<N/A>"))
            else:
                self.log.info(
                    "Process %d %s running.", pid, "UP and" if running else "NOT"
                )

            if self.options.stop:
                self.return_code = error.EX_OK if running else error.EX_UNAVAILABLE
                return

        # Check if we only need to run once
        if self.options.run_once:
            params = self.jobs[self.options.run_once]
            if self.options.dry_run:
                params["dry_run"] = True
            # Make a copy here to prevent the original handler from
            # getting overwritten
            params["__handler_copy"] = params.get("__handler")(params)
            params["__handler_copy"].run()
            sys.exit(0)

        dcontext = DaemonContext(
            detach_process=False,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        # Set up for forking into the background, if not disabled via
        # the flag
        if not self.options.no_fork:
            dcontext.stdin = None
            if log_file is not None:
                log_file_handle = open(  # pylint: disable=consider-using-with
                    log_file, "w", encoding="utf-8"
                )
            else:
                log_file_handle = None
            dcontext.stderr = log_file_handle
            dcontext.stdout = log_file_handle
            dcontext.pidfile = pid_file
            if running and self.options.adopt_stale_pid_file and not pid_exists(pid):
                self.log.debug("Removing stale PID file")
                os.unlink(pid_file.path)
                with pid_file:
                    pass
            # Ensure we can lock the pid_file ahead of time
            try:
                with pid_file:
                    pass
            except (AlreadyLocked, LockFailed) as exc:
                self.log.error("Cannot lock pidfile: %s", exc)
                sys.exit(1)
            dcontext.detach_process = True
            self.log.info("Writing pid to %s and detaching process...", pid_file.path)
            self.log.info("Logging stderr/stdout to %r", log_file or "/dev/null")

        # Change logging format to something more daemon-like
        logging.basicConfig(
            force=True,
            format=config.settings.TORQUE._settings.get(
                "log_format", "%(asctime)s %(levelname)5s %(name)s: %(message)s"
            ),
        )
        self.log.setLevel(log_level)

        with dcontext:
            # Set up services
            self.sched = BackgroundScheduler()

            # Run services
            self.sched.start()
            try:
                self.add_jobs()
                self.run_forever()
            finally:
                if self.sched.running:
                    self.log.info("Shutting down scheduler...")
                    self.sched.shutdown()


def run():  # pragma: no cover
    """The entry point."""
    RtorrentQueueManager().run()


if __name__ == "__main__":
    run()
