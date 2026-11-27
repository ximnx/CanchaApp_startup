"""Blueprint de Mis reservas: reserva confirmada inmediata, Próximas/Historial y regla 3h."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from config import (
    HORAS_MIN_CANCELACION,
    MODALIDADES_POR_DEPORTE,
    ahora_colombia,
    fecha_hora_colombia,
    modalidad_valida,
    normalizar_celular_colombiano,
)
from db.canchas import (
    cancelar_reserva,
    crear_reserva_atomica,
    obtener_cancha_por_id,
    obtener_deportes_de_cancha,
    obtener_reservas_por_usuario,
    puede_cancelar_jugador,
)
from db.partidos import crear_notificacion
from db.usuarios import actualizar_telefono_usuario, buscar_usuario_por_id
from security import requiere_rol

reservas_bp = Blueprint("reservas", __name__)


@reservas_bp.route("/reservar", methods=["POST"])
@requiere_rol("jugador", destino_error="canchas.ver_canchas", mensaje="Solo los jugadores pueden reservar.")
def solicitar_reserva():
    cancha_id = request.form.get("cancha_id", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    nombre_reserva = request.form.get("nombre_reserva", "").strip()
    identificacion = request.form.get("identificacion", "").strip()
    telefono_raw = request.form.get("telefono_reserva", "").strip()
    deporte_reserva = request.form.get("deporte_reserva", "").strip()
    modalidad_reserva = request.form.get("modalidad_reserva", "").strip()

    if not cancha_id.isdigit() or not fecha or not hora:
        flash("Selecciona una fecha y hora válidas.", "error")
        return redirect(url_for("canchas.ver_canchas"))

    cancha_id_num = int(cancha_id)
    cancha = obtener_cancha_por_id(cancha_id_num)
    if not cancha:
        flash("La cancha seleccionada no existe.", "error")
        return redirect(url_for("canchas.ver_canchas"))

    if len(nombre_reserva) < 3:
        flash("Ingresa tu nombre completo para la reserva.", "error")
        return redirect(url_for("canchas.detalle_cancha", cancha_id=cancha_id_num, fecha=fecha))

    if len(identificacion) < 5 or len(identificacion) > 20:
        flash("Ingresa un número de identificación válido (5 a 20 caracteres).", "error")
        return redirect(url_for("canchas.detalle_cancha", cancha_id=cancha_id_num, fecha=fecha))

    # Validamos celular colombiano (lo pedimos si el usuario aún no lo tiene en su perfil)
    usuario = buscar_usuario_por_id(session["usuario_id"])
    tel_cuenta = (usuario["telefono"] or "") if usuario else ""
    telefono_final = normalizar_celular_colombiano(telefono_raw or tel_cuenta)
    if not telefono_final:
        flash("Ingresa un celular colombiano válido (10 dígitos, empieza por 3) para recordatorios.", "error")
        return redirect(url_for("canchas.detalle_cancha", cancha_id=cancha_id_num, fecha=fecha))

    if telefono_final != tel_cuenta:
        actualizar_telefono_usuario(session["usuario_id"], telefono_final)

    # Verificar en hora de Colombia que el turno sea futuro
    try:
        if fecha_hora_colombia(fecha, hora) <= ahora_colombia():
            flash("No puedes reservar un turno que ya pasó.", "error")
            return redirect(url_for("canchas.detalle_cancha", cancha_id=cancha_id_num))
    except ValueError:
        flash("Fecha u hora con formato inválido.", "error")
        return redirect(url_for("canchas.detalle_cancha", cancha_id=cancha_id_num))

    deporte_principal = cancha["deporte"] if cancha["deporte"] else "Fútbol"
    deportes_ofrecidos = obtener_deportes_de_cancha(cancha_id_num, deporte_principal)
    if deporte_reserva not in deportes_ofrecidos:
        deporte_reserva = deporte_principal

    if not modalidad_valida(deporte_reserva, modalidad_reserva):
        if deporte_reserva == deporte_principal and modalidad_valida(deporte_principal, cancha["tipo_futbol"]):
            modalidad_reserva = cancha["tipo_futbol"]
        else:
            modalidad_reserva = MODALIDADES_POR_DEPORTE[deporte_reserva][0]

    ok, msg, _reserva_id, _precio = crear_reserva_atomica(
        usuario_id=session["usuario_id"],
        cancha_id=cancha_id_num,
        fecha_iso=fecha,
        hora_hm=hora,
        nombre_reserva=nombre_reserva,
        identificacion=identificacion,
        deporte_reserva=deporte_reserva,
        modalidad_reserva=modalidad_reserva,
        origen="web",
        telefono_reserva=telefono_final,
    )
    if not ok:
        flash(msg, "error")
        return redirect(url_for("canchas.detalle_cancha", cancha_id=cancha_id_num, fecha=fecha))

    # Notificación inmediata al administrador: la reserva nació confirmada
    crear_notificacion(
        cancha["administrador_id"],
        "Nueva reserva confirmada",
        f"{nombre_reserva} reservó {cancha['nombre']} el {fecha} a las {hora}.",
        f"/administrador?cancha_id={cancha_id_num}&fecha={fecha}",
        "reserva",
        ahora_colombia().isoformat(),
    )

    flash(f"Reserva confirmada en {cancha['nombre']} ({fecha} · {hora}).", "exito")
    return redirect(url_for("reservas.mis_reservas", tab="proximas", nueva="1"))


@reservas_bp.route("/mis_reservas")
@requiere_rol(
    "jugador",
    destino_error="admin.panel_administrador",
    mensaje="Esta sección es para jugadores.",
)
def mis_reservas():
    tab_activo = request.args.get("tab", "proximas").strip()
    if tab_activo not in ("proximas", "historial"):
        tab_activo = "proximas"

    reserva_nueva = request.args.get("nueva") == "1"
    ahora = ahora_colombia()
    todas = obtener_reservas_por_usuario(session["usuario_id"])

    proximas = []
    historial = []
    for r in todas:
        estado_efectivo = "confirmada" if r["estado"] == "pendiente" else r["estado"]
        dt_turno = fecha_hora_colombia(r["fecha"], r["hora"])
        es_futura_activa = estado_efectivo == "confirmada" and dt_turno > ahora

        puede_canc, motivo_no_canc = puede_cancelar_jugador(r["fecha"], r["hora"]) if es_futura_activa else (False, "")
        item = {
            "id": r["id"],
            "cancha_id": r["cancha_id"],
            "nombre_cancha": r["nombre_cancha"],
            "direccion_cancha": r["direccion_cancha"],
            "telefono_cancha": r["telefono_cancha"] or "",
            "fecha": r["fecha"],
            "hora": r["hora"],
            "estado": estado_efectivo,
            "estado_pago": r["estado_pago"] or "pendiente",
            "precio_cancha": r["precio_aplicado"] or r["precio_cancha"],
            "deporte_reserva": r["deporte_reserva"] or r["deporte_cancha"] or "Fútbol",
            "modalidad_reserva": r["modalidad_reserva"] or r["tipo_futbol"],
            "es_fija": bool(r["reserva_fija_id"]),
            "puede_cancelar": puede_canc,
            "motivo_no_cancelar": motivo_no_canc,
            "cancelada_por_rol": r["cancelada_por_rol"] or "",
            "motivo_cancelacion": r["motivo_cancelacion"] or "",
        }
        if es_futura_activa:
            proximas.append(item)
        else:
            historial.append(item)

    return render_template(
        "mis_reservas.html",
        tab_activo=tab_activo,
        reserva_nueva=reserva_nueva,
        proximas=proximas,
        historial=historial,
        horas_min_cancelacion=HORAS_MIN_CANCELACION,
    )


@reservas_bp.route("/mis_reservas/cancelar/<int:reserva_id>", methods=["POST"])
@requiere_rol("jugador", destino_error="inicio.inicio")
def cancelar_mi_reserva(reserva_id):
    motivo = request.form.get("motivo", "").strip()
    ok, msg, reserva = cancelar_reserva(reserva_id, "jugador", session["usuario_id"], motivo)
    if not ok:
        flash(msg, "error")
        return redirect(url_for("reservas.mis_reservas", tab="proximas"))

    # Notificamos al administrador que el jugador canceló su reserva
    if reserva:
        crear_notificacion(
            reserva["administrador_id"],
            "Reserva cancelada por jugador",
            f"{reserva['nombre_reserva'] or session.get('usuario_nombre')} canceló {reserva['nombre_cancha']} ({reserva['fecha']} · {reserva['hora']}).",
            f"/administrador?cancha_id={reserva['cancha_id']}&fecha={reserva['fecha']}",
            "reserva",
            ahora_colombia().isoformat(),
        )
    flash("Reserva cancelada. El horario quedó libre.", "exito")
    return redirect(url_for("reservas.mis_reservas", tab="historial"))
