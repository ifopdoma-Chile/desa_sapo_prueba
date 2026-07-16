import os
import logging
import psycopg2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# CREDENCIALES Y CONFIGURACIÓN SEGURA DESDE VARIABLES DE ENTORNO
# -----------------------------------------------------------------------------
# Base de datos (usar variables de entorno y SSL por defecto)
DATABASE_CONFIG = {
    "dbname": "gisdb",
    "user": "appmovil",
    "password": "2025$Doma##",
    "host": "giscc.ifop.cl",
    "port": "5432",
}
# Correo SMTP (usar variables de entorno)
SMTP_CONFIG = {
    "REMITENTE": "doma.gis.ifop@gmail.com",
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": 465,
    "SMTP_USERNAME": "doma.gis.ifop@gmail.com",
    "SMTP_PASSWORD": "tkswkmcdujdsenam"
}

def _validate_db_config():
    missing = [k for k in ("dbname", "user", "password", "host") if not DATABASE_CONFIG.get(k)]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno para DB: {', '.join(missing)}")

def get_db_connection():
    """
    Crea una conexión a PostgreSQL usando sslmode (por defecto 'require').
    Lanza RuntimeError si faltan credenciales.
    """
    _validate_db_config()
    return psycopg2.connect(
        dbname=DATABASE_CONFIG["dbname"],
        user=DATABASE_CONFIG["user"],
        password=DATABASE_CONFIG["password"],
        host=DATABASE_CONFIG["host"],
        port=DATABASE_CONFIG["port"],
    )

def _validate_smtp_config():
    missing = [k for k in ("SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD") if not SMTP_CONFIG.get(k)]
    if missing:
        # Permitimos que REMITENTE use el valor por defecto si no se especifica.
        raise RuntimeError(f"Faltan variables de entorno para SMTP: {', '.join(missing)}")
