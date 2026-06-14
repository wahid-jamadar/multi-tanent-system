import datetime as dt
import logging
import os
import sys
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from prometheus_flask_exporter import PrometheusMetrics
from pythonjsonlogger import jsonlogger

db = SQLAlchemy()
socketio = SocketIO()
metrics = PrometheusMetrics(app=None)
scheduler = BackgroundScheduler(timezone='UTC')

def setup_logger() -> logging.Logger:
    logger_inst = logging.getLogger('filebridge')
    logger_inst.setLevel(logging.INFO)
    if logger_inst.handlers:
        return logger_inst
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(user_id)s %(job_uuid)s')
    handler.setFormatter(formatter)
    logger_inst.addHandler(handler)
    return logger_inst

logger = setup_logger()
log_file_lock = threading.Lock()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMINAL_LOG_PATH = os.path.join(ROOT_DIR, 'terminal.log')

class TerminalLogTee:
    def __init__(self, original_stream, file_path):
        self.original_stream = original_stream
        self.file_path = file_path
        self.write_count = 0
        
    def write(self, message):
        self.original_stream.write(message)
        self.original_stream.flush()
        if not message:
            return
        
        with log_file_lock:
            self.write_count += 1
            if self.write_count >= 100:
                self.write_count = 0
                if os.path.exists(self.file_path):
                    if os.path.getsize(self.file_path) > 5242880:  # 5MB
                        try:
                            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                lines = f.readlines()
                            with open(self.file_path, 'w', encoding='utf-8') as f:
                                f.writelines(lines[-2000:])
                        except Exception:
                            try:
                                with open(self.file_path, 'w') as f:
                                    f.close()
                            except Exception:
                                pass
            try:
                with open(self.file_path, 'a', encoding='utf-8', errors='ignore') as f:
                    f.write(message)
            except Exception:
                pass

    def flush(self):
        self.original_stream.flush()

def setup_terminal_tee():
    if not hasattr(sys, '_terminal_tee_setup'):
        sys.stdout = TerminalLogTee(sys.stdout, TERMINAL_LOG_PATH)
        sys.stderr = TerminalLogTee(sys.stderr, TERMINAL_LOG_PATH)
        sys._terminal_tee_setup = True

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

def log_info(message, **context):
    from app.security.scoped_access import system_log
    level = context.get('level', 'INFO')
    component = context.get('component', 'system')
    system_log(level, component, message, context)

def log_error(message, **context):
    from app.security.scoped_access import system_log
    system_log('ERROR', context.get('component', 'system'), message, context)
