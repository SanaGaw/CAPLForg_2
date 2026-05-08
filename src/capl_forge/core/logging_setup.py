"""Logging setup with QueueHandler for thread safety."""
import logging
import queue
import threading

def setup_logging(log_level: int = logging.INFO) -> logging.Logger:
    """Set up logging with a QueueHandler for thread-safe logging."""
    log_queue = queue.Queue()
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    queue_handler.setFormatter(formatter)

    listener = logging.handlers.QueueListener(
        log_queue, logging.StreamHandler()
    )
    listener.start()

    logger = logging.getLogger("capl_forge")
    logger.addHandler(queue_handler)
    logger.setLevel(log_level)
    return logger
