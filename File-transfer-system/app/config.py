import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-change-me')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql+pymysql://filebridge_user:filebridge_pass@172.100.30.191:3306/filebridge')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_ENV = os.getenv('APP_ENV', 'development')
    BASE_URL = os.getenv('BASE_URL', 'https://172.100.30.191:5001')
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', '')
    AGENT_BOOTSTRAP_TOKEN = os.getenv('AGENT_BOOTSTRAP_TOKEN', 'dev-bootstrap-token')
    JOB_SIGNING_SECRET = os.getenv('JOB_SIGNING_SECRET', 'dev-job-secret')
    SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', '30'))
    SESSION_WARNING_MINUTES = int(os.getenv('SESSION_WARNING_MINUTES', '25'))
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_FROM = os.getenv('SMTP_FROM', '')
    SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 107374182400))
    RELAY_CLEANUP_HOURS = int(os.getenv('RELAY_CLEANUP_HOURS', '24'))
    TRANSFER_CHUNK_SIZE = int(os.getenv('TRANSFER_CHUNK_SIZE', str(1048576)))
    TRANSFER_RETRY_LIMIT = int(os.getenv('TRANSFER_RETRY_LIMIT', '5'))
    AGENT_UPDATE_VERSION = os.getenv('AGENT_UPDATE_VERSION', '1.5.0')
    AGENT_UPDATE_URL = os.getenv('AGENT_UPDATE_URL', '')
