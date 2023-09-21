import datetime
import logging
from queue import Empty, Queue
from threading import Thread


class SafeLogger:
    _filename: str = None

    def __init__(self, filename: str = None, write_mode: str = None):
        """
        SafeLogger provides a mechanism to thread-safely log
        if initialized with a filename and optionally with a write mode
        (default is w+) otherwise will work as a wrapper around the logging
        package.
        The double working mechanism is meant to not force file logging to
        the methods that depend on it.

        :param filename: the log file name, if `None` the class will behave as
            a simple logger
        :param write_mode: file write mode, default is `w+`
        """
        if filename is not None:
            self._filename = filename
            if write_mode is None:
                write_mode = "w+"
            self.filewriter = open(filename, write_mode)
            self.queue = Queue()
            self.finished = False
            Thread(
                name="SafeLogWriter", target=self.write_worker, daemon=True
            ).start()
        else:
            self.filewriter = None
            self.finished = True

    def _write(self, data: str):
        """
        Enqueues messages that will be safely consumed
        by the logging thread

        :param data: The message that will be enqueued
        """
        if self.filewriter and self.queue:
            self.queue.put(data)

    def error(self, data: str):
        """
        Safely logs an Error in the logfile if the object has been
        instantiated with a filename, otherwise logs an error using
        the standard log mechanism

        :param data: the log message
        """
        if self.filewriter and not self.finished:
            self._write(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} '
                f"[ERR] {data}"
            )
        else:
            import logging

            logging.error(data)

    def warning(self, data: str):
        """
        Safely logs a Warning in the logfile if the object has been
        instantiated with a filename, otherwise logs a Warning using
        the standard log mechanism

        :param data: the log message
        """
        if self.filewriter and not self.finished:
            self._write(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} '
                f"[WRN] {data}"
            )
        else:
            logging.warning(data)

    def info(self, data: str):
        """
        Safely logs an Info in the logfile if the object has been
        instantiated with a filename, otherwise logs an Info using
        the standard log mechanism

        :param data: the log message
        """
        if self.filewriter and not self.finished:
            self._write(
                f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} '
                f"[INF] {data}"
            )
        else:
            logging.info(data)

    @property
    def log_file_name(self):
        return self._filename

    def write_worker(self):
        """
        Consumer thread to log on a file
        """
        while not self.finished:
            try:
                data = self.queue.get(True)
            except Empty:
                continue
            self.filewriter.write(f"{data}\n")
            self.filewriter.flush()
            self.queue.task_done()

    def close(self):
        """
        Waits all the messages to be consumed, kills the thread
        and closes the file writer
        """
        self.queue.join()
        self.finished = True
        self.filewriter.close()
