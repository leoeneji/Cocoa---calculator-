import psycopg

from .config import settings


def get_connection():
    return psycopg.connect(settings.database_url)