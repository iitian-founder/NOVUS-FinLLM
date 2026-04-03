import logging
import json
import os
import datetime

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        
        # Include any extra attributes passed via `extra={"key": "value"}`
        for key, val in record.__dict__.items():
            if key not in {"args", "asctime", "created", "exc_info", "exc_text", 
                           "filename", "funcName", "levelname", "levelno", "lineno", 
                           "module", "msecs", "message", "msg", "name", "pathname", 
                           "process", "processName", "relativeCreated", "stack_info", "thread", "threadName"}:
                log_obj[key] = val
                
        # If there is an exception, include its traceback
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj)

def get_logger(name: str = "novus") -> logging.Logger:
    """
    Returns a configured structured logger.
    Uses JSON standard out formatting in production.
    """
    logger = logging.getLogger(name)
    
    # Only configure if it doesn't already have handlers
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        handler = logging.StreamHandler()
        # You can toggle JSON vs standard formatting based on ENV var
        if os.getenv("ENVIRONMENT") == "production" or os.getenv("LOG_FORMAT") == "json":
            handler.setFormatter(JSONFormatter())
        else:
            # Human readable for local dev
            formatter = logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ"
            )
            handler.setFormatter(formatter)
            
        logger.addHandler(handler)
        
    return logger
