# app/__init__.py
from flask import Flask


def create_app():
    app = Flask(__name__)

    # Configuraciones de la aplicación
    app.config['SECRET_KEY'] = '1sdsdsdwe3434erfdfx2345'

    app.config["SHORTENER_API_KEY"] = "acortador_ifop_2026"
    app.config["SHORTENER_DB_DSN"] = "postgresql://usuario:password@host:5432/bd"

    # Importar y registrar blueprints
    from app.routes import main
    app.register_blueprint(main)

    from app.shortener import bp as shortener_bp
    app.register_blueprint(shortener_bp)

    return app
