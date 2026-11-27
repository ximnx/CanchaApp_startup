"""Blueprint de Canchas: búsqueda, filtros en panel inferior, favoritas, mapa y detalle con tarifas."""

from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from config import (
    DEPORTE_POR_SLUG,
    DEPORTES_CATALOGO,
    DEPORTES_NOMBRES,
    DIAS_SEMANA,
    HORAS_DISPONIBLES,
    MODALIDADES_POR_DEPORTE,
    TIPOS_CANCHA,
    deporte_de_modalidad,
    hoy_colombia,
)
from db.agenda import generar_reservas_fijas_pendientes
from db.canchas import (
    enriquecer_cancha,
    obtener_agenda_dia,
    obtener_cancha_por_id,
    obtener_deportes_de_cancha,
    obtener_precio_minimo_cancha,
    obtener_todas_las_canchas,
)
from db.usuarios import alternar_favorito, buscar_usuario_por_id, obtener_ids_favoritos
from security import requiere_login, url_retorno_segura

canchas_bp = Blueprint("canchas", __name__)


@canchas_bp.route("/deporte/<slug>")
def redirigir_deporte(slug):
    """Redirige enlaces de deporte directo a Canchas filtrada."""
    info = DEPORTE_POR_SLUG.get(slug.lower())
    if not info:
        return redirect(url_for("canchas.ver_canchas"))
    return redirect(url_for("canchas.ver_canchas", deporte=info["nombre"]))


@canchas_bp.route("/canchas")
def ver_canchas():
    deporte_sel = request.args.get("deporte", "").strip()
    tipo_sel = request.args.get("tipo", "").strip()
    busqueda = request.args.get("q", "").strip()
    fecha_sel = request.args.get("fecha", "").strip()
    hora_sel = request.args.get("hora", "").strip()
    precio_min_txt = request.args.get("precio_min", "").strip()
    precio_max_txt = request.args.get("precio_max", "").strip()
    tipo_cancha_sel = request.args.get("tipo_cancha", "").strip()
    solo_favoritas = request.args.get("favoritas", "").strip() == "1"
    vista_mapa = request.args.get("vista", "lista").strip() == "mapa"

    if deporte_sel not in DEPORTES_NOMBRES:
        deporte_sel = ""

    if not deporte_sel and tipo_sel:
        inferido = deporte_de_modalidad(tipo_sel)
        if inferido:
            deporte_sel = inferido

    modalidades_disponibles = MODALIDADES_POR_DEPORTE.get(deporte_sel, [])
    if tipo_sel not in modalidades_disponibles:
        tipo_sel = ""

    if hora_sel not in HORAS_DISPONIBLES:
        hora_sel = ""
    if tipo_cancha_sel not in TIPOS_CANCHA:
        tipo_cancha_sel = ""

    precio_min = int(precio_min_txt) if precio_min_txt.isdigit() and int(precio_min_txt) > 0 else None
    precio_max = int(precio_max_txt) if precio_max_txt.isdigit() and int(precio_max_txt) > 0 else None
    if precio_min is None:
        precio_min_txt = ""
    if precio_max is None:
        precio_max_txt = ""

    usuario_id = session.get("usuario_id")
    if solo_favoritas and not usuario_id:
        flash("Inicia sesión para filtrar tus canchas favoritas.", "error")
        return redirect(url_for("auth.login"))

    fecha_hoy = hoy_colombia().isoformat()
    favoritos_ids = obtener_ids_favoritos(usuario_id)
    canchas_bd = obtener_todas_las_canchas(
        tipo_futbol=tipo_sel or None,
        busqueda=busqueda or None,
        deporte=deporte_sel or None,
        fecha=fecha_sel or None,
        hora=hora_sel or None,
        precio_min=precio_min,
        precio_max=precio_max,
        tipo_cancha=tipo_cancha_sel or None,
        solo_favoritas_usuario_id=usuario_id if solo_favoritas else None,
    )

    canchas = [
        enriquecer_cancha(c, fecha_hoy, favoritos_ids, deporte_contexto=deporte_sel or None)
        for c in canchas_bd
    ]

    filtros_activos = sum(1 for v in [
        deporte_sel,
        tipo_sel,
        tipo_cancha_sel,
        fecha_sel,
        hora_sel,
        precio_min_txt,
        precio_max_txt,
        solo_favoritas,
    ] if v)

    return render_template(
        "canchas.html",
        canchas=canchas,
        deportes=DEPORTES_CATALOGO,
        modalidades_por_deporte=MODALIDADES_POR_DEPORTE,
        deporte_seleccionado=deporte_sel,
        modalidades_disponibles=modalidades_disponibles,
        tipo_seleccionado=tipo_sel,
        tipos_cancha=TIPOS_CANCHA,
        tipo_cancha_sel=tipo_cancha_sel,
        busqueda=busqueda,
        fecha_seleccionada=fecha_sel,
        hora_seleccionada=hora_sel,
        precio_min=precio_min_txt,
        precio_max=precio_max_txt,
        solo_favoritas=solo_favoritas,
        horas_disponibles=HORAS_DISPONIBLES,
        fecha_hoy=fecha_hoy,
        vista_mapa=vista_mapa,
        filtros_activos=filtros_activos,
    )


@canchas_bp.route("/cancha/<int:cancha_id>")
def detalle_cancha(cancha_id):
    cancha = obtener_cancha_por_id(cancha_id)
    if not cancha:
        flash("La cancha que buscas no existe.", "error")
        return redirect(url_for("canchas.ver_canchas"))

    # Aseguramos que las reservas fijas estén generadas antes de mostrar disponibilidad al jugador
    generar_reservas_fijas_pendientes(cancha_id=cancha_id)

    hoy = hoy_colombia()
    fecha_hoy = hoy.isoformat()
    fecha_param = request.args.get("fecha", "").strip()
    try:
        fecha_sel_dt = date.fromisoformat(fecha_param) if fecha_param else hoy
        if fecha_sel_dt < hoy:
            fecha_sel_dt = hoy
    except ValueError:
        fecha_sel_dt = hoy

    # Tira ágil de próximos 14 días en zona America/Bogota
    abrev_dias = {idx: ab for idx, _, ab in DIAS_SEMANA}
    fechas_strip = []
    for offset in range(14):
        d = hoy + timedelta(days=offset)
        fechas_strip.append({
            "iso": d.isoformat(),
            "abrev": "Hoy" if offset == 0 else ("Mañ" if offset == 1 else abrev_dias[d.weekday()]),
            "dia": d.day,
        })

    # Si no se especificó fecha y hoy ya no tiene turnos libres, avanzamos a mañana automáticamente
    agenda_dia = obtener_agenda_dia(cancha_id, fecha_sel_dt.isoformat())
    if not fecha_param and not any(f["disponible_jugador"] for f in agenda_dia):
        fecha_sel_dt = hoy + timedelta(days=1)
        agenda_dia = obtener_agenda_dia(cancha_id, fecha_sel_dt.isoformat())

    # Al jugador SOLO le pasamos datos públicos: disponibilidad y precio del turno (nunca quién reservó)
    horarios_jugador = [
        {
            "fecha": f["fecha"],
            "hora": f["hora"],
            "disponible": f["disponible_jugador"],
            "precio": f["precio"],
        }
        for f in agenda_dia
        if not f["pasado"]
    ]

    deporte_principal = cancha["deporte"] if cancha["deporte"] else "Fútbol"
    deportes_cancha = obtener_deportes_de_cancha(cancha["id"], deporte_principal)
    modalidades_cancha = {dep: MODALIDADES_POR_DEPORTE.get(dep, []) for dep in deportes_cancha}
    caracteristicas_lista = [
        item.strip() for item in (cancha["caracteristicas"] or "").split(",") if item.strip()
    ]
    precio_desde, tiene_tarifas = obtener_precio_minimo_cancha(cancha["id"], cancha["precio"])

    favoritos_ids = obtener_ids_favoritos(session.get("usuario_id"))
    usuario_telefono = ""
    if session.get("usuario_id"):
        u = buscar_usuario_por_id(session["usuario_id"])
        if u:
            usuario_telefono = u["telefono"] or ""

    return render_template(
        "reservas.html",
        cancha=cancha,
        precio_desde=precio_desde,
        tiene_tarifas=tiene_tarifas,
        deportes_cancha=deportes_cancha,
        modalidades_cancha=modalidades_cancha,
        caracteristicas_lista=caracteristicas_lista,
        es_favorita=cancha["id"] in favoritos_ids,
        fechas_strip=fechas_strip,
        fecha_seleccionada=fecha_sel_dt.isoformat(),
        horarios_jugador=horarios_jugador,
        hay_libres=any(h["disponible"] for h in horarios_jugador),
        usuario_telefono=usuario_telefono,
        fecha_hoy=fecha_hoy,
    )


@canchas_bp.route("/favoritos/<int:cancha_id>", methods=["POST"])
@requiere_login("Inicia sesión para guardar canchas favoritas.")
def toggle_favorito(cancha_id):
    cancha = obtener_cancha_por_id(cancha_id)
    if not cancha:
        flash("La cancha no existe.", "error")
        return redirect(url_for("canchas.ver_canchas"))

    guardado = alternar_favorito(session["usuario_id"], cancha_id)
    flash(
        f"{cancha['nombre']} guardada en favoritas." if guardado else f"{cancha['nombre']} quitada de favoritas.",
        "exito",
    )
    return redirect(url_retorno_segura(url_for("canchas.ver_canchas")))
