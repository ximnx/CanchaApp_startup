"""Registro de blueprints organizados por pantalla de Ready Match."""

from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.canchas import canchas_bp
from routes.inicio import inicio_bp
from routes.partidos import partidos_bp
from routes.perfil import perfil_bp
from routes.pwa import pwa_bp
from routes.reservas import reservas_bp


def registrar_rutas(app):
    """Conecta todos los módulos de rutas a la aplicación Flask."""
    app.register_blueprint(inicio_bp)
    app.register_blueprint(canchas_bp)
    app.register_blueprint(partidos_bp)
    app.register_blueprint(reservas_bp)
    app.register_blueprint(perfil_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(pwa_bp)
