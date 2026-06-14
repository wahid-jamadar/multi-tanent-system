# FileBridge Agent - Updated May 26, 2026
import hashlib
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import platform
from pathlib import Path
import queue
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import zipfile

import psutil
import requests
import urllib3
import yaml

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # watchdog is optional until installed on existing agents
    FileSystemEventHandler = object
    Observer = None

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except Exception:
    win32serviceutil = None
    win32service = None
    win32event = None
    servicemanager = None


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPT_PATH = Path(SCRIPT_DIR)
CONFIG_FILE = str(SCRIPT_PATH / "config.yaml")
STATE_DIR = SCRIPT_PATH / "state"
LOG_DIR = SCRIPT_PATH / "logs"
QUEUE_FILE = STATE_DIR / "operation_queue.jsonl"
CHUNK_SIZE = 1024 * 1024
MAX_CHUNK_RETRIES = 3
PLACEHOLDER_UUIDS = {"", "00000000-0000-0000-0000-000000000000", "replace-agent-uuid"}
AGENT_VERSION = "1.5.2"
STARTED_AT = time.monotonic()
_LAST_NET = {"time": time.monotonic(), "sent": 0, "recv": 0}


def setup_logging(level=logging.INFO):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = str(LOG_DIR / "agent.log")
    
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    
    # Clear existing handlers
    for h in root.handlers[:]:
        root.removeHandler(h)
        
    if not running_as_service():
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)
    
    file_h = TimedRotatingFileHandler(log_file, when="midnight", backupCount=14, encoding="utf-8")
    file_h.setFormatter(formatter)
    root.addHandler(file_h)
    
    # Quieten noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def running_as_service():
    return bool(os.environ.get("FILEBRIDGE_SERVICE")) or (win32serviceutil is not None and "PythonService.exe" in sys.executable)


setup_logging()


def default_base_path():
    return "C:\\" if platform.system() == "Windows" else "/"


def detect_ip_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "172.100.30.191"


def detect_drives():
    drives = []
    if platform.system() == "Windows":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append(root)
    else:
        drives.append("/")
    return drives


def machine_fingerprint():
    raw = "|".join(
        [
            socket.gethostname(),
            platform.system(),
            platform.node(),
            platform.machine(),
            str(uuid.getnode()),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_config(config):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    backup = Path(CONFIG_FILE + ".bak")
    if Path(CONFIG_FILE).exists():
        try:
            shutil.copy2(CONFIG_FILE, backup)
        except Exception:
            pass
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        base = default_base_path()
        config = {
            "backend_url": os.environ.get("FILEBRIDGE_SERVER_URL", "https://172.100.30.191:5001"),
            "bootstrap_token": "replace-bootstrap-token",
            "agent_uuid": "",
            "agent_token": "",
            "agent": {"id": "", "token": "", "name": socket.gethostname()},
            "server": {"url": os.environ.get("FILEBRIDGE_SERVER_URL", "https://172.100.30.191:5001")},
            "sync": {"folders": [base], "rules": []},
            "monitoring": {"heartbeat_interval": 30},
            "transfer": {"chunk_size": CHUNK_SIZE, "retry_limit": 5, "compression": True, "encryption": True},
            "machine_fingerprint": "",
            "heartbeat_interval": 30,
            "server_name": socket.gethostname(),
            "base_path": base,
            "allowed_paths": [base],
            "log_level": "INFO",
        }
        save_config(config)
    else:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    changed = False
    config.setdefault("agent", {})
    config.setdefault("server", {})
    config.setdefault("sync", {})
    config.setdefault("monitoring", {})
    config.setdefault("transfer", {})
    if not config.get("backend_url"):
        if config["server"].get("url"):
            config["backend_url"] = config["server"]["url"]
            changed = True
        elif config.get("url"):
            config["backend_url"] = config["url"]
            changed = True

    if config.get("backend_url") and not config["server"].get("url"):
        config["server"]["url"] = config["backend_url"]
        changed = True
    if config["server"].get("url") and config.get("backend_url") != config["server"]["url"]:
        config["backend_url"] = config["server"]["url"]
        changed = True
    if not config.get("server_name"):
        config["server_name"] = socket.gethostname()
        changed = True
    if not config.get("base_path") or (platform.system() != "Windows" and config.get("base_path") == "C:\\"):
        config["base_path"] = default_base_path()
        changed = True
    # Automatically detect all drive letters on Windows if allowed_paths/sync.folders is empty or defaults to C:\
    drives = None
    if platform.system() == "Windows":
        drives = [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{letter}:\\")]

    if not config.get("allowed_paths") or config.get("allowed_paths") == ["C:\\"]:
        config["allowed_paths"] = drives or [config.get("base_path") or default_base_path()]
        changed = True
    if not config["sync"].get("folders") or config["sync"].get("folders") == ["C:\\"]:
        config["sync"]["folders"] = config.get("allowed_paths") or [config["base_path"]]
        changed = True
    if not config["monitoring"].get("heartbeat_interval"):
        config["monitoring"]["heartbeat_interval"] = int(config.get("heartbeat_interval", 30))
        changed = True
    config["heartbeat_interval"] = int(config["monitoring"].get("heartbeat_interval", 30))
    if not config.get("machine_fingerprint"):
        config["machine_fingerprint"] = machine_fingerprint()
        changed = True

    # First-run identity must be generated locally and never shipped in templates.
    if str(config.get("agent_uuid", "")).lower() in PLACEHOLDER_UUIDS:
        config["agent_uuid"] = str(uuid.uuid4())
        config["agent_token"] = ""
        config["agent"]["id"] = config["agent_uuid"]
        config["agent"]["token"] = ""
        changed = True
    if not config["agent"].get("id"):
        config["agent"]["id"] = config["agent_uuid"]
    if config.get("agent_token") and not config["agent"].get("token"):
        config["agent"]["token"] = config["agent_token"]

    if changed:
        save_config(config)
    
    # Apply configured log level
    log_level = getattr(logging, str(config.get("log_level", "INFO")).upper(), logging.INFO)
    setup_logging(log_level)
    return config


def reset_identity(config, reason):
    logging.warning("Regenerating agent identity: %s", reason)
    config["agent_uuid"] = str(uuid.uuid4())
    config["agent_token"] = ""
    config["machine_fingerprint"] = machine_fingerprint()
    save_config(config)
    return config


def post_progress(config, job_uuid, transferred_bytes, total_bytes, message):
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    payload = {
        "transferred_bytes": int(transferred_bytes),
        "total_bytes": int(total_bytes or 0),
        "progress_percent": round((transferred_bytes / total_bytes) * 100, 2) if total_bytes else 0,
        "message": message,
    }
    if not hasattr(post_progress, "_started"):
        post_progress._started = {}
    started = post_progress._started.setdefault(job_uuid, time.time())
    elapsed = max(time.time() - started, 0.001)
    speed = int(transferred_bytes / elapsed)
    payload["transfer_speed_bps"] = speed
    payload["eta_seconds"] = int(((total_bytes or 0) - transferred_bytes) / speed) if speed and total_bytes else None
    try:
        requests.post(
            f"{config['backend_url'].rstrip('/')}/api/agents/jobs/{job_uuid}/progress",
            json=payload,
            headers=headers,
            verify=False,
            timeout=10,
        )
    except Exception as exc:
        logging.warning("Progress update failed for %s: %s", job_uuid, exc)


def send_result(config, job_uuid, status, message, result=None, bytes_transferred=0, checksum_sha256=None):
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    payload = {
        "status": status,
        "message": message,
        "result": result or {},
        "bytes_transferred": int(bytes_transferred or 0),
        "checksum_sha256": checksum_sha256,
    }
    try:
        requests.post(
            f"{config['backend_url'].rstrip('/')}/api/agents/jobs/{job_uuid}/result",
            json=payload,
            headers=headers,
            verify=False,
            timeout=10,
        )
    except Exception as exc:
        logging.error("Failed to send job result: %s", exc)


def allowed_roots(config):
    roots = config.get("allowed_paths") or [config.get("base_path") or default_base_path()]
    if "all" in roots:
        return []
    return [os.path.abspath(os.path.expanduser(root)) for root in roots if root]


def is_safe_path(path, config):
    if not path or path.startswith("SERVER_RELAY:"):
        return True
    roots = allowed_roots(config)
    if not roots:  # "all" or empty means allow everything
        return True
    try:
        target = os.path.abspath(os.path.expanduser(path))
        for root in roots:
            try:
                if os.path.commonpath([root, target]) == root:
                    return True
            except ValueError:
                continue
    except Exception:
        return False
    return False


def ensure_safe_path(path, config, purpose):
    if not is_safe_path(path, config):
        raise PermissionError(f"{purpose} path is outside configured base paths: {path}")


def calculate_sha256(file_path):
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            sha.update(chunk)
    return sha.hexdigest()


def file_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            total += os.path.getsize(os.path.join(root, name))
    return total


def safe_name(name):
    cleaned = os.path.basename(str(name).replace("\\", os.sep).replace("/", os.sep))
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Invalid filename")
    return cleaned


def safe_extract_zip(zip_file, extract_path):
    base = os.path.abspath(extract_path)
    with zipfile.ZipFile(zip_file, "r") as z:
        for member in z.infolist():
            if member.filename.startswith("/") or member.filename.startswith("\\") or ".." in member.filename.split("/"):
                raise PermissionError(f"Unsafe ZIP member blocked: {member.filename}")
            target_path = os.path.abspath(os.path.join(base, member.filename))
            if os.path.commonpath([base, target_path]) != base:
                raise PermissionError(f"Zip Slip attempt blocked: {member.filename}")
        z.extractall(base)
        for member in z.infolist():
            target_path = os.path.abspath(os.path.join(base, member.filename))
            if os.path.isfile(target_path):
                try:
                    date_time = member.date_time + (0, 0, -1)
                    mtime = time.mktime(date_time)
                    os.utime(target_path, (mtime, mtime))
                except Exception:
                    pass


def make_zip(source, job_uuid, config):
    archive_path = os.path.join(tempfile.gettempdir(), f"{job_uuid}.zip")
    source = os.path.abspath(source)
    total = max(file_size(source), 1)
    sent = 0
    # Store paths relative to the selected folder itself, not its parent, so extraction
    # recreates the original contents exactly once under the requested destination.
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(source):
            rel_root = os.path.relpath(root, source)
            if rel_root != "." and not files and not dirs:
                z.write(root, rel_root + "/")
            for filename in files:
                fp = os.path.join(root, filename)
                arcname = os.path.relpath(fp, source)
                z.write(fp, arcname)
                sent += os.path.getsize(fp)
                post_progress(config, job_uuid, sent, total, "Packaging folder")
    return archive_path


def file_row(path, base_path=None, include_checksum=False):
    rel_path = os.path.relpath(path, base_path) if base_path else (os.path.basename(path) or path)
    rel_path = rel_path.replace("\\", "/")
    try:
        stat = os.stat(path)
        is_dir = os.path.isdir(path)
        row = {
            "name": os.path.basename(path) or path,
            "path": path,
            "rel_path": rel_path,
            "is_dir": is_dir,
            "size": None if is_dir else stat.st_size,
            "modified_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            "mtime": stat.st_mtime
        }
        if include_checksum and not is_dir:
            try:
                row["checksum_sha256"] = calculate_sha256(path)
            except Exception as exc:
                row["checksum_error"] = str(exc)
        return row
    except Exception as exc:
        return {
            "name": os.path.basename(path) or path, 
            "path": path, 
            "rel_path": rel_path,
            "is_dir": False, 
            "size": None, 
            "error": str(exc)
        }


def validate_path(path, expect_exists=False, expect_writable=False):
    result = {
        "path": path,
        "exists": os.path.exists(path),
        "is_dir": os.path.isdir(path),
        "is_file": os.path.isfile(path),
        "writable": False,
    }
    if expect_exists and not result["exists"]:
        result["error"] = f"Path not found: {path}"
        return result
    writable_target = path if result["is_dir"] else os.path.dirname(path) or path
    while writable_target and not os.path.exists(writable_target):
        parent = os.path.dirname(writable_target)
        if parent == writable_target:
            break
        writable_target = parent
    result["writable"] = bool(writable_target and os.access(writable_target, os.W_OK))
    if expect_writable and not result["writable"]:
        result["error"] = f"Destination is not writable: {path}"
    return result


def resolve_destination(destination, filename, destination_is_dir=False, source_is_dir=False):
    destination = destination or "."
    filename = safe_name(filename)
    explicit_dir = bool(destination_is_dir or source_is_dir)
    if explicit_dir:
        os.makedirs(destination, exist_ok=True)
        return os.path.join(destination, filename) if not source_is_dir else destination
    if os.path.isdir(destination):
        return os.path.join(destination, filename)
    parent = os.path.dirname(destination)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return destination


def copy_file_chunked(src, dst, config, job_uuid, total, offset=0, progress_base=0):
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    mode = "ab" if offset else "wb"
    done = offset
    with open(src, "rb") as fin, open(dst, mode) as fout:
        if offset:
            fin.seek(offset)
        while True:
            chunk = fin.read(CHUNK_SIZE)
            if not chunk:
                break
            fout.write(chunk)
            done += len(chunk)
            post_progress(config, job_uuid, progress_base + done, total, "Copying file")
    shutil.copystat(src, dst)
    return done


def sync_paths(source, destination, config, job_uuid, overwrite=True):
    ensure_safe_path(source, config, "Source")
    ensure_safe_path(destination, config, "Destination")
    if not os.path.exists(source):
        raise FileNotFoundError(f"Source not found: {source}")

    total = max(file_size(source), 1)
    copied = 0
    changed = []
    if os.path.isfile(source):
        target = resolve_destination(destination, os.path.basename(source), os.path.isdir(destination))
        if overwrite or not os.path.exists(target):
            if os.path.exists(target) and calculate_sha256(source) == calculate_sha256(target):
                return {"destination_path": target, "changed": []}, 0, calculate_sha256(source)
            copied = copy_file_chunked(source, target, config, job_uuid, total)
            if calculate_sha256(source) != calculate_sha256(target):
                raise IOError(f"Checksum mismatch after sync: {target}")
            changed.append(target)
        return {"destination_path": target, "changed": changed}, copied, calculate_sha256(source)

    os.makedirs(destination, exist_ok=True)
    for root, _dirs, files in os.walk(source):
        rel_root = os.path.relpath(root, source)
        target_root = destination if rel_root == "." else os.path.join(destination, rel_root)
        os.makedirs(target_root, exist_ok=True)
        for name in files:
            src = os.path.join(root, name)
            dst = os.path.join(target_root, name)
            src_hash = calculate_sha256(src)
            if os.path.exists(dst) and calculate_sha256(dst) == src_hash:
                copied += os.path.getsize(src)
                post_progress(config, job_uuid, copied, total, "Syncing folder")
                continue
            if overwrite or not os.path.exists(dst):
                copy_file_chunked(src, dst, config, job_uuid, total, progress_base=copied)
                if calculate_sha256(dst) != src_hash:
                    raise IOError(f"Checksum mismatch after sync: {dst}")
                changed.append(dst)
            copied += os.path.getsize(src)
            post_progress(config, job_uuid, copied, total, "Syncing folder")
    return {"destination_path": destination, "changed": changed}, copied, None


def upload_with_retries(config, job_uuid, upload_target, upload_name, checksum, source_is_dir=False):
    size = os.path.getsize(upload_target)
    headers = {
        "Authorization": f"Bearer {config['agent_token']}",
    }
    backend_url = config['backend_url'].rstrip('/')
    
    # 1. Fetch current upload offset from the server (for resumable uploads)
    offset = 0
    try:
        response = requests.get(
            f"{backend_url}/api/agents/jobs/{job_uuid}/upload",
            headers=headers,
            verify=False,
            timeout=15
        )
        if response.status_code == 200:
            res_data = response.json()
            offset = res_data.get("uploaded_bytes", 0)
            logging.info("Resumable upload: Server reported offset %s of %s", offset, size)
    except Exception as exc:
        logging.warning("Failed to fetch upload offset for %s: %s. Starting from 0.", job_uuid, exc)
        offset = 0

    if offset > size:
        offset = 0
    elif offset == size:
        logging.info("Upload for %s already fully present on server.", job_uuid)
        return {"ok": True, "checksum_sha256": checksum}

    # 2. Chunk upload loop
    chunk_size = config.get("transfer", {}).get("chunk_size", CHUNK_SIZE)
    CHUNK_TIMEOUT = 600
    
    logging.info("Starting chunked upload for %s starting from offset %s with chunk_size %s", job_uuid, offset, chunk_size)
    
    with open(upload_target, "rb") as f:
        while offset < size:
            f.seek(offset)
            chunk_data = f.read(chunk_size)
            if not chunk_data:
                break
                
            chunk_len = len(chunk_data)
            
            chunk_headers = {
                "Authorization": f"Bearer {config['agent_token']}",
                "X-Upload-Offset": str(offset),
                "X-Chunk-Size": str(chunk_len),
                "X-File-Size": str(size),
                "X-Original-Filename": upload_name,
                "X-Source-Is-Dir": "1" if source_is_dir else "0",
                "X-SHA256": checksum,
            }
            
            chunk_posted = False
            for attempt in range(1, MAX_CHUNK_RETRIES + 1):
                try:
                    response = requests.post(
                        f"{backend_url}/api/agents/jobs/{job_uuid}/upload",
                        headers=chunk_headers,
                        files={"file": (upload_name, chunk_data, "application/octet-stream")},
                        verify=False,
                        timeout=CHUNK_TIMEOUT,
                    )
                    response.raise_for_status()
                    
                    res_json = response.json()
                    chunk_posted = True
                    offset = res_json.get("uploaded_bytes", offset + chunk_len)
                    
                    post_progress(config, job_uuid, offset, size, "Uploading relay file")
                    break
                except Exception as exc:
                    logging.warning("Upload chunk at offset %s failed (attempt %s/%s): %s", offset, attempt, MAX_CHUNK_RETRIES, exc)
                    time.sleep(attempt * 2)
                    
            if not chunk_posted:
                raise IOError(f"Upload failed at offset {offset} after retries")
                
    post_progress(config, job_uuid, size, size, "Upload complete")
    return {"ok": True, "checksum_sha256": checksum}



class PersistentOperationQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, operation):
        operation.setdefault("operation_uuid", str(uuid.uuid4()))
        operation.setdefault("timestamp", time.time())
        operation.setdefault("retry_count", 0)
        operation.setdefault("status", "queued")
        with self.lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(operation, ensure_ascii=False) + "\n")

    def load(self):
        if not self.path.exists():
            return []
        rows = []
        with self.lock, self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def replace(self, rows):
        tmp = self.path.with_suffix(".tmp")
        with self.lock, tmp.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)


class FileBridgeEventHandler(FileSystemEventHandler):
    def __init__(self, operation_queue):
        self.operation_queue = operation_queue

    def on_any_event(self, event):
        if getattr(event, "is_directory", False) and event.event_type == "modified":
            return
        path = os.path.abspath(getattr(event, "src_path", ""))
        if not path or path.endswith(".filebridge_tmp"):
            return
        operation_type = {
            "created": "created",
            "modified": "modified",
            "deleted": "deleted",
            "moved": "renamed",
        }.get(event.event_type, event.event_type)
        payload = {
            "operation_type": operation_type,
            "path": path,
            "destination_path": os.path.abspath(getattr(event, "dest_path", "")) if getattr(event, "dest_path", None) else "",
            "is_directory": bool(getattr(event, "is_directory", False)),
            "size_bytes": os.path.getsize(path) if os.path.isfile(path) else 0,
        }
        self.operation_queue.append(payload)


def start_watchers(config, operation_queue):
    if Observer is None:
        logging.warning("watchdog is not installed; realtime folder monitoring disabled")
        return None
    observer = Observer()
    folders = config.get("sync", {}).get("folders") or config.get("allowed_paths") or []
    for folder in folders:
        if folder == "all":
            continue
        folder = os.path.abspath(os.path.expanduser(str(folder)))
        if os.path.isdir(folder):
            # Do not monitor system root recursively to avoid inotify limitations/system folders
            is_root = (folder == "/" or folder.lower() == "c:\\")
            recursive = not is_root
            try:
                observer.schedule(FileBridgeEventHandler(operation_queue), folder, recursive=recursive)
                logging.info("Monitoring folder: %s (recursive=%s)", folder, recursive)
            except Exception as e:
                logging.error("Failed to schedule monitoring for %s: %s", folder, e)
    if not observer.emitters:
        logging.warning("No valid sync folders configured for watchdog monitoring")
        return None
    observer.daemon = True
    try:
        observer.start()
    except Exception as e:
        logging.error("Failed to start watchdog observer: %s", e)
        return None
    return observer


def flush_operation_queue(config, operation_queue):
    rows = operation_queue.load()
    if not rows:
        return 0
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    try:
        response = requests.post(
            f"{config['backend_url'].rstrip('/')}/api/agents/events",
            json={"events": rows[:100]},
            headers=headers,
            verify=False,
            timeout=10,
        )
        if response.status_code == 401:
            register_agent(force=True)
            return 0
        response.raise_for_status()
        accepted = int(response.json().get("accepted", 0))
        operation_queue.replace(rows[accepted:])
        return accepted
    except Exception as exc:
        logging.warning("Operation queue flush failed: %s", exc)
        return 0


def collect_telemetry(config, queue_depth=0, current_transfers=0):
    global _LAST_NET
    net = psutil.net_io_counters()
    now = time.monotonic()
    elapsed = max(now - _LAST_NET["time"], 1)
    network_speed = ((net.bytes_sent - _LAST_NET["sent"]) + (net.bytes_recv - _LAST_NET["recv"])) / elapsed
    _LAST_NET = {"time": now, "sent": net.bytes_sent, "recv": net.bytes_recv}
    disk_path = config.get("base_path") or default_base_path()
    try:
        disk = psutil.disk_usage(disk_path)
        disk_percent = disk.percent
    except Exception:
        disk_percent = 0
    return {
        "agent_uuid": config["agent_uuid"],
        "machine_fingerprint": config.get("machine_fingerprint"),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": disk_percent,
        "network_speed_bps": int(network_speed),
        "network_bytes_sent": net.bytes_sent,
        "network_bytes_recv": net.bytes_recv,
        "online_status": "online",
        "current_transfers": current_transfers,
        "queue_depth": queue_depth,
        "uptime_seconds": int(time.monotonic() - STARTED_AT),
        "drives": detect_drives(),
    }


def download_with_retries(config, job_uuid, tmp_path, expected_size=0):
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    offset = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
    if expected_size and offset > expected_size:
        os.remove(tmp_path)
        offset = 0
    # 12-hour timeout: generous upper bound for very large files over slow links
    DOWNLOAD_TIMEOUT = 43200
    for attempt in range(1, MAX_CHUNK_RETRIES + 1):
        try:
            if expected_size and offset == expected_size:
                post_progress(config, job_uuid, offset, expected_size, "Download already complete")
                return offset
            req_headers = dict(headers)
            if offset:
                req_headers["Range"] = f"bytes={offset}-"
            response = requests.get(
                f"{config['backend_url'].rstrip('/')}/api/agents/jobs/{job_uuid}/download",
                headers=req_headers,
                verify=False,
                stream=True,
                timeout=DOWNLOAD_TIMEOUT,
            )
            response.raise_for_status()
            if offset and response.status_code != 206:
                logging.warning(
                    "Server ignored range request for %s at offset %s; restarting download",
                    job_uuid,
                    offset,
                )
                offset = 0
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            mode = "ab" if offset else "wb"
            with open(tmp_path, mode) as fout:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        fout.write(chunk)
                        offset += len(chunk)
                        post_progress(config, job_uuid, offset, expected_size, "Downloading relay file")
            if expected_size and offset != expected_size:
                raise IOError(f"Incomplete download: received {offset} of {expected_size} bytes")
            return offset
        except Exception as exc:
            logging.warning("Download retry %s/%s for %s failed: %s", attempt, MAX_CHUNK_RETRIES, job_uuid, exc)
            offset = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
            if expected_size and offset > expected_size:
                os.remove(tmp_path)
                offset = 0
            time.sleep(attempt * 2)
    raise IOError("Download failed after retries")


def register_agent(force=False):
    config = load_config()
    if config.get("agent_token") and not force:
        return config

    payload = {
        "bootstrap_token": config.get("bootstrap_token", "replace-bootstrap-token"),
        "agent_uuid": config["agent_uuid"],
        "machine_fingerprint": config.get("machine_fingerprint") or machine_fingerprint(),
        "server_name": config.get("server_name", socket.gethostname()),
        "agent_name": config.get("server_name", socket.gethostname()),
        "hostname": socket.gethostname(),
        "ip_address": detect_ip_address(),
        "os_type": platform.system().lower(),
        "os_info": f"{platform.system()} {platform.release()} {platform.version()}",
        "protocol": "winrm" if platform.system() == "Windows" else "ssh",
        "port": 5985 if platform.system() == "Windows" else 22,
        "base_path": config.get("base_path") or default_base_path(),
        "version": AGENT_VERSION,
        "uptime_seconds": int(time.monotonic() - STARTED_AT),
        "install_dir": SCRIPT_DIR,
        "drives": detect_drives(),
        "sync_folders": config.get("sync", {}).get("folders") or config.get("allowed_paths") or [],
        "capabilities": ["filesystem", "python", "copy", "move", "sync", "browse", "validate", "checksum", "resumable", "watchdog", "service", "telemetry"],
    }

    try:
        response = requests.post(f"{config['backend_url'].rstrip('/')}/api/agents/register", json=payload, verify=False, timeout=10)
        if response.status_code == 409:
            config = reset_identity(config, "backend reported duplicate UUID collision")
            return register_agent()
        response.raise_for_status()
        data = response.json()
        config["agent_token"] = data["agent_token"]
        config["agent_uuid"] = data.get("agent_uuid", config["agent_uuid"])
        config["agent"]["id"] = config["agent_uuid"]
        config["agent"]["token"] = config["agent_token"]
        config["heartbeat_interval"] = int(data.get("heartbeat_interval") or config.get("heartbeat_interval", 30))
        config["monitoring"]["heartbeat_interval"] = config["heartbeat_interval"]
        save_config(config)
        logging.info("Registered successfully.")
        return config
    except Exception as exc:
        logging.error("Registration failed: %s", exc)
        return None


def send_heartbeat(config, operation_queue=None, current_transfers=0):
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    queue_depth = len(operation_queue.load()) if operation_queue else 0
    payload = collect_telemetry(config, queue_depth=queue_depth, current_transfers=current_transfers)
    payload["running_jobs"] = current_transfers
    try:
        response = requests.post(f"{config['backend_url'].rstrip('/')}/api/agents/heartbeat", json=payload, headers=headers, verify=False, timeout=5)
        if response.status_code == 409:
            reset_identity(config, "heartbeat duplicate UUID collision")
            return
        if response.status_code == 401:
            logging.error("Authentication failed (401). Attempting re-registration...")
            register_agent(force=True)
            return
        response.raise_for_status()
        logging.info("Heartbeat sent successfully")
    except Exception as exc:
        logging.error("Heartbeat failed: %s", exc)


def refresh_runtime_config(config):
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    try:
        response = requests.get(f"{config['backend_url'].rstrip('/')}/api/agents/config", headers=headers, verify=False, timeout=10)
        if response.status_code == 401:
            register_agent(force=True)
            return config
        response.raise_for_status()
        data = response.json()
        folders = [row["path"] for row in data.get("folders", []) if row.get("path")]
        if folders:
            config.setdefault("sync", {})["folders"] = folders
            config["allowed_paths"] = folders
        transfer = data.get("transfer") or {}
        if transfer:
            config.setdefault("transfer", {}).update(transfer)
        save_config(config)
    except Exception as exc:
        logging.warning("Runtime config refresh failed: %s", exc)
    return config


def check_for_updates(config):
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    try:
        response = requests.get(f"{config['backend_url'].rstrip('/')}/api/agents/update", headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        manifest = response.json()
        if manifest.get("version") and manifest.get("version") != AGENT_VERSION and manifest.get("download_url"):
            logging.info("Update available: %s -> %s", AGENT_VERSION, manifest["version"])
            # Production installers can replace the executable from a supervisor process.
            # The agent records the manifest now and leaves rollback-safe replacement to the service wrapper.
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with (STATE_DIR / "pending_update.json").open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
    except Exception as exc:
        logging.debug("Update check failed: %s", exc)


def execute_job(config, job):
    job_uuid = job.get("job_uuid")
    job_type = job.get("job_type")
    source = job.get("source_path", "")
    destination = job.get("destination_path") or ""
    source_server_id = job.get("source_server_id")
    destination_server_id = job.get("destination_server_id")
    destination_is_dir = bool(job.get("destination_is_dir"))
    overwrite = bool(job.get("overwrite", True))

    logging.info("transfer_start job=%s type=%s src=%s dst=%s", job_uuid, job_type, source, destination)

    try:
        if source.startswith("SERVER_RELAY:"):
            # Robust extraction of relay_uuid
            parts = source.split(":")
            relay_uuid = parts[1] if len(parts) >= 2 else job_uuid
            
            # Use dedicated fields from payload for filename and type
            orig_filename = job.get("original_filename") or (parts[2] if len(parts) >= 3 else "file")
            # The server sends source_is_dir as a boolean in the payload
            is_directory = bool(job.get("source_is_dir", False))
            
            expected_checksum = job.get("checksum_sha256")
            expected_size = int(job.get("total_bytes") or 0)
            ensure_safe_path(destination, config, "Destination")
            save_path = resolve_destination(destination, orig_filename, destination_is_dir, is_directory)
            tmp_path = save_path + ".filebridge_tmp"
            bytes_done = download_with_retries(config, job_uuid, tmp_path, expected_size)
            actual_checksum = calculate_sha256(tmp_path)
            if expected_checksum and expected_checksum.lower() != actual_checksum.lower():
                os.remove(tmp_path)
                logging.error("checksum_mismatch job=%s expected=%s actual=%s", job_uuid, expected_checksum, actual_checksum)
                send_result(config, job_uuid, "failed", "Integrity failure: checksum mismatch.", bytes_transferred=bytes_done)
                return
            if is_directory:
                os.makedirs(save_path, exist_ok=True)
                safe_extract_zip(tmp_path, save_path)
                os.remove(tmp_path)
                send_result(config, job_uuid, "success", "Folder download completed.", {"path": save_path}, bytes_done, actual_checksum)
            else:
                os.replace(tmp_path, save_path)
                original_mtime = job.get("original_mtime")
                if original_mtime is not None:
                    try:
                        os.utime(save_path, (original_mtime, original_mtime))
                    except Exception as exc:
                        logging.warning("Failed to preserve mtime for %s: %s", save_path, exc)
                send_result(config, job_uuid, "success", "File download completed.", {"path": save_path}, bytes_done, actual_checksum)
            return

        if job_type == "list":
            # Automatically redirect unsafe paths to the first allowed root
            roots = allowed_roots(config)
            if not is_safe_path(source, config) or source in {"", "/", "\\"}:
                if roots:
                    if platform.system() == "Windows" and source in {"", "/", "\\"}:
                        pass
                    else:
                        source = roots[0]
                else:
                    if platform.system() == "Windows" and source in {"", "/", "\\"}:
                        pass
                    else:
                        source = default_base_path()
            
            # Only enforce safety checks for non-drive-listing targets on Windows
            if not (platform.system() == "Windows" and source in {"", "/", "\\"}):
                ensure_safe_path(source, config, "Browse")

            recursive = bool(job.get("recursive", False))
            
            files = []
            if platform.system() == "Windows" and source in {"", "/", "\\"}:
                allowed_drives = set()
                if roots:
                    for r in roots:
                        drive = os.path.splitdrive(r)[0].upper()
                        if drive:
                            allowed_drives.add(drive)
                
                drive_list = []
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    drive_path = f"{letter}:\\"
                    if os.path.exists(drive_path):
                        if roots and f"{letter}:" not in allowed_drives:
                            continue
                        drive_list.append({
                            "name": drive_path,
                            "path": drive_path,
                            "is_dir": True,
                            "size": None,
                            "modified_at": ""
                        })
                files = drive_list
            else:
                if not os.path.exists(source):
                    send_result(config, job_uuid, "failed", f"Path not found: {source}")
                    return
                
                if recursive:
                    # Full recursive scan
                    for root, dirs, filenames in os.walk(source):
                        # Add directory itself (except the root source if it's already included)
                        if root != source:
                            files.append(file_row(root, source))
                        
                        for name in filenames:
                            fp = os.path.join(root, name)
                            row = file_row(fp, source, include_checksum=True)
                            files.append(row)
                else:
                    entries = sorted(os.listdir(source), key=lambda n: (not os.path.isdir(os.path.join(source, n)), n.lower()))
                    files = [file_row(os.path.join(source, name)) for name in entries]
            
            send_result(config, job_uuid, "success", "Files loaded.", {"path": source, "files": files})
            return

        if job_type == "validate":
            ensure_safe_path(source, config, "Validate")
            result = validate_path(source, job.get("expect_exists"), job.get("expect_writable"))
            status = "failed" if result.get("error") else "success"
            send_result(config, job_uuid, status, result.get("error") or "Path validated.", result)
            return

        if job_type == "mkdir":
            ensure_safe_path(source, config, "Create folder")
            os.makedirs(source, exist_ok=True)
            send_result(config, job_uuid, "success", "Folder created.", {"path": source})
            return

        if job_type == "delete":
            ensure_safe_path(source, config, "Delete")
            if not os.path.exists(source):
                send_result(config, job_uuid, "success", "Item already absent.", {"path": source, "already_absent": True})
                return
            shutil.rmtree(source) if os.path.isdir(source) else os.remove(source)
            send_result(config, job_uuid, "success", "Item deleted.", {"path": source})
            return

        if job_type == "rename":
            ensure_safe_path(source, config, "Rename source")
            ensure_safe_path(destination, config, "Rename destination")
            shutil.move(source, destination)
            send_result(config, job_uuid, "success", "Item renamed.", {"path": destination})
            return

        if job_type not in {"copy", "move", "sync"}:
            send_result(config, job_uuid, "failed", f"Unsupported job type: {job_type}")
            return

        ensure_safe_path(source, config, "Source")
        if destination:
            ensure_safe_path(destination, config, "Destination")
        if not os.path.exists(source):
            send_result(config, job_uuid, "failed", f"Source not found: {source}")
            return

        src_is_dir = os.path.isdir(source)
        total = max(file_size(source), 1)
        if destination_server_id and destination_server_id != source_server_id:
            tmp_zip = None
            upload_target = source
            upload_name = os.path.basename(source.rstrip("\\/"))
            if src_is_dir:
                tmp_zip = make_zip(source, job_uuid, config)
                upload_target = tmp_zip
                upload_name = upload_name + ".zip"
            checksum = calculate_sha256(upload_target)
            upload_size = os.path.getsize(upload_target)
            post_progress(config, job_uuid, 0, upload_size, "Uploading relay file")
            upload_with_retries(config, job_uuid, upload_target, upload_name, checksum, src_is_dir)
            if tmp_zip and os.path.exists(tmp_zip):
                os.remove(tmp_zip)
            if job_type == "move":
                shutil.rmtree(source) if src_is_dir else os.remove(source)
            send_result(config, job_uuid, "success", "Upload complete.", {"checksum": checksum}, upload_size, checksum)
            return

        if job_type == "sync":
            result, copied, checksum = sync_paths(source, destination, config, job_uuid, overwrite)
            send_result(config, job_uuid, "success", "Local sync completed.", result, copied, checksum)
            return

        if src_is_dir:
            dest_path = resolve_destination(destination, os.path.basename(source.rstrip("\\/")), destination_is_dir, True)
            if job_type == "copy":
                shutil.copytree(source, dest_path, dirs_exist_ok=overwrite)
            else:
                shutil.move(source, dest_path)
        else:
            dest_path = resolve_destination(destination, os.path.basename(source), destination_is_dir, False)
            if job_type == "copy":
                copy_file_chunked(source, dest_path, config, job_uuid, total)
            else:
                shutil.move(source, dest_path)
        checksum = calculate_sha256(dest_path) if os.path.isfile(dest_path) else None
        send_result(config, job_uuid, "success", f"Local {job_type} completed.", {"source_path": source, "destination_path": dest_path}, total, checksum)

    except Exception as exc:
        logging.error("transfer_failure job=%s error=%s", job_uuid, exc, exc_info=True)
        send_result(config, job_uuid, "failed", str(exc))


def poll_jobs(config):
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    try:
        response = requests.post(f"{config['backend_url'].rstrip('/')}/api/agents/jobs/poll", json={}, headers=headers, verify=False, timeout=10)
        if response.status_code == 401:
            logging.error("Authentication failed (401) during poll. Attempting re-registration...")
            register_agent(force=True)
            return
        response.raise_for_status()
        job = response.json().get("job")
        if job:
            execute_job(config, job)
    except Exception as exc:
        logging.error("Poll failed: %s", exc)


def main():
    logging.info("Starting FileBridge Python Agent...")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    operation_queue = PersistentOperationQueue(QUEUE_FILE)
    config = None
    while not config or not config.get("agent_token"):
        config = register_agent()
        if not config or not config.get("agent_token"):
            logging.info("Retrying registration in 5 seconds...")
            time.sleep(5)

    logging.info("Agent Active: %s", config["agent_uuid"])
    config = refresh_runtime_config(config)
    observer = start_watchers(config, operation_queue)
    last_heartbeat = 0
    last_config_refresh = 0
    last_update_check = 0
    # Track jobs running in background threads so we don't double-execute
    _active_job_threads = {}

    try:
        while True:
            try:
                config = load_config()
                if not config.get("agent_token"):
                    config = register_agent() or config
                now = time.monotonic()
                if now - last_config_refresh >= 120:
                    config = refresh_runtime_config(config)
                    last_config_refresh = now
                if now - last_update_check >= 3600:
                    check_for_updates(config)
                    last_update_check = now

                # Count active (non-finished) job threads for heartbeat
                active_count = sum(1 for t in _active_job_threads.values() if t.is_alive())

                if now - last_heartbeat >= config.get("heartbeat_interval", 10):
                    send_heartbeat(config, operation_queue=operation_queue, current_transfers=active_count)
                    last_heartbeat = now
                flush_operation_queue(config, operation_queue)

                # Only poll for a new job if under the max concurrent jobs limit (10)
                if active_count < 10:
                    headers = {"Authorization": f"Bearer {config['agent_token']}"}
                    try:
                        response = requests.post(
                            f"{config['backend_url'].rstrip('/')}/api/agents/jobs/poll",
                            json={}, headers=headers, verify=False, timeout=10
                        )
                        if response.status_code == 401:
                            logging.error("Authentication failed (401) during poll. Attempting re-registration...")
                            register_agent(force=True)
                        else:
                            response.raise_for_status()
                            job = response.json().get("job")
                            if job:
                                job_uuid = job.get("job_uuid", "")
                                # Run the job in a daemon thread so heartbeats keep firing
                                t = threading.Thread(
                                    target=execute_job,
                                    args=(config, job),
                                    name=f"job-{job_uuid}",
                                    daemon=True,
                                )
                                t.start()
                                _active_job_threads[job_uuid] = t
                                logging.info("Job %s started in background thread", job_uuid)
                    except Exception as exc:
                        logging.error("Poll failed: %s", exc)

                # Purge finished threads from tracking dict
                for jid in list(_active_job_threads):
                    if not _active_job_threads[jid].is_alive():
                        del _active_job_threads[jid]

            except Exception as exc:
                logging.error("Unexpected error: %s", exc)
            time.sleep(2)
    finally:
        if observer:
            logging.info("Stopping folder watchers...")
            observer.stop()
            observer.join()


class FileBridgeWindowsService(win32serviceutil.ServiceFramework if win32serviceutil else object):
    _svc_name_ = "FileBridgeAgent"
    _svc_display_name_ = "FileBridge Agent"
    _svc_description_ = "FileBridge distributed file synchronization and monitoring agent."

    def __init__(self, args):
        if win32serviceutil:
            win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None) if win32event else None

    def SvcStop(self):
        if win32service:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.stop_event:
            win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        os.environ["FILEBRIDGE_SERVICE"] = "1"
        if servicemanager:
            servicemanager.LogInfoMsg("FileBridge Agent service starting")
        main()


def service_command(argv):
    SERVICE_COMMANDS = {"install-service", "install", "uninstall-service", "remove",
                        "restart-service", "restart", "start-service", "stop-service"}
    command = argv[1].lower() if len(argv) > 1 else ""
    # Not a service command — let main() run normally on any platform
    if command not in SERVICE_COMMANDS:
        return None
    if platform.system() != "Windows" or not win32serviceutil:
        print("Windows service commands require Windows with pywin32 installed.")
        return 1
    if command in {"install-service", "install"}:
        win32serviceutil.InstallService(
            FileBridgeWindowsService,
            FileBridgeWindowsService._svc_name_,
            FileBridgeWindowsService._svc_display_name_,
            description=FileBridgeWindowsService._svc_description_,
            startType=win32service.SERVICE_AUTO_START,
        )
        print("FileBridgeAgent service installed.")
        return 0
    if command in {"uninstall-service", "remove"}:
        win32serviceutil.RemoveService(FileBridgeWindowsService._svc_name_)
        print("FileBridgeAgent service removed.")
        return 0
    if command in {"restart-service", "restart"}:
        try:
            win32serviceutil.RestartService(FileBridgeWindowsService._svc_name_)
        except Exception:
            win32serviceutil.StartService(FileBridgeWindowsService._svc_name_)
        print("FileBridgeAgent service restarted.")
        return 0
    if command == "start-service":
        win32serviceutil.StartService(FileBridgeWindowsService._svc_name_)
        return 0
    if command == "stop-service":
        win32serviceutil.StopService(FileBridgeWindowsService._svc_name_)
        return 0
    return None


if __name__ == "__main__":
    service_result = service_command(sys.argv)
    if service_result is not None:
        sys.exit(service_result)
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Agent stopped by user.")
        sys.exit(0)
