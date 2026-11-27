"""Blueprint de Partidos: Explorar, Mis partidos, Solicitudes y publicar rival."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from config import (
    CATEGORIAS_EQUIPO,
    DEPORTES_CATALOGO,
    DEPORTES_NOMBRES,
    HORAS_DISPONIBLES,
    MODALIDADES_POR_DEPORTE,
    NIVELES_JUEGO,
    ahora_colombia,
    deporte_de_modalidad,
    hoy_colombia,
)
from db.partidos import (
    actualizar_estado_solicitud,
    crear_notificacion,
    crear_partido,
    crear_solicitud,
    existe_solicitud,
    obtener_equipo_por_id,
    obtener_equipos_por_capitan,
    obtener_partido_por_id,
    obtener_rival_aceptado,
    obtener_solicitud_por_id,
    obtener_solicitudes_enviadas,
    obtener_solicitudes_recibidas,
    obtener_todos_los_partidos,
)
from security import requiere_rol

partidos_bp = Blueprint("partidos", __name__)


@partidos_bp.route("/rivales")
def buscar_rivales():
    tab_activo = request.args.get("tab", "explorar").strip()
    if tab_activo not in ("explorar", "mis_partidos", "solicitudes"):
        tab_activo = "explorar"

    deporte_sel = request.args.get("deporte", "").strip()
    tipo_sel = request.args.get("tipo", "").strip()
    categoria_sel = request.args.get("categoria", "").strip()
    nivel_sel = request.args.get("nivel", "").strip()
    fecha_sel = request.args.get("fecha", "").strip()
    busqueda = request.args.get("q", "").strip()

    if deporte_sel not in DEPORTES_NOMBRES:
        deporte_sel = ""
    if not deporte_sel and tipo_sel:
        inferido = deporte_de_modalidad(tipo_sel)
        if inferido:
            deporte_sel = inferido

    modalidades_disponibles = MODALIDADES_POR_DEPORTE.get(deporte_sel, [])
    if tipo_sel not in modalidades_disponibles:
        tipo_sel = ""
    if categoria_sel not in CATEGORIAS_EQUIPO:
        categoria_sel = ""
    if nivel_sel not in NIVELES_JUEGO:
        nivel_sel = ""

    partidos_bd = obtener_todos_los_partidos(
        tipo_futbol=tipo_sel or None,
        categoria=categoria_sel or None,
        deporte=deporte_sel or None,
        nivel=nivel_sel or None,
        fecha=fecha_sel or None,
        busqueda=busqueda or None,
    )

    fecha_hoy = hoy_colombia().isoformat()
    usuario_id = session.get("usuario_id")

    partidos_explorar = []
    mis_partidos = []
    for p in partidos_bd:
        if p["fecha"] < fecha_hoy:
            continue
        item = {"partido": p, "rival_aceptado": obtener_rival_aceptado(p["id"])}
        if usuario_id and p["capitan_id"] == usuario_id:
            mis_partidos.append(item)
        else:
            partidos_explorar.append(item)

    mis_equipos = []
    solicitudes_recibidas = []
    solicitudes_enviadas = []
    if usuario_id and session.get("tipo_usuario") == "jugador":
        mis_equipos = obtener_equipos_por_capitan(usuario_id)
        solicitudes_recibidas = obtener_solicitudes_recibidas(usuario_id)
        solicitudes_enviadas = obtener_solicitudes_enviadas(usuario_id)

    pendientes_sol = sum(1 for s in solicitudes_recibidas if s["estado"] == "pendiente")
    filtros_activos = sum(1 for v in [deporte_sel, tipo_sel, categoria_sel, nivel_sel, fecha_sel, busqueda] if v)

    return render_template(
        "rivales.html",
        tab_activo=tab_activo,
        partidos_explorar=partidos_explorar,
        mis_partidos=mis_partidos,
        mis_equipos=mis_equipos,
        solicitudes_recibidas=solicitudes_recibidas,
        solicitudes_enviadas=solicitudes_enviadas,
        pendientes_sol=pendientes_sol,
        deportes=DEPORTES_CATALOGO,
        modalidades_por_deporte=MODALIDADES_POR_DEPORTE,
        deporte_seleccionado=deporte_sel,
        modalidades_disponibles=modalidades_disponibles,
        categorias=CATEGORIAS_EQUIPO,
        niveles_juego=NIVELES_JUEGO,
        horas_disponibles=HORAS_DISPONIBLES,
        tipo_seleccionado=tipo_sel,
        categoria_seleccionada=categoria_sel,
        nivel_seleccionado=nivel_sel,
        fecha_seleccionada=fecha_sel,
        busqueda=busqueda,
        filtros_activos=filtros_activos,
        fecha_hoy=fecha_hoy,
    )


@partidos_bp.route("/rivales/publicar", methods=["POST"])
@requiere_rol("jugador", destino_error="partidos.buscar_rivales", mensaje="Solo los jugadores pueden publicar partidos.")
def publicar_partido():
    equipo_id = request.form.get("equipo_id", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    lugar = request.form.get("lugar", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    nivel = request.form.get("nivel", "Intermedio").strip()

    if nivel not in NIVELES_JUEGO:
        nivel = "Intermedio"

    if not equipo_id.isdigit() or not fecha or hora not in HORAS_DISPONIBLES or not lugar or not descripcion:
        flash("Completa todos los campos para publicar el partido.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    if fecha < hoy_colombia().isoformat():
        flash("No puedes publicar un partido en una fecha pasada.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    equipo = obtener_equipo_por_id(int(equipo_id))
    if not equipo or equipo["capitan_id"] != session["usuario_id"]:
        flash("Solo puedes publicar con tus propios equipos.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    deporte_equipo = equipo["deporte"] if equipo["deporte"] else "Fútbol"
    crear_partido(int(equipo_id), fecha, hora, lugar, descripcion, nivel, deporte_equipo)
    flash(f"Partido publicado con {equipo['nombre']}.", "exito")
    return redirect(url_for("partidos.buscar_rivales", tab="mis_partidos"))


@partidos_bp.route("/rivales/solicitar/<int:partido_id>", methods=["POST"])
@requiere_rol("jugador", destino_error="partidos.buscar_rivales", mensaje="Solo los jugadores pueden enviar solicitudes.")
def enviar_solicitud_rival(partido_id):
    equipo_id = request.form.get("equipo_id", "").strip()
    if not equipo_id.isdigit():
        flash("Selecciona uno de tus equipos.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    equipo = obtener_equipo_por_id(int(equipo_id))
    if not equipo or equipo["capitan_id"] != session["usuario_id"]:
        flash("El equipo seleccionado no te pertenece.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    partido = obtener_partido_por_id(partido_id)
    if not partido:
        flash("La publicación ya no existe.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    deporte_partido = partido["deporte"] if partido["deporte"] else "Fútbol"
    deporte_equipo = equipo["deporte"] if equipo["deporte"] else "Fútbol"
    if deporte_equipo != deporte_partido:
        flash(f"Debes usar un equipo de {deporte_partido} para este partido.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    if partido["capitan_id"] == session["usuario_id"]:
        flash("No puedes retar tu propia publicación.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    if obtener_rival_aceptado(partido_id):
        flash("Este partido ya tiene rival confirmado.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    if existe_solicitud(partido_id, int(equipo_id)):
        flash("Ya enviaste una solicitud con ese equipo.", "error")
        return redirect(url_for("partidos.buscar_rivales"))

    crear_solicitud(partido_id, int(equipo_id))
    crear_notificacion(
        partido["capitan_id"],
        f"Nuevo reto de {deporte_partido}",
        f"{equipo['nombre']} quiere jugar contra {partido['nombre_equipo']} el {partido['fecha']} a las {partido['hora']}.",
        "/rivales?tab=solicitudes",
        "partido",
        ahora_colombia().isoformat(),
    )
    flash(f"Solicitud enviada a {partido['nombre_equipo']}.", "exito")
    return redirect(url_for("partidos.buscar_rivales", tab="solicitudes"))


@partidos_bp.route("/rivales/solicitud/<int:solicitud_id>", methods=["POST"])
@requiere_rol("jugador", destino_error="partidos.buscar_rivales", mensaje="Solo los jugadores pueden responder solicitudes.")
def responder_solicitud_rival(solicitud_id):
    accion = request.form.get("accion", "").strip()
    if accion not in ("aceptar", "rechazar"):
        flash("Acción no válida.", "error")
        return redirect(url_for("partidos.buscar_rivales", tab="solicitudes"))

    solicitud = obtener_solicitud_por_id(solicitud_id)
    if not solicitud or solicitud["capitan_publicador_id"] != session["usuario_id"]:
        flash("No puedes responder esta solicitud.", "error")
        return redirect(url_for("partidos.buscar_rivales", tab="solicitudes"))

    if solicitud["estado"] != "pendiente":
        flash("Esta solicitud ya fue respondida.", "error")
        return redirect(url_for("partidos.buscar_rivales", tab="solicitudes"))

    if accion == "aceptar":
        if obtener_rival_aceptado(solicitud["partido_id"]):
            flash("Ya aceptaste otro rival para este partido.", "error")
            return redirect(url_for("partidos.buscar_rivales", tab="solicitudes"))

        actualizar_estado_solicitud(solicitud_id, "aceptada")
        crear_notificacion(
            solicitud["capitan_retador_id"],
            "Partido aceptado en Ready Match",
            f"{solicitud['nombre_publicador']} aceptó jugar contra {solicitud['nombre_retador']} el {solicitud['fecha']} a las {solicitud['hora']}.",
            "/rivales?tab=solicitudes",
            "partido",
            ahora_colombia().isoformat(),
        )
        flash(f"Partido acordado con {solicitud['nombre_retador']}.", "exito")
    else:
        actualizar_estado_solicitud(solicitud_id, "rechazada")
        crear_notificacion(
            solicitud["capitan_retador_id"],
            "Solicitud no aceptada",
            f"{solicitud['nombre_publicador']} no pudo aceptar el partido del {solicitud['fecha']} a las {solicitud['hora']}.",
            "/rivales?tab=solicitudes",
            "partido",
            ahora_colombia().isoformat(),
        )
        flash("Solicitud rechazada.", "exito")

    return redirect(url_for("partidos.buscar_rivales", tab="solicitudes"))
