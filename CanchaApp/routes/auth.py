"""Blueprint de autenticación: registro (con celular), login, recuperación y cierre de sesión."""

from datetime import timedelta
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from config import ahora_colombia, normalizar_celular_colombiano, obtener_codigo_admin
from db.agenda import generar_reservas_fijas_pendientes
from db.usuarios import (
    actualizar_contrasena_usuario,
    buscar_usuario_por_correo,
    guardar_codigo_recuperacion,
    registrar_usuario,
)
from mailer import enviar_correo_recuperacion

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        telefono_raw = request.form.get("telefono", "").strip()
        contrasena = request.form.get("contrasena", "")
        tipo_usuario = request.form.get("tipo_usuario", "")
        codigo_admin = request.form.get("codigo_admin", "").strip()

        if not nombre or not correo or not contrasena or not tipo_usuario:
            flash("Completa todos los campos obligatorios.", "error")
            return render_template("registro.html")

        if "@" not in correo or "." not in correo:
            flash("Ingresa un correo electrónico válido.", "error")
            return render_template("registro.html")

        telefono = ""
        if telefono_raw:
            telefono = normalizar_celular_colombiano(telefono_raw)
            if not telefono:
                flash("Ingresa un celular colombiano válido (10 dígitos, empieza por 3).", "error")
                return render_template("registro.html")

        if len(contrasena) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("registro.html")

        if tipo_usuario not in ("jugador", "administrador"):
            flash("Tipo de usuario no válido.", "error")
            return render_template("registro.html")

        if tipo_usuario == "administrador":
            codigo_esperado = obtener_codigo_admin()
            if not codigo_esperado:
                flash("El registro de administradores no está habilitado en el servidor (.env).", "error")
                return render_template("registro.html")
            if not secrets.compare_digest(codigo_admin, codigo_esperado):
                flash("Código de administrador incorrecto.", "error")
                return render_template("registro.html")

        if buscar_usuario_por_correo(correo):
            flash("Ya existe una cuenta registrada con ese correo.", "error")
            return render_template("registro.html")

        registrar_usuario(nombre, correo, generate_password_hash(contrasena), tipo_usuario, telefono)
        flash("Cuenta creada con éxito. Inicia sesión para entrar.", "exito")
        return redirect(url_for("auth.login"))

    return render_template("registro.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        contrasena = request.form.get("contrasena", "")

        if not correo or not contrasena:
            flash("Ingresa tu correo y contraseña.", "error")
            return render_template("login.html")

        usuario = buscar_usuario_por_correo(correo)
        if usuario and check_password_hash(usuario["contrasena"], contrasena):
            csrf_actual = session.get("_csrf_token")
            session.clear()
            if csrf_actual:
                session["_csrf_token"] = csrf_actual

            session["usuario_id"] = usuario["id"]
            session["usuario_nombre"] = usuario["nombre"]
            session["tipo_usuario"] = usuario["tipo_usuario"]
            session["usuario_foto"] = usuario["foto"]

            flash(f"Hola, {usuario['nombre']}.", "exito")
            if usuario["tipo_usuario"] == "administrador":
                # Genera reservas fijas pendientes al iniciar sesión (idempotente)
                generar_reservas_fijas_pendientes(administrador_id=usuario["id"])
                return redirect(url_for("admin.panel_administrador"))
            return redirect(url_for("inicio.inicio"))

        flash("Correo o contraseña incorrectos.", "error")
        return render_template("login.html")

    return render_template("login.html")


@auth_bp.route("/olvide_contrasena", methods=["GET", "POST"])
def olvide_contrasena():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        if not correo or "@" not in correo or "." not in correo:
            flash("Ingresa un correo electrónico válido.", "error")
            return render_template("olvide_contrasena.html")

        usuario = buscar_usuario_por_correo(correo)
        if usuario:
            codigo = str(secrets.randbelow(900000) + 100000)
            fecha_expira = (ahora_colombia() + timedelta(minutes=15)).isoformat()
            guardar_codigo_recuperacion(usuario["id"], codigo, fecha_expira)
            enviar_correo_recuperacion(correo, codigo)

        session["correo_recuperacion"] = correo
        flash("Si el correo está registrado, enviamos un código de 6 dígitos.", "exito")
        return redirect(url_for("auth.restablecer_contrasena"))

    return render_template("olvide_contrasena.html")


@auth_bp.route("/restablecer_contrasena", methods=["GET", "POST"])
def restablecer_contrasena():
    correo_sugerido = session.get("correo_recuperacion", "")

    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        codigo = request.form.get("codigo", "").strip()
        nueva = request.form.get("nueva_contrasena", "")
        confirmar = request.form.get("confirmar_contrasena", "")

        if not correo or not codigo or not nueva or not confirmar:
            flash("Completa todos los campos.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        if len(nueva) < 6:
            flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        if nueva != confirmar:
            flash("Las contraseñas no coinciden.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        usuario = buscar_usuario_por_correo(correo)
        if not usuario or not usuario["codigo_recuperacion"] or usuario["codigo_recuperacion"] != codigo:
            flash("Correo o código incorrecto.", "error")
            return render_template("restablecer_contrasena.html", correo=correo)

        try:
            from datetime import datetime
            expira_dt = datetime.fromisoformat(usuario["codigo_expira"])
            ahora_dt = ahora_colombia() if expira_dt.tzinfo else ahora_colombia().replace(tzinfo=None)
            vencido = ahora_dt > expira_dt
        except ValueError:
            vencido = True

        if not usuario["codigo_expira"] or vencido:
            flash("El código ha vencido. Solicita uno nuevo.", "error")
            return redirect(url_for("auth.olvide_contrasena"))

        actualizar_contrasena_usuario(usuario["id"], generate_password_hash(nueva))
        session.pop("correo_recuperacion", None)
        flash("Contraseña actualizada. Ya puedes iniciar sesión.", "exito")
        return redirect(url_for("auth.login"))

    return render_template("restablecer_contrasena.html", correo=correo_sugerido)


@auth_bp.route("/cerrar_sesion")
def cerrar_sesion():
    session.clear()
    flash("Sesión cerrada.", "exito")
    return redirect(url_for("inicio.inicio"))
