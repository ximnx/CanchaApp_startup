"""Blueprint de Administración: Agenda, Pagos, Tarifas, Clientes, Fijas, Reportes (Excel/PDF) y Recordatorios."""

from datetime import date, timedelta
import io

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for

from config import (
    DEPORTES_CATALOGO,
    DEPORTES_NOMBRES,
    DIAS_SEMANA,
    ESTADOS_PAGO,
    HORAS_DISPONIBLES,
    IMAGENES_PREDETERMINADAS,
    MODALIDADES_POR_DEPORTE,
    TIPOS_CANCHA,
    ahora_colombia,
    hoy_colombia,
    imagen_por_defecto_deporte,
    modalidad_valida,
    normalizar_celular_colombiano,
)
from db.agenda import (
    crear_reserva_fija,
    finalizar_reserva_fija,
    generar_reservas_fijas_pendientes,
    marcar_recordatorio_enviado,
    obtener_clientes_frecuentes,
    obtener_detalle_cliente,
    obtener_mapa_calor_horas_muertas,
    obtener_recordatorios_admin,
    obtener_reporte_ganancias,
    obtener_reservas_fijas_admin,
    sugerir_clientes_admin,
)
from db.canchas import (
    actualizar_cancha,
    actualizar_estado_pago,
    alternar_bloqueo_turno,
    cancelar_reserva,
    crear_cancha,
    crear_reserva_atomica,
    crear_tarifa_cancha,
    eliminar_cancha,
    eliminar_tarifa_cancha,
    obtener_agenda_dia,
    obtener_cancha_por_id,
    obtener_canchas_por_administrador,
    obtener_deportes_de_cancha,
    obtener_tarifas_cancha,
)
from db.partidos import crear_notificacion
from media import formatear_precio, guardar_imagen_subida
from security import requiere_rol

admin_bp = Blueprint("admin", __name__)

NOMBRES_DIA = {idx: nombre for idx, nombre, _ in DIAS_SEMANA}
ABREV_DIA = {idx: abrev for idx, _, abrev in DIAS_SEMANA}


def _etiqueta_dias(dias_csv):
    """Convierte '0,1,2,3,4' en 'Lun a Vie' o 'Sáb, Dom'."""
    nums = sorted({int(x) for x in (dias_csv or "").split(",") if x.isdigit()})
    if nums == [0, 1, 2, 3, 4]:
        return "Lun a Vie"
    if nums == [5, 6]:
        return "Sáb y Dom"
    if nums == [0, 1, 2, 3, 4, 5, 6]:
        return "Todos los días"
    return ", ".join(ABREV_DIA.get(n, str(n)) for n in nums)


def _leer_formulario_cancha(imagen_por_defecto):
    """Extrae y valida los campos al crear o editar una cancha."""
    nombre = request.form.get("nombre", "").strip()
    direccion = request.form.get("direccion", "").strip()
    telefono_raw = request.form.get("telefono", "").strip()
    precio_texto = request.form.get("precio", "").strip()
    deporte = request.form.get("deporte", "Fútbol").strip()
    tipo_futbol = request.form.get("tipo_futbol", "").strip()
    tipo_cancha = request.form.get("tipo_cancha", "Sintética").strip()
    descripcion = request.form.get("descripcion", "").strip()[:500]
    caracteristicas = request.form.get("caracteristicas", "").strip()[:240]
    deportes_extra = [d for d in request.form.getlist("deportes_extra") if d in DEPORTES_NOMBRES]
    img_pred = request.form.get("imagen_predeterminada", "auto").strip()

    if not nombre or not direccion or not precio_texto or deporte not in DEPORTES_NOMBRES:
        return None, "Completa nombre, dirección, precio y deporte."

    if not modalidad_valida(deporte, tipo_futbol):
        return None, f"La modalidad no corresponde a {deporte}."

    telefono = ""
    if telefono_raw:
        telefono = normalizar_celular_colombiano(telefono_raw)
        if not telefono:
            return None, "El teléfono de la cancha debe ser un celular colombiano válido (10 dígitos, empieza por 3)."

    if tipo_cancha not in TIPOS_CANCHA:
        tipo_cancha = "Sintética"

    if not precio_texto.isdigit() or int(precio_texto) <= 0:
        return None, "El precio por hora debe ser un número mayor que cero."

    ruta_imagen = imagen_por_defecto
    if img_pred == "auto":
        ruta_imagen = imagen_por_defecto_deporte(deporte)
    elif img_pred in IMAGENES_PREDETERMINADAS:
        ruta_imagen = img_pred

    nueva_foto, error_foto = guardar_imagen_subida(request.files.get("foto"), "cancha", session["usuario_id"])
    if error_foto:
        return None, error_foto
    if nueva_foto:
        ruta_imagen = nueva_foto

    return {
        "nombre": nombre,
        "direccion": direccion,
        "telefono": telefono,
        "precio": int(precio_texto),
        "deporte": deporte,
        "tipo_futbol": tipo_futbol,
        "deportes_extra": deportes_extra,
        "tipo_cancha": tipo_cancha,
        "descripcion": descripcion,
        "caracteristicas": caracteristicas,
        "imagen": ruta_imagen,
    }, None


# ---------------- FASE 1, 2, 3, 5: AGENDA Y GESTIÓN DE CANCHAS ----------------

@admin_bp.route("/administrador")
@requiere_rol("administrador", destino_error="inicio.inicio", mensaje="Acceso exclusivo para administradores.")
def panel_administrador():
    admin_id = session["usuario_id"]
    # Proceso idempotente: asegura turnos generados de reservas fijas para próximas 8 semanas
    generar_reservas_fijas_pendientes(administrador_id=admin_id)

    tab_activo = request.args.get("tab", "agenda").strip()
    if tab_activo not in ("agenda", "canchas"):
        tab_activo = "agenda"

    mis_canchas = obtener_canchas_por_administrador(admin_id)
    hoy = hoy_colombia()
    fecha_hoy = hoy.isoformat()

    # Selección de cancha activa (selector solo visible si hay más de 1)
    cancha_id_param = request.args.get("cancha_id", "").strip()
    cancha_activa = None
    if mis_canchas:
        if cancha_id_param.isdigit():
            cancha_activa = next((c for c in mis_canchas if c["id"] == int(cancha_id_param)), None)
        if not cancha_activa:
            cancha_activa = mis_canchas[0]

    # Fecha seleccionada y tira ágil de días (hoy - 2 hasta hoy + 11)
    fecha_param = request.args.get("fecha", "").strip()
    try:
        fecha_sel_dt = date.fromisoformat(fecha_param) if fecha_param else hoy
    except ValueError:
        fecha_sel_dt = hoy
    fecha_sel = fecha_sel_dt.isoformat()

    base_strip = fecha_sel_dt if abs((fecha_sel_dt - hoy).days) > 7 else hoy
    dias_strip = []
    for offset in range(-2, 12):
        d = base_strip + timedelta(days=offset)
        dias_strip.append({
            "iso": d.isoformat(),
            "abrev": "Hoy" if d == hoy else ABREV_DIA[d.weekday()],
            "dia": d.day,
            "es_hoy": d == hoy,
        })

    franjas = obtener_agenda_dia(cancha_activa["id"], fecha_sel) if cancha_activa else []
    clientes_sugeridos = sugerir_clientes_admin(admin_id) if tab_activo == "agenda" else []
    recordatorios_pend = sum(1 for r in obtener_recordatorios_admin(admin_id) if not r["enviado"])

    # Datos para la pestaña Canchas (tarifas + reservas fijas + deportes)
    canchas_detalle = []
    if tab_activo == "canchas":
        for c in mis_canchas:
            dep_p = c["deporte"] if c["deporte"] else "Fútbol"
            tarifas = [
                {
                    "id": t["id"],
                    "dias_texto": _etiqueta_dias(t["dias_semana"]),
                    "hora_inicio": t["hora_inicio"],
                    "hora_fin": t["hora_fin"],
                    "precio": t["precio"],
                }
                for t in obtener_tarifas_cancha(c["id"])
            ]
            fijas = [
                {
                    "id": rf["id"],
                    "dia_nombre": NOMBRES_DIA.get(rf["dia_semana"], ""),
                    "hora": rf["hora"],
                    "nombre_cliente": rf["nombre_cliente"],
                    "telefono_cliente": rf["telefono_cliente"],
                }
                for rf in obtener_reservas_fijas_admin(admin_id, c["id"])
            ]
            canchas_detalle.append({
                "cancha": c,
                "deportes_ofrecidos": obtener_deportes_de_cancha(c["id"], dep_p),
                "tarifas": tarifas,
                "fijas": fijas,
            })

    # Choques pendientes de confirmación si el admin intentó crear una reserva fija con fechas ocupadas
    choques_fija = session.pop("choques_fija_pendiente", None)

    return render_template(
        "administrador.html",
        tab_activo=tab_activo,
        mis_canchas=mis_canchas,
        cancha_activa=cancha_activa,
        canchas_detalle=canchas_detalle,
        dias_strip=dias_strip,
        fecha_sel=fecha_sel,
        fecha_hoy=fecha_hoy,
        fecha_ant=(fecha_sel_dt - timedelta(days=1)).isoformat(),
        fecha_sig=(fecha_sel_dt + timedelta(days=1)).isoformat(),
        franjas=franjas,
        clientes_sugeridos=clientes_sugeridos,
        recordatorios_pend=recordatorios_pend,
        choques_fija=choques_fija,
        dias_semana=DIAS_SEMANA,
        horas_disponibles=HORAS_DISPONIBLES,
        deportes_catalogo=DEPORTES_CATALOGO,
        modalidades_por_deporte=MODALIDADES_POR_DEPORTE,
        tipos_cancha=TIPOS_CANCHA,
        tipos_futbol=MODALIDADES_POR_DEPORTE["Fútbol"],
    )


@admin_bp.route("/administrador/agendar", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def agendar_manual():
    """Agenda una reserva presencial o telefónica (sin crear cuenta de usuario)."""
    admin_id = session["usuario_id"]
    cancha_id = request.form.get("cancha_id", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    nombre_cliente = request.form.get("nombre_cliente", "").strip()
    telefono_raw = request.form.get("telefono_cliente", "").strip()
    estado_pago = request.form.get("estado_pago", "pendiente").strip()
    monto_abonado = request.form.get("monto_abonado", "0").strip()

    if not cancha_id.isdigit() or not fecha or hora not in HORAS_DISPONIBLES:
        flash("Datos de turno no válidos.", "error")
        return redirect(url_for("admin.panel_administrador"))

    cancha_id_num = int(cancha_id)
    cancha = obtener_cancha_por_id(cancha_id_num)
    if not cancha or cancha["administrador_id"] != admin_id:
        flash("No puedes agendar en una cancha que no te pertenece.", "error")
        return redirect(url_for("admin.panel_administrador"))

    if len(nombre_cliente) < 2:
        flash("Escribe a nombre de quién queda la reserva.", "error")
        return redirect(url_for("admin.panel_administrador", cancha_id=cancha_id_num, fecha=fecha))

    telefono = ""
    if telefono_raw:
        telefono = normalizar_celular_colombiano(telefono_raw)
        if not telefono:
            flash("Si ingresas celular, debe ser colombiano válido (10 dígitos, empieza por 3).", "error")
            return redirect(url_for("admin.panel_administrador", cancha_id=cancha_id_num, fecha=fecha))

    ok, msg, _rid, _precio = crear_reserva_atomica(
        usuario_id=admin_id,
        cancha_id=cancha_id_num,
        fecha_iso=fecha,
        hora_hm=hora,
        nombre_reserva=nombre_cliente,
        deporte_reserva=cancha["deporte"] or "Fútbol",
        modalidad_reserva=cancha["tipo_futbol"],
        origen="admin",
        telefono_reserva=telefono,
        estado_pago=estado_pago if estado_pago in ESTADOS_PAGO else "pendiente",
        monto_abonado=int(monto_abonado) if monto_abonado.isdigit() else 0,
    )
    flash(f"Turno agendado para {nombre_cliente} ({hora})." if ok else msg, "exito" if ok else "error")
    return redirect(url_for("admin.panel_administrador", cancha_id=cancha_id_num, fecha=fecha))


@admin_bp.route("/administrador/pago/<int:reserva_id>", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def cambiar_estado_pago_admin(reserva_id):
    nuevo_estado = request.form.get("estado_pago", "").strip()
    monto_abonado = request.form.get("monto_abonado", "").strip()
    cancha_id = request.form.get("cancha_id", "").strip()
    fecha = request.form.get("fecha", "").strip()

    ok, msg = actualizar_estado_pago(
        reserva_id,
        session["usuario_id"],
        nuevo_estado,
        monto_abonado if monto_abonado else None,
    )
    flash(msg, "exito" if ok else "error")
    return redirect(url_for("admin.panel_administrador", cancha_id=cancha_id or None, fecha=fecha or None))


@admin_bp.route("/administrador/cancelar_reserva/<int:reserva_id>", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def cancelar_reserva_admin(reserva_id):
    motivo = request.form.get("motivo", "").strip()
    cancha_id = request.form.get("cancha_id", "").strip()
    fecha = request.form.get("fecha", "").strip()

    ok, msg, reserva = cancelar_reserva(reserva_id, "administrador", session["usuario_id"], motivo)
    if ok and reserva and reserva["origen"] != "admin" and reserva["usuario_id"] != session["usuario_id"]:
        texto_motivo = f" Motivo: {motivo}." if motivo else ""
        crear_notificacion(
            reserva["usuario_id"],
            "Reserva cancelada por la cancha",
            f"Tu turno en {reserva['nombre_cancha']} ({reserva['fecha']} · {reserva['hora']}) fue cancelado.{texto_motivo}",
            "/mis_reservas?tab=historial",
            "reserva",
            ahora_colombia().isoformat(),
        )
    flash(msg, "exito" if ok else "error")
    return redirect(url_for("admin.panel_administrador", cancha_id=cancha_id or None, fecha=fecha or None))


@admin_bp.route("/administrador/bloquear_turno", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def bloquear_turno_agenda():
    cancha_id = request.form.get("cancha_id", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()

    if not cancha_id.isdigit() or not fecha or hora not in HORAS_DISPONIBLES:
        flash("Datos de turno no válidos.", "error")
        return redirect(url_for("admin.panel_administrador"))

    ok, msg = alternar_bloqueo_turno(int(cancha_id), fecha, hora, session["usuario_id"])
    flash(msg, "exito" if ok else "error")
    return redirect(url_for("admin.panel_administrador", cancha_id=int(cancha_id), fecha=fecha))


# ---------------- FASE 3: TARIFAS POR HORARIO ----------------

@admin_bp.route("/administrador/tarifas/agregar", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def agregar_tarifa_admin():
    cancha_id = request.form.get("cancha_id", "").strip()
    dias = request.form.getlist("dias_semana")
    hora_inicio = request.form.get("hora_inicio", "").strip()
    hora_fin = request.form.get("hora_fin", "").strip()
    precio_txt = request.form.get("precio", "").strip()

    if not cancha_id.isdigit() or not precio_txt.isdigit():
        flash("Completa cancha, días, horario y un precio válido.", "error")
        return redirect(url_for("admin.panel_administrador", tab="canchas"))

    ok, msg = crear_tarifa_cancha(
        int(cancha_id), session["usuario_id"], dias, hora_inicio, hora_fin, int(precio_txt)
    )
    flash(msg, "exito" if ok else "error")
    return redirect(url_for("admin.panel_administrador", tab="canchas"))


@admin_bp.route("/administrador/tarifas/eliminar/<int:tarifa_id>", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def eliminar_tarifa_admin(tarifa_id):
    if eliminar_tarifa_cancha(tarifa_id, session["usuario_id"]):
        flash("Tarifa eliminada.", "exito")
    else:
        flash("No se pudo eliminar esa tarifa.", "error")
    return redirect(url_for("admin.panel_administrador", tab="canchas"))


# ---------------- FASE 5: RESERVAS FIJAS ----------------

@admin_bp.route("/administrador/fijas/crear", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def crear_fija_admin():
    cancha_id = request.form.get("cancha_id", "").strip()
    dia_semana = request.form.get("dia_semana", "").strip()
    hora = request.form.get("hora", "").strip()
    nombre_cliente = request.form.get("nombre_cliente", "").strip()
    telefono_raw = request.form.get("telefono_cliente", "").strip()
    fecha_inicio = request.form.get("fecha_inicio", hoy_colombia().isoformat()).strip()
    omitir_choques = request.form.get("omitir_choques", "") == "1"

    if not cancha_id.isdigit() or not dia_semana.isdigit():
        flash("Datos inválidos para la reserva fija.", "error")
        return redirect(url_for("admin.panel_administrador"))

    telefono = ""
    if telefono_raw:
        telefono = normalizar_celular_colombiano(telefono_raw)
        if not telefono:
            flash("Celular inválido (debe tener 10 dígitos y empezar por 3).", "error")
            return redirect(url_for("admin.panel_administrador", cancha_id=int(cancha_id)))

    ok, msg, choques = crear_reserva_fija(
        int(cancha_id),
        session["usuario_id"],
        int(dia_semana),
        hora,
        nombre_cliente,
        telefono,
        fecha_inicio,
        omitir_choques=omitir_choques,
    )
    if not ok and choques:
        # Guardamos los datos en sesión para mostrar las fechas en conflicto y preguntar si las omite
        session["choques_fija_pendiente"] = {
            "cancha_id": int(cancha_id),
            "dia_semana": int(dia_semana),
            "dia_nombre": NOMBRES_DIA.get(int(dia_semana), ""),
            "hora": hora,
            "nombre_cliente": nombre_cliente,
            "telefono_cliente": telefono,
            "fecha_inicio": fecha_inicio,
            "choques": choques,
        }
        flash(f"Hay {len(choques)} fecha(s) ocupada(s): {', '.join(choques)}. Confirma si deseas omitirlas.", "error")
        return redirect(url_for("admin.panel_administrador", cancha_id=int(cancha_id)))

    flash(msg, "exito" if ok else "error")
    return redirect(url_for("admin.panel_administrador", cancha_id=int(cancha_id)))


@admin_bp.route("/administrador/fijas/finalizar/<int:fija_id>", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def finalizar_fija_admin(fija_id):
    if finalizar_reserva_fija(fija_id, session["usuario_id"]):
        flash("Reserva fija finalizada y turnos futuros liberados.", "exito")
    else:
        flash("No se pudo finalizar la reserva fija.", "error")
    return redirect(url_for("admin.panel_administrador", tab="canchas"))


# ---------------- FASE 4: CLIENTES FRECUENTES ----------------

@admin_bp.route("/administrador/clientes")
@requiere_rol("administrador", destino_error="inicio.inicio")
def ver_clientes_admin():
    busqueda = request.args.get("q", "").strip()
    clientes = obtener_clientes_frecuentes(session["usuario_id"], busqueda)
    return render_template("admin_clientes.html", clientes=clientes, busqueda=busqueda, cliente_detalle=None)


@admin_bp.route("/administrador/clientes/detalle")
@requiere_rol("administrador", destino_error="inicio.inicio")
def detalle_cliente_admin():
    clave = request.args.get("clave", "").strip()
    info, reservas = obtener_detalle_cliente(session["usuario_id"], clave)
    if not info:
        flash("Cliente no encontrado en tus canchas.", "error")
        return redirect(url_for("admin.ver_clientes_admin"))
    return render_template("admin_clientes.html", clientes=[], busqueda="", cliente_detalle=info, reservas_cliente=reservas)


# ---------------- FASE 7: RECORDATORIOS POR WHATSAPP ----------------

@admin_bp.route("/administrador/recordatorios")
@requiere_rol("administrador", destino_error="inicio.inicio")
def ver_recordatorios_admin():
    generar_reservas_fijas_pendientes(administrador_id=session["usuario_id"])
    recordatorios = obtener_recordatorios_admin(session["usuario_id"])
    return render_template("admin_recordatorios.html", recordatorios=recordatorios)


@admin_bp.route("/administrador/recordatorios/<int:reserva_id>/marcar", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def marcar_recordatorio_admin(reserva_id):
    ok, msg = marcar_recordatorio_enviado(reserva_id, session["usuario_id"])
    flash(msg, "exito" if ok else "error")
    return redirect(url_for("admin.ver_recordatorios_admin"))


# ---------------- FASE 6: REPORTES Y EXPORTACIÓN EXCEL / PDF ----------------

def _leer_filtros_reporte(admin_id):
    mis_canchas = obtener_canchas_por_administrador(admin_id)
    cancha_id_raw = request.args.get("cancha_id", "").strip()
    cancha_id = None
    nombre_cancha = "Todas mis canchas"
    if cancha_id_raw.isdigit():
        match = next((c for c in mis_canchas if c["id"] == int(cancha_id_raw)), None)
        if match:
            cancha_id = match["id"]
            nombre_cancha = match["nombre"]
    elif len(mis_canchas) == 1:
        cancha_id = mis_canchas[0]["id"]
        nombre_cancha = mis_canchas[0]["nombre"]

    modo = request.args.get("modo", "mes").strip()
    if modo not in ("dia", "mes"):
        modo = "mes"
    hoy = hoy_colombia()
    periodo_def = hoy.isoformat() if modo == "dia" else hoy.strftime("%Y-%m")
    periodo = request.args.get("periodo", "").strip() or periodo_def
    if modo == "dia" and len(periodo) != 10:
        periodo = hoy.isoformat()
    if modo == "mes" and len(periodo) != 7:
        periodo = hoy.strftime("%Y-%m")

    return mis_canchas, cancha_id, nombre_cancha, modo, periodo


@admin_bp.route("/administrador/reportes")
@requiere_rol("administrador", destino_error="inicio.inicio")
def ver_reportes_admin():
    admin_id = session["usuario_id"]
    mis_canchas, cancha_id, nombre_cancha, modo, periodo = _leer_filtros_reporte(admin_id)
    reporte = obtener_reporte_ganancias(admin_id, cancha_id, modo, periodo)
    mes_calor = periodo[:7]
    calor = obtener_mapa_calor_horas_muertas(admin_id, cancha_id, mes_calor)

    return render_template(
        "admin_reportes.html",
        mis_canchas=mis_canchas,
        cancha_id_sel=cancha_id,
        nombre_cancha=nombre_cancha,
        modo=modo,
        periodo=periodo,
        reporte=reporte,
        calor=calor,
    )


@admin_bp.route("/administrador/reportes/exportar.xlsx")
@requiere_rol("administrador", destino_error="inicio.inicio")
def exportar_reporte_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    admin_id = session["usuario_id"]
    _, cancha_id, nombre_cancha, modo, periodo = _leer_filtros_reporte(admin_id)
    reporte = obtener_reporte_ganancias(admin_id, cancha_id, modo, periodo)
    calor = obtener_mapa_calor_horas_muertas(admin_id, cancha_id, periodo[:7])

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen y Reservas"

    azul_fill = PatternFill("solid", fgColor="0D1B34")
    blanco_bold = Font(color="FFFFFF", bold=True)
    bold = Font(bold=True)

    ws.append(["Ready Match — Reporte de Ganancias"])
    ws["A1"].font = Font(size=13, bold=True, color="0D1B34")
    ws.append(["Cancha:", nombre_cancha, "Periodo:", f"{modo.capitalize()} {periodo}"])
    ws.append([])
    ws.append(["Alquileres activos", reporte["total_alquileres"], "Canceladas", reporte["total_canceladas"]])
    ws.append(["Total generado", formatear_precio(reporte["total_ingresos"])])
    ws.append(["Cobrado (pagado + abonos)", formatear_precio(reporte["total_cobrado"])])
    ws.append(["Pendiente por cobrar", formatear_precio(reporte["total_pendiente"])])
    ws.append([])

    encabezados = ["Fecha", "Hora", "Cancha", "Cliente", "Pago", "Precio", "Cobrado", "Pendiente"]
    ws.append(encabezados)
    fila_enc = ws.max_row
    for col_idx in range(1, len(encabezados) + 1):
        celda = ws.cell(row=fila_enc, column=col_idx)
        celda.fill = azul_fill
        celda.font = blanco_bold

    for r in reporte["reservas"]:
        ws.append([
            r["fecha"],
            r["hora"],
            r["cancha"],
            r["cliente"],
            r["estado_pago"].capitalize(),
            formatear_precio(r["precio"]),
            formatear_precio(r["cobrado"]),
            formatear_precio(r["pendiente"]),
        ])

    for col in ("A", "B", "C", "D", "E", "F", "G", "H"):
        ws.column_dimensions[col].width = 18

    # Segunda hoja: Horas muertas del mes
    ws2 = wb.create_sheet("Horas muertas")
    ws2.append(["Día", "Hora", "Ocupación %", "Alquileres", "Capacidad"])
    for col_idx in range(1, 6):
        c = ws2.cell(row=1, column=col_idx)
        c.fill = azul_fill
        c.font = blanco_bold
    for h in calor["horas_muertas"]:
        ws2.append([h["dia_nombre"], h["hora"], f"{h['pct']}%", h["usados"], h["capacidad"]])
    for col in ("A", "B", "C", "D", "E"):
        ws2.column_dimensions[col].width = 16

    salida = io.BytesIO()
    wb.save(salida)
    salida.seek(0)
    return send_file(
        salida,
        as_attachment=True,
        download_name=f"ready_match_reporte_{periodo}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@admin_bp.route("/administrador/reportes/exportar.pdf")
@requiere_rol("administrador", destino_error="inicio.inicio")
def exportar_reporte_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    admin_id = session["usuario_id"]
    _, cancha_id, nombre_cancha, modo, periodo = _leer_filtros_reporte(admin_id)
    reporte = obtener_reporte_ganancias(admin_id, cancha_id, modo, periodo)
    calor = obtener_mapa_calor_horas_muertas(admin_id, cancha_id, periodo[:7])

    salida = io.BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    estilos = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph("Ready Match — Reporte de Ganancias y Control", estilos["Title"]))
    elementos.append(Paragraph(f"Establecimiento: <b>{nombre_cancha}</b> | Periodo: <b>{modo.capitalize()} {periodo}</b>", estilos["Normal"]))
    elementos.append(Spacer(1, 12))

    resumen_datos = [
        ["Métrica", "Valor"],
        ["Canchas alquiladas (activas)", str(reporte["total_alquileres"])],
        ["Reservas canceladas", str(reporte["total_canceladas"])],
        ["Total generado", formatear_precio(reporte["total_ingresos"])],
        ["Cobrado (pagado + abonos)", formatear_precio(reporte["total_cobrado"])],
        ["Pendiente por cobrar", formatear_precio(reporte["total_pendiente"])],
    ]
    tabla_res = Table(resumen_datos, colWidths=[260, 180])
    tabla_res.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D1B34")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E4")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FB")]),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabla_res)
    elementos.append(Spacer(1, 16))

    if reporte["reservas"]:
        elementos.append(Paragraph("Detalle de reservas activas", estilos["Heading3"]))
        filas_det = [["Fecha", "Hora", "Cancha", "Cliente", "Pago", "Cobrado", "Pendiente"]]
        for r in reporte["reservas"][:60]:
            filas_det.append([
                r["fecha"],
                r["hora"],
                r["cancha"][:22],
                r["cliente"][:20],
                r["estado_pago"].capitalize(),
                formatear_precio(r["cobrado"]),
                formatear_precio(r["pendiente"]),
            ])
        tabla_det = Table(filas_det, colWidths=[68, 44, 118, 102, 60, 74, 74])
        tabla_det.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0066EE")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E4")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        elementos.append(tabla_det)
        elementos.append(Spacer(1, 14))

    elementos.append(Paragraph(f"Horas muertas del mes ({calor['mes']})", estilos["Heading3"]))
    filas_hm = [["Día", "Hora", "Ocupación", "Alquileres"]]
    for h in calor["horas_muertas"]:
        filas_hm.append([h["dia_nombre"], h["hora"], f"{h['pct']}%", f"{h['usados']}/{h['capacidad']}"])
    tabla_hm = Table(filas_hm, colWidths=[120, 80, 100, 100])
    tabla_hm.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D1B34")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E4")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.append(tabla_hm)

    doc.build(elementos)
    salida.seek(0)
    return send_file(
        salida,
        as_attachment=True,
        download_name=f"ready_match_reporte_{periodo}.pdf",
        mimetype="application/pdf",
    )


# ---------------- CRUD DE CANCHAS ----------------

@admin_bp.route("/administrador/agregar_cancha", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def agregar_cancha():
    datos, error = _leer_formulario_cancha("imagenes/cancha1.jpg")
    if error:
        flash(error, "error")
        return redirect(url_for("admin.panel_administrador", tab="canchas"))

    crear_cancha(
        datos["nombre"],
        datos["direccion"],
        datos["precio"],
        datos["tipo_futbol"],
        datos["imagen"],
        session["usuario_id"],
        datos["deporte"],
        datos["deportes_extra"],
        datos["tipo_cancha"],
        datos["descripcion"],
        datos["caracteristicas"],
        datos["telefono"],
    )
    flash(f"Cancha '{datos['nombre']}' registrada.", "exito")
    return redirect(url_for("admin.panel_administrador", tab="canchas"))


@admin_bp.route("/administrador/editar_cancha/<int:cancha_id>", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def editar_cancha(cancha_id):
    cancha = obtener_cancha_por_id(cancha_id)
    if not cancha or cancha["administrador_id"] != session["usuario_id"]:
        flash("No puedes editar una cancha que no te pertenece.", "error")
        return redirect(url_for("admin.panel_administrador", tab="canchas"))

    datos, error = _leer_formulario_cancha(cancha["imagen"])
    if error:
        flash(error, "error")
        return redirect(url_for("admin.panel_administrador", tab="canchas"))

    actualizar_cancha(
        cancha_id,
        session["usuario_id"],
        datos["nombre"],
        datos["direccion"],
        datos["precio"],
        datos["tipo_futbol"],
        datos["imagen"],
        datos["deporte"],
        datos["deportes_extra"],
        datos["tipo_cancha"],
        datos["descripcion"],
        datos["caracteristicas"],
        datos["telefono"],
    )
    flash(f"Cancha '{datos['nombre']}' actualizada.", "exito")
    return redirect(url_for("admin.panel_administrador", tab="canchas"))


@admin_bp.route("/administrador/eliminar_cancha/<int:cancha_id>", methods=["POST"])
@requiere_rol("administrador", destino_error="inicio.inicio")
def eliminar_cancha_admin(cancha_id):
    if eliminar_cancha(cancha_id, session["usuario_id"]):
        flash("Cancha eliminada.", "exito")
    else:
        flash("No puedes eliminar una cancha que no te pertenece.", "error")
    return redirect(url_for("admin.panel_administrador", tab="canchas"))
