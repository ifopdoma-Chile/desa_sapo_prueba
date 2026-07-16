from app import create_app
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response

# Crear la instancia de la aplicación Flask
app = create_app()

# Configurar el prefijo de rutas para Nginx (por ejemplo, /app)
app.config['APPLICATION_ROOT'] = '/app'

# Ajuste del prefijo para las rutas
app.wsgi_app = DispatcherMiddleware(
    Response('Not Found', status=404),  # Para rutas no manejadas directamente por Flask
    {
        '/app': app.wsgi_app  # Aplica el prefijo "/app" a todas las rutas
    }
)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, debug=True)
    # Ruta del certificado y la clave privada
    #ssl_context = ('/Data/sapo_prueba/certificado/certificate.pem', 'path/to/private-key.pem')

    # Servir la aplicación con HTTPS
    #app.run(host='0.0.0.0', port=443, debug=False, ssl_context=ssl_context)
