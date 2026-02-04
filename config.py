"""
Configuration file for ELFT Invoice Platform
Loads settings from environment variables for security
"""
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables from .env file
load_dotenv()

# Database Configuration
# Support both Railway's DATABASE_URL and individual variables
database_url = os.getenv('DATABASE_URL')

if database_url:
    # Parse Railway's DATABASE_URL format
    # postgresql://user:password@host:port/dbname
    parsed = urlparse(database_url)
    DB_CONFIG = {
        'host': parsed.hostname,
        'port': parsed.port or 5432,
        'database': parsed.path[1:],  # Remove leading slash
        'user': parsed.username,
        'password': parsed.password
    }
else:
    # Use individual environment variables (for local development)
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'contract_management'),
        'user': os.getenv('DB_USER', 'contract_admin'),
        'password': os.getenv('DB_PASSWORD', 'SecurePass2026!')
    }

# API Keys
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Flask Configuration
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))

# Excluded months for analysis (comma-separated)
EXCLUDED_MONTHS = os.getenv('EXCLUDED_MONTHS', '2024-08,2024-11,Aug-24,Nov-24,August 2024,November 2024').split(',')
