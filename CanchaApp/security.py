"""Seguridad y control de acceso: CSRF, decoradores de sesión/rol y redirecciones seguras."""

from functools import wraps
import secrets
from urllib.parse import urlparse

from flask import flash, redirect, request, session, url_for
from markupsafe import Markup


def obtener_token_csrf():
    """Genera o recupera el token CSRF vinculado a la sesión actual."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def campo_csrf_html():
    """Devuelve el campo oculto con el token CSRF para formularios POST."""
    token = obtener_token_csrf()
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')


def validar_csrf_peticion():
    """Valida el token CSRF en peticiones POST (formulario o cabecera X-CSRF-Token)."""
    if request.method != "POST":
        return True
    token_sesion = session.get("_csrf_token", "")
    token_enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    if not token_sesion or not token_enviado:
        return False
    return secrets.compare_digest(token_sesion, token_enviado)


def url_retorno_segura(fallback):
    """Permite redirigir a la ruta previa solo si pertenece al mismo host."""
    destino = request.form.get("next") or request.referrer or ""
    if destino:
        parseada = urlparse(destino)
        if not parseada.netloc and parseada.path.startswith("/") and not parseada.path.startswith("//"):
            return parseada.path + (f"?{parseada.query}" if parseada.query else "")
        if parseada.netloc == request.host and parseada.path.startswith("/"):
            return parseada.path + (f"?{parseada.query}" if parseada.query else "")
    return fallback


def requiere_login(mensaje="Debes iniciar sesión para continuar."):
    """Protege rutas privadas que requieren un usuario autenticado."""
    def decorador(vista):
        @wraps(vista)
        def envuelta(*args, **kwargs):
            if "usuario_id" not in session:
                flash(mensaje, "error")
                return redirect(url_for("auth.login"))
            return vista(*args, **kwargs)
        return envuelta
    return decorador


def requiere_rol(rol_esperado, destino_error="inicio.inicio", mensaje=None):
    """Protege rutas restringidas a jugadores o administradores."""
    texto_error = mensaje or f"Esta sección es solo para perfil de {rol_esperado}."

    def decorador(vista):
        @wraps(vista)
        def envuelta(*args, **kwargs):
            if "usuario_id" not in session:
                flash("Debes iniciar sesión para continuar.", "error")
                return redirect(url_for("auth.login"))
            if session.get("tipo_usuario") != rol_esperado:
                flash(texto_error, "error")
                return redirect(url_for(destino_error))
            return vista(*args, **kwargs)
        return envuelta
    return decorador
