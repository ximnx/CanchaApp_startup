"""Punto de entrada principal de Ready Match (Flask + SQLite + PWA)."""

import os

from flask import Flask, flash, jsonify, redirect, request, url_for

from config import TAMANO_MAX_ARCHIVO, cargar_archivo_env, obtener_codigo_admin, obtener_secret_key
from db.connection import crear_tablas
from media import clase_deporte, formatear_precio, partes_fecha_calendario
from routes import registrar_rutas
from security import campo_csrf_html, obtener_token_csrf, validar_csrf_peticion

cargar_archivo_env()

app = Flask(__name__)

# Seguridad de sesión y carga de archivos (sin secretos fijos en el código)
app.secret_key = obtener_secret_key()
obtener_codigo_admin()  # Advierte al arrancar si falta CODIGO_ADMIN_RM en .env
app.config["MAX_CONTENT_LENGTH"] = TAMANO_MAX_ARCHIVO
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Inicialización no destructiva de tablas SQLite
crear_tablas()

# Filtros y utilidades globales para plantillas
app.jinja_env.filters["precio_cop"] = formatear_precio
app.jinja_env.filters["clase_deporte"] = clase_deporte
app.jinja_env.filters["fecha_cal"] = partes_fecha_calendario
app.jinja_env.globals["csrf_input"] = campo_csrf_html
app.jinja_env.globals["csrf_token"] = obtener_token_csrf


@app.before_request
def proteger_csrf():
    """Valida el token CSRF en toda solicitud POST."""
    if request.method == "POST" and not validar_csrf_peticion():
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Token CSRF inválido"}), 403
        flash("La sesión del formulario expiró. Inténtalo de nuevo.", "error")
        return redirect(request.referrer or url_for("inicio.inicio"))
    return None


@app.after_request
def encabezados_seguridad(respuesta):
    """Agrega cabeceras HTTP de protección básica."""
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    respuesta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return respuesta


@app.errorhandler(404)
def pagina_no_encontrada(_error):
    flash("La pantalla solicitada no existe.", "error")
    return redirect(url_for("inicio.inicio"))


@app.errorhandler(413)
def archivo_demasiado_grande(_error):
    flash("La imagen supera el límite permitido de 5 MB.", "error")
    return redirect(request.referrer or url_for("inicio.inicio"))


registrar_rutas(app)


if __name__ == "__main__":
    # FLASK_DEBUG desactivado por defecto
    modo_debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=modo_debug)
