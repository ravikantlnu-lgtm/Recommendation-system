import json
import logging
import os
from datetime import datetime, timezone

from config import get_settings
from google.cloud import logging as cloud_logging
from google.cloud.logging.handlers import CloudLoggingHandler
from models import DefaultLog, ErrorLog
from pydantic import BaseModel

from models import DefaultLog, ErrorLog, ExceptionLog

settings = get_settings()


class BigQueryFormatter(logging.Formatter):
    def __init__(self, model: BaseModel, pretty: bool = False):
        super().__init__()
        self.model = model
        self.pretty = pretty  # Allow pretty-printing for local logs

    def format(self, record):
        log_entry = {
            "severity": record.levelname,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": record.getMessage(),
            "logger_name": record.name,
            "jsonPayload": self.model(
                **record.msg
            ).dict(),  # Parse the log message into model format
        }

        if self.pretty:
            # Pretty-print for local debugging
            print("=========== PRETTY PRINTING LOGS =================")
            return json.dumps(log_entry, indent=4)
        else:
            # Normal JSON output (for structured logging in production)
            print("=========== NOT PRETTY PRINTING LOGS =================")
            return json.dumps(log_entry)


def setup_logger(name, model: BaseModel, level=logging.INFO):
    # Initialize the Google Cloud Logging client
    client = cloud_logging.Client()

    # Create a Cloud Logging handler
    cloud_handler = CloudLoggingHandler(client)
    cloud_handler.setLevel(level)

    # Create a logger for your application
    logger = logging.getLogger(name)
    logger.setLevel(level)  # Set the logging level for your logger

    is_development = os.getenv("DEPLOYMENT", "dev") == "dev"

    # Create a formatter for BigQuery logs
    bq_formatter = BigQueryFormatter(model, pretty=is_development)
    cloud_handler.setFormatter(bq_formatter)

    # Attach the Cloud Logging handler
    logger.addHandler(cloud_handler)

    return logger


# Setup loggers
error_logger = setup_logger("error_logger", ErrorLog, level=logging.ERROR)
default_logger = setup_logger("default_logger", DefaultLog)


def log_error(
    log_message,
    function_name=None,
    endpoint=None,
    error_type=None,
    stack_trace=None,
    json_payload=None,
):
    error_log = ErrorLog(
        log_timestamp=datetime.now(timezone.utc).isoformat(),
        severity="ERROR",
        resource_type="cloud_run",
        resource_labels=[{"key": function_name, "value": endpoint}],
        log_name=f"projects/{settings.PROJECT_ID}/logs/error_log",
        log_message=log_message,
        error_type=error_type,
        stack_trace=stack_trace,
        json_payload=json_payload,
    )
    error_logger.error(error_log.dict(), exc_info=True)


def log_default(
    log_message,
    resource_type=None,
    resource_labels=None,
    log_name=None,
    json_payload=None,
):
    default_log = DefaultLog(
        log_timestamp=datetime.now(timezone.utc).isoformat(),
        resource_type=resource_type,
        resource_labels=resource_labels or [],
        log_name=log_name,
        log_message=log_message,
        json_payload=json_payload,
    )
    default_logger.info(default_log.dict())