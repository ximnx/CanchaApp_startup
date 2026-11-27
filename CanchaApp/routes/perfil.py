"""Blueprint de Perfil: datos personales, teléfono, foto, Mis equipos, suscripción Beta y ajustes."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    CATEGORIAS_EQUIPO,
    DEPORTES_CATALOGO,
    DEPORTES_NOMBRES,
    MODALIDADES_POR_DEPORTE,
    modalidad_valida,
    normalizar_celular_colombiano,
)
from db.partidos import (
    actualizar_equipo,
    agregar_integrante_equipo,
    crear_equipo,
    eliminar_integrante_equipo,
    existe_equipo_por_nombre,
    obtener_equipo_por_id,
    obtener_equipos_por_capitan,
    obtener_integrantes_equipo,
)
from db.usuarios import (
    actualizar_contrasena_usuario,
    actualizar_perfil_usuario,
    buscar_usuario_por_id,
    obtener_suscripcion_admin,
)
from media import guardar_imagen_subida
from security import requiere_login, requiere_rol

perfil_bp = Blueprint("perfil", __name__)


@perfil_bp.route("/perfil", methods=["GET", "POST"])
@requiere_login("Inicia sesión para ver tu perfil.")
def mi_perfil():
    usuario = buscar_usuario_por_id(session["usuario_id"])
    if not usuario:
        session.clear()
        return redirect(url_for("auth.login"))

    deportes_favoritos = [
        d.strip() for d in (usuario["deportes_favoritos"] or "").split(",") if d.strip() in DEPORTES_NOMBRES
    ]

    if request.method == "POST":
        seccion = request.form.get("seccion", "datos").strip()

        if seccion == "deportes":
            deportes_sel = [d for d in request.form.getlist("deportes_favoritos") if d in DEPORTES_NOMBRES]
            actualizar_perfil_usuario(usuario["id"], usuario["nombre"], usuario["foto"], deportes_favoritos=deportes_sel)
            flash("Deportes favoritos actualizados.", "exito")
            return redirect(url_for("perfil.mi_perfil"))

        nuevo_nombre = request.form.get("nombre", "").strip()
        telefono_raw = request.form.get("telefono", "").strip()
        if len(nuevo_nombre) < 2:
            flash("Escribe un nombre válido (mínimo 2 caracteres).", "error")
            return redirect(url_for("perfil.mi_perfil"))

        telefono_norm = ""
        if telefono_raw:
            telefono_norm = normalizar_celular_colombiano(telefono_raw)
            if not telefono_norm:
                flash("Ingresa un celular colombiano válido (10 dígitos, empieza por 3).", "error")
                return redirect(url_for("perfil.mi_perfil"))

        ruta_foto = usuario["foto"]
        nueva_foto, error_foto = guardar_imagen_subida(request.files.get("foto"), "perfil", usuario["id"])
        if error_foto:
            flash(error_foto, "error")
            return redirect(url_for("perfil.mi_perfil"))
        if nueva_foto:
            ruta_foto = nueva_foto

        actualizar_perfil_usuario(usuario["id"], nuevo_nombre, ruta_foto, telefono=telefono_norm)
        session["usuario_nombre"] = nuevo_nombre
        session["usuario_foto"] = ruta_foto
        flash("Datos personales actualizados.", "exito")
        return redirect(url_for("perfil.mi_perfil"))

    total_equipos = (
        len(obtener_equipos_por_capitan(usuario["id"]))
        if usuario["tipo_usuario"] == "jugador"
        else 0
    )
    suscripcion = (
        obtener_suscripcion_admin(usuario["id"])
        if usuario["tipo_usuario"] == "administrador"
        else None
    )

    return render_template(
        "perfil.html",
        usuario=usuario,
        deportes_catalogo=DEPORTES_CATALOGO,
        deportes_favoritos=deportes_favoritos,
        total_equipos=total_equipos,
        suscripcion=suscripcion,
    )


@perfil_bp.route("/perfil/quitar_foto", methods=["POST"])
@requiere_login("Inicia sesión para modificar tu perfil.")
def quitar_foto_perfil():
    usuario = buscar_usuario_por_id(session["usuario_id"])
    if usuario:
        actualizar_perfil_usuario(usuario["id"], usuario["nombre"], "")
        session["usuario_foto"] = ""
        flash("Foto de perfil eliminada.", "exito")
    return redirect(url_for("perfil.mi_perfil"))


@perfil_bp.route("/perfil/contrasena", methods=["POST"])
@requiere_login("Inicia sesión para cambiar tu contraseña.")
def cambiar_contrasena_perfil():
    usuario = buscar_usuario_por_id(session["usuario_id"])
    if not usuario:
        session.clear()
        return redirect(url_for("auth.login"))

    actual = request.form.get("contrasena_actual", "")
    nueva = request.form.get("nueva_contrasena", "")
    confirmar = request.form.get("confirmar_contrasena", "")

    if not check_password_hash(usuario["contrasena"], actual):
        flash("La contraseña actual no es correcta.", "error")
        return redirect(url_for("perfil.mi_perfil"))

    if len(nueva) < 6:
        flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
        return redirect(url_for("perfil.mi_perfil"))

    if nueva != confirmar:
        flash("Las contraseñas nuevas no coinciden.", "error")
        return redirect(url_for("perfil.mi_perfil"))

    actualizar_contrasena_usuario(usuario["id"], generate_password_hash(nueva))
    flash("Contraseña actualizada correctamente.", "exito")
    return redirect(url_for("perfil.mi_perfil"))


# ---------------- MIS EQUIPOS (DENTRO DE PERFIL) ----------------

@perfil_bp.route("/equipos")
@requiere_rol("jugador", destino_error="perfil.mi_perfil", mensaje="La gestión de equipos es para jugadores.")
def ver_equipos():
    mis_equipos_bd = obtener_equipos_por_capitan(session["usuario_id"])
    equipos_vista = [
        {"equipo": eq, "integrantes": obtener_integrantes_equipo(eq["id"])}
        for eq in mis_equipos_bd
    ]
    return render_template(
        "equipos.html",
        equipos_vista=equipos_vista,
        deportes=DEPORTES_CATALOGO,
        modalidades_por_deporte=MODALIDADES_POR_DEPORTE,
        categorias=CATEGORIAS_EQUIPO,
    )


@perfil_bp.route("/equipos/crear", methods=["POST"])
@requiere_rol("jugador", destino_error="perfil.mi_perfil")
def registrar_equipo():
    nombre = request.form.get("nombre", "").strip()
    deporte = request.form.get("deporte", "Fútbol").strip()
    categoria = request.form.get("categoria", "").strip()
    tipo_futbol = request.form.get("tipo_futbol", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    integrantes_texto = request.form.get("integrantes_iniciales", "").strip()

    if not nombre or not descripcion:
        flash("Escribe el nombre y una descripción para tu equipo.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    if deporte not in DEPORTES_NOMBRES or categoria not in CATEGORIAS_EQUIPO:
        flash("Deporte o categoría no válidos.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    if not modalidad_valida(deporte, tipo_futbol):
        flash(f"La modalidad no corresponde a {deporte}.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    if existe_equipo_por_nombre(nombre):
        flash("Ya existe un equipo con ese nombre.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    equipo_id = crear_equipo(nombre, categoria, tipo_futbol, session["usuario_id"], descripcion, deporte)
    if integrantes_texto:
        for nombre_int in [x.strip() for x in integrantes_texto.split(",") if x.strip()][:20]:
            agregar_integrante_equipo(equipo_id, nombre_int)

    flash(f"Equipo '{nombre}' creado.", "exito")
    return redirect(url_for("perfil.ver_equipos"))


@perfil_bp.route("/equipos/<int:equipo_id>/editar", methods=["POST"])
@requiere_rol("jugador", destino_error="perfil.mi_perfil")
def editar_equipo(equipo_id):
    equipo = obtener_equipo_por_id(equipo_id)
    if not equipo or equipo["capitan_id"] != session["usuario_id"]:
        flash("No puedes editar este equipo.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    nombre = request.form.get("nombre", "").strip()
    deporte = request.form.get("deporte", equipo["deporte"] or "Fútbol").strip()
    categoria = request.form.get("categoria", "").strip()
    tipo_futbol = request.form.get("tipo_futbol", "").strip()
    descripcion = request.form.get("descripcion", "").strip()

    if not nombre or not descripcion:
        flash("Completa nombre y descripción del equipo.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    if deporte not in DEPORTES_NOMBRES or categoria not in CATEGORIAS_EQUIPO or not modalidad_valida(deporte, tipo_futbol):
        flash("Deporte, modalidad o categoría no válidos.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    if existe_equipo_por_nombre(nombre, excluir_id=equipo_id):
        flash("Ya existe otro equipo con ese nombre.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    actualizar_equipo(equipo_id, session["usuario_id"], nombre, categoria, tipo_futbol, descripcion, deporte)
    flash(f"Equipo '{nombre}' actualizado.", "exito")
    return redirect(url_for("perfil.ver_equipos"))


@perfil_bp.route("/equipos/<int:equipo_id>/integrantes/agregar", methods=["POST"])
@requiere_rol("jugador", destino_error="perfil.ver_equipos")
def agregar_integrante(equipo_id):
    equipo = obtener_equipo_por_id(equipo_id)
    if not equipo or equipo["capitan_id"] != session["usuario_id"]:
        flash("Solo el capitán puede agregar integrantes.", "error")
        return redirect(url_for("perfil.ver_equipos"))

    nombre_int = request.form.get("nombre_integrante", "").strip()[:60]
    posicion = request.form.get("posicion", "").strip()[:40]
    if len(nombre_int) < 2:
        flash("Escribe el nombre del integrante (mínimo 2 caracteres).", "error")
        return redirect(url_for("perfil.ver_equipos"))

    agregar_integrante_equipo(equipo_id, nombre_int, posicion)
    flash(f"{nombre_int} agregado a {equipo['nombre']}.", "exito")
    return redirect(url_for("perfil.ver_equipos"))


@perfil_bp.route("/equipos/integrantes/eliminar/<int:integrante_id>", methods=["POST"])
@requiere_rol("jugador", destino_error="perfil.ver_equipos")
def eliminar_integrante(integrante_id):
    if eliminar_integrante_equipo(integrante_id, session["usuario_id"]):
        flash("Integrante retirado.", "exito")
    else:
        flash("No se pudo retirar el integrante.", "error")
    return redirect(url_for("perfil.ver_equipos"))
