"""Lógica de datos para Clientes (Fase 4), Reservas Fijas (Fase 5), Reportes (Fase 6) y Recordatorios (Fase 7)."""

import calendar
from datetime import date, timedelta
from urllib.parse import quote

from config import (
    DIAS_SEMANA,
    HORAS_DISPONIBLES,
    SEMANAS_VENTANA_FIJAS,
    ahora_colombia,
    fecha_hora_colombia,
    hoy_colombia,
    normalizar_celular_colombiano,
    telefono_whatsapp_co,
)
from db.canchas import crear_reserva_atomica
from db.connection import obtener_conexion


# ---------------- FASE 4: CLIENTES FRECUENTES Y AUTOCOMPLETADO ----------------

def _clave_y_datos_cliente(fila):
    """Genera una clave estable separando clientes con cuenta web de agendados por admin."""
    if fila["origen"] != "admin" and fila["usuario_id"] != fila["administrador_id"]:
        clave = f"u:{fila['usuario_id']}"
        nombre = (fila["nombre_usuario"] or fila["nombre_reserva"] or "Jugador").strip()
        tel = normalizar_celular_colombiano(fila["telefono_reserva"] or fila["telefono_usuario"] or "")
        es_cuenta = True
    else:
        nombre = (fila["nombre_reserva"] or "Cliente sin nombre").strip()
        tel = normalizar_celular_colombiano(fila["telefono_reserva"] or "")
        clave = f"a:{nombre.lower()}|{tel}"
        es_cuenta = False
    return clave, nombre, tel, es_cuenta


def obtener_clientes_frecuentes(administrador_id, busqueda=""):
    """Deriva la lista de clientes frecuentes de las canchas del administrador desde reservas."""
    conexion = obtener_conexion()
    filas = conexion.execute(
        """
        SELECT reservas.*, canchas.nombre AS nombre_cancha,
               canchas.administrador_id AS administrador_id,
               usuarios.nombre AS nombre_usuario,
               usuarios.telefono AS telefono_usuario
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        JOIN usuarios ON reservas.usuario_id = usuarios.id
        WHERE canchas.administrador_id = ?
        ORDER BY reservas.fecha DESC, reservas.hora DESC
        """,
        (administrador_id,),
    ).fetchall()
    conexion.close()

    ahora = ahora_colombia()
    agrupados = {}

    for fila in filas:
        clave, nombre, tel, es_cuenta = _clave_y_datos_cliente(fila)
        if clave not in agrupados:
            agrupados[clave] = {
                "clave": clave,
                "nombre": nombre,
                "telefono": tel,
                "es_cuenta": es_cuenta,
                "partidos_jugados": 0,
                "proximas": 0,
                "canceladas": 0,
                "ultima_fecha": "",
            }
        cliente = agrupados[clave]
        if tel and not cliente["telefono"]:
            cliente["telefono"] = tel

        if fila["estado"] in ("confirmada", "pendiente"):
            dt_turno = fecha_hora_colombia(fila["fecha"], fila["hora"])
            if dt_turno <= ahora:
                cliente["partidos_jugados"] += 1
                if not cliente["ultima_fecha"] or fila["fecha"] > cliente["ultima_fecha"]:
                    cliente["ultima_fecha"] = fila["fecha"]
            else:
                cliente["proximas"] += 1
        elif fila["estado"] == "cancelada":
            cliente["canceladas"] += 1

    lista = list(agrupados.values())
    q = (busqueda or "").strip().lower()
    if q:
        q_digitos = normalizar_celular_colombiano(q) or "".join(ch for ch in q if ch.isdigit())
        filtrada = []
        for c in lista:
            if q in c["nombre"].lower():
                filtrada.append(c)
            elif q_digitos and q_digitos in (c["telefono"] or ""):
                filtrada.append(c)
        lista = filtrada

    lista.sort(key=lambda x: (-x["partidos_jugados"], -x["proximas"], x["nombre"].lower()))
    return lista


def obtener_detalle_cliente(administrador_id, clave_cliente):
    """Devuelve los datos y el historial completo de reservas de un cliente en las canchas del admin."""
    conexion = obtener_conexion()
    filas = conexion.execute(
        """
        SELECT reservas.*, canchas.nombre AS nombre_cancha,
               canchas.administrador_id AS administrador_id,
               usuarios.nombre AS nombre_usuario,
               usuarios.telefono AS telefono_usuario
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        JOIN usuarios ON reservas.usuario_id = usuarios.id
        WHERE canchas.administrador_id = ?
        ORDER BY reservas.fecha DESC, reservas.hora DESC
        """,
        (administrador_id,),
    ).fetchall()
    conexion.close()

    ahora = ahora_colombia()
    info = None
    reservas_cliente = []
    for fila in filas:
        clave, nombre, tel, es_cuenta = _clave_y_datos_cliente(fila)
        if clave != clave_cliente:
            continue
        if info is None:
            info = {
                "clave": clave,
                "nombre": nombre,
                "telefono": tel,
                "es_cuenta": es_cuenta,
                "partidos_jugados": 0,
                "proximas": 0,
            }
        if tel and not info["telefono"]:
            info["telefono"] = tel
        if fila["estado"] in ("confirmada", "pendiente"):
            if fecha_hora_colombia(fila["fecha"], fila["hora"]) <= ahora:
                info["partidos_jugados"] += 1
            else:
                info["proximas"] += 1
        reservas_cliente.append(fila)

    return info, reservas_cliente


def sugerir_clientes_admin(administrador_id):
    """Lista compacta de clientes previos (nombre, teléfono) para autocompletar al agendar."""
    clientes = obtener_clientes_frecuentes(administrador_id)
    return [{"nombre": c["nombre"], "telefono": c["telefono"]} for c in clientes[:80]]


# ---------------- FASE 5: RESERVAS FIJAS SEMANALES ----------------

def fechas_ventana_fija(dia_semana, fecha_inicio_iso, semanas=SEMANAS_VENTANA_FIJAS):
    """Calcula las fechas semanales dentro de la ventana móvil desde max(hoy, fecha_inicio)."""
    hoy = hoy_colombia()
    try:
        inicio = date.fromisoformat(fecha_inicio_iso)
    except ValueError:
        inicio = hoy
    desde = max(hoy, inicio)
    hasta = hoy + timedelta(days=7 * semanas)

    desfase = (int(dia_semana) - desde.weekday()) % 7
    actual = desde + timedelta(days=desfase)
    fechas = []
    while actual <= hasta:
        fechas.append(actual.isoformat())
        actual += timedelta(days=7)
    return fechas


def verificar_choques_reserva_fija(cancha_id, dia_semana, hora_hm, fecha_inicio_iso):
    """Devuelve la lista de fechas de la ventana que ya están ocupadas o bloqueadas."""
    fechas = fechas_ventana_fija(dia_semana, fecha_inicio_iso)
    if not fechas:
        return []

    conexion = obtener_conexion()
    choques = []
    for f_iso in fechas:
        ocupada = conexion.execute(
            """
            SELECT id FROM reservas
            WHERE cancha_id = ? AND fecha = ? AND hora = ? AND estado IN ('confirmada', 'pendiente')
            """,
            (cancha_id, f_iso, hora_hm),
        ).fetchone()
        bloqueada = conexion.execute(
            "SELECT id FROM horarios WHERE cancha_id = ? AND fecha = ? AND hora = ? AND bloqueado = 1",
            (cancha_id, f_iso, hora_hm),
        ).fetchone()
        if ocupada or bloqueada:
            choques.append(f_iso)
    conexion.close()
    return choques


def generar_reservas_fijas_pendientes(administrador_id=None, cancha_id=None):
    """
    Proceso idempotente que genera las reservas reales de las próximas 8 semanas
    para todas las reservas fijas activas, respetando excepciones y turnos ocupados.
    """
    conexion = obtener_conexion()
    consulta = """
        SELECT rf.*, canchas.administrador_id AS administrador_id
        FROM reservas_fijas rf
        JOIN canchas ON rf.cancha_id = canchas.id
        WHERE rf.activa = 1
    """
    params = []
    if administrador_id:
        consulta += " AND canchas.administrador_id = ?"
        params.append(administrador_id)
    if cancha_id:
        consulta += " AND rf.cancha_id = ?"
        params.append(cancha_id)

    fijas = conexion.execute(consulta, params).fetchall()

    excepciones_por_fija = {}
    for rf in fijas:
        excs = {
            e["fecha"]
            for e in conexion.execute(
                "SELECT fecha FROM reservas_fijas_excepciones WHERE reserva_fija_id = ?",
                (rf["id"],),
            ).fetchall()
        }
        excepciones_por_fija[rf["id"]] = excs
    conexion.close()

    generadas = 0
    for rf in fijas:
        excs = excepciones_por_fija.get(rf["id"], set())
        fechas = fechas_ventana_fija(rf["dia_semana"], rf["fecha_inicio"])
        usuario_destino = rf["usuario_id"] or rf["administrador_id"]
        origen_res = "web" if rf["usuario_id"] and rf["usuario_id"] != rf["administrador_id"] else "admin"

        for f_iso in fechas:
            if f_iso in excs:
                continue
            ok, _, _, _ = crear_reserva_atomica(
                usuario_id=usuario_destino,
                cancha_id=rf["cancha_id"],
                fecha_iso=f_iso,
                hora_hm=rf["hora"],
                nombre_reserva=rf["nombre_cliente"],
                deporte_reserva=rf["deporte_reserva"],
                modalidad_reserva=rf["modalidad_reserva"],
                origen=origen_res,
                telefono_reserva=rf["telefono_cliente"],
                reserva_fija_id=rf["id"],
            )
            if ok:
                generadas += 1
    return generadas


def crear_reserva_fija(
    cancha_id,
    administrador_id,
    dia_semana,
    hora_hm,
    nombre_cliente,
    telefono_cliente,
    fecha_inicio_iso,
    deporte_reserva="Fútbol",
    modalidad_reserva="",
    omitir_choques=False,
):
    """Crea una reserva fija semanal. Si hay choques y omitir_choques=False, devuelve las fechas en conflicto."""
    if hora_hm not in HORAS_DISPONIBLES:
        return False, "Hora no válida.", []
    if not (0 <= int(dia_semana) <= 6):
        return False, "Día de la semana no válido.", []
    if len(nombre_cliente.strip()) < 2:
        return False, "Escribe el nombre del cliente.", []

    conexion = obtener_conexion()
    cancha = conexion.execute(
        "SELECT id, deporte, tipo_futbol FROM canchas WHERE id = ? AND administrador_id = ?",
        (cancha_id, administrador_id),
    ).fetchone()
    if not cancha:
        conexion.close()
        return False, "No puedes crear reservas fijas en una cancha que no te pertenece.", []

    choques = verificar_choques_reserva_fija(cancha_id, int(dia_semana), hora_hm, fecha_inicio_iso)
    if choques and not omitir_choques:
        conexion.close()
        return False, "Hay fechas ocupadas en las próximas semanas.", choques

    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO reservas_fijas (
            cancha_id, dia_semana, hora, nombre_cliente, telefono_cliente,
            usuario_id, deporte_reserva, modalidad_reserva, fecha_inicio, activa, creada_en
        )
        VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, 1, ?)
        """,
        (
            cancha_id,
            int(dia_semana),
            hora_hm,
            nombre_cliente.strip(),
            telefono_cliente,
            deporte_reserva or cancha["deporte"] or "Fútbol",
            modalidad_reserva or cancha["tipo_futbol"],
            fecha_inicio_iso,
            ahora_colombia().isoformat(),
        ),
    )
    fija_id = cursor.lastrowid

    # Si el admin decidió omitir los choques, los marcamos como excepciones para respetar las reservas previas
    for f_ch in choques:
        cursor.execute(
            """
            INSERT OR IGNORE INTO reservas_fijas_excepciones (reserva_fija_id, fecha, motivo, creada_en)
            VALUES (?, ?, 'Turno ya ocupado al crear fija', ?)
            """,
            (fija_id, f_ch, ahora_colombia().isoformat()),
        )

    conexion.commit()
    conexion.close()

    generadas = generar_reservas_fijas_pendientes(administrador_id=administrador_id, cancha_id=cancha_id)
    return True, f"Reserva fija creada ({generadas} turnos generados).", choques


def obtener_reservas_fijas_admin(administrador_id, cancha_id=None):
    """Lista las reservas fijas activas de las canchas del administrador."""
    conexion = obtener_conexion()
    consulta = """
        SELECT rf.*, canchas.nombre AS nombre_cancha
        FROM reservas_fijas rf
        JOIN canchas ON rf.cancha_id = canchas.id
        WHERE canchas.administrador_id = ? AND rf.activa = 1
    """
    params = [administrador_id]
    if cancha_id:
        consulta += " AND rf.cancha_id = ?"
        params.append(cancha_id)
    consulta += " ORDER BY rf.dia_semana ASC, rf.hora ASC"
    filas = conexion.execute(consulta, params).fetchall()
    conexion.close()
    return filas


def finalizar_reserva_fija(fija_id, administrador_id):
    """Finaliza una reserva fija y cancela sus turnos futuros aún no jugados."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    fila = cursor.execute(
        """
        SELECT rf.id
        FROM reservas_fijas rf
        JOIN canchas ON rf.cancha_id = canchas.id
        WHERE rf.id = ? AND canchas.administrador_id = ?
        """,
        (fija_id, administrador_id),
    ).fetchone()
    if not fila:
        conexion.close()
        return False

    ahora = ahora_colombia()
    hoy_iso = ahora.date().isoformat()
    hora_actual = ahora.strftime("%H:%M")

    cursor.execute("UPDATE reservas_fijas SET activa = 0 WHERE id = ?", (fija_id,))
    cursor.execute(
        """
        UPDATE reservas
        SET estado = 'cancelada',
            cancelada_por_rol = 'administrador',
            cancelada_por_id = ?,
            cancelada_en = ?,
            motivo_cancelacion = 'Reserva fija finalizada'
        WHERE reserva_fija_id = ?
          AND estado IN ('confirmada', 'pendiente')
          AND (fecha > ? OR (fecha = ? AND hora > ?))
        """,
        (administrador_id, ahora.isoformat(), fija_id, hoy_iso, hoy_iso, hora_actual),
    )
    conexion.commit()
    conexion.close()
    return True


# ---------------- FASE 6: REPORTES, GANANCIAS Y HORAS MUERTAS ----------------

def obtener_reporte_ganancias(administrador_id, cancha_id=None, modo="mes", periodo=None):
    """
    Calcula alquileres y ganancias por día o mes, separando cobrado (pagado + abonos)
    de pendiente por cobrar. Excluye reservas canceladas/rechazadas.
    """
    hoy = hoy_colombia()
    if modo == "dia":
        periodo_val = periodo if (periodo and len(periodo) == 10) else hoy.isoformat()
        filtro_fecha = "reservas.fecha = ?"
    else:
        modo = "mes"
        periodo_val = periodo if (periodo and len(periodo) == 7) else hoy.strftime("%Y-%m")
        filtro_fecha = "substr(reservas.fecha, 1, 7) = ?"

    conexion = obtener_conexion()
    consulta = f"""
        SELECT reservas.*, canchas.nombre AS nombre_cancha, canchas.precio AS precio_base
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        WHERE canchas.administrador_id = ? AND {filtro_fecha}
    """
    params = [administrador_id, periodo_val]
    if cancha_id:
        consulta += " AND reservas.cancha_id = ?"
        params.append(int(cancha_id))
    consulta += " ORDER BY reservas.fecha ASC, reservas.hora ASC"

    filas = conexion.execute(consulta, params).fetchall()
    conexion.close()

    total_alquileres = 0
    total_canceladas = 0
    total_ingresos = 0
    total_cobrado = 0
    total_pendiente = 0
    reservas_validas = []
    por_clave = {}

    for r in filas:
        if r["estado"] in ("cancelada", "rechazada"):
            total_canceladas += 1
            continue

        precio = int(r["precio_aplicado"] or r["precio_base"] or 0)
        ep = r["estado_pago"] or "pendiente"
        if ep == "pagado":
            cobrado = precio
        elif ep == "abonado":
            cobrado = min(int(r["monto_abonado"] or 0), precio)
        else:
            cobrado = 0
        pendiente = max(0, precio - cobrado)

        total_alquileres += 1
        total_ingresos += precio
        total_cobrado += cobrado
        total_pendiente += pendiente

        reservas_validas.append({
            "id": r["id"],
            "fecha": r["fecha"],
            "hora": r["hora"],
            "cancha": r["nombre_cancha"],
            "cliente": r["nombre_reserva"] or "Cliente",
            "estado_pago": ep,
            "precio": precio,
            "cobrado": cobrado,
            "pendiente": pendiente,
        })

        clave = r["hora"] if modo == "dia" else r["fecha"][8:10]
        if clave not in por_clave:
            por_clave[clave] = {"etiqueta": clave, "alquileres": 0, "cobrado": 0, "pendiente": 0, "total": 0}
        por_clave[clave]["alquileres"] += 1
        por_clave[clave]["cobrado"] += cobrado
        por_clave[clave]["pendiente"] += pendiente
        por_clave[clave]["total"] += precio

    serie = sorted(por_clave.values(), key=lambda x: x["etiqueta"])
    max_valor = max((item["total"] for item in serie), default=1)
    for item in serie:
        item["pct_cobrado"] = round((item["cobrado"] / max_valor) * 100) if max_valor else 0
        item["pct_pendiente"] = round((item["pendiente"] / max_valor) * 100) if max_valor else 0

    return {
        "modo": modo,
        "periodo": periodo_val,
        "total_alquileres": total_alquileres,
        "total_canceladas": total_canceladas,
        "total_ingresos": total_ingresos,
        "total_cobrado": total_cobrado,
        "total_pendiente": total_pendiente,
        "serie": serie,
        "reservas": reservas_validas,
    }


def obtener_mapa_calor_horas_muertas(administrador_id, cancha_id=None, mes_iso=None):
    """
    Calcula el porcentaje de ocupación mensual por (día de la semana, hora) para identificar horas muertas.
    """
    hoy = hoy_colombia()
    mes = mes_iso if (mes_iso and len(mes_iso) == 7) else hoy.strftime("%Y-%m")
    anio, num_mes = int(mes[:4]), int(mes[5:7])
    _, dias_en_mes = calendar.monthrange(anio, num_mes)

    # Cuántas veces cae cada día de la semana (0..6) en el mes elegido
    ocurrencias_dia = {d: 0 for d in range(7)}
    for dia_num in range(1, dias_en_mes + 1):
        ocurrencias_dia[date(anio, num_mes, dia_num).weekday()] += 1

    conexion = obtener_conexion()
    if cancha_id:
        total_canchas = 1
        filas = conexion.execute(
            """
            SELECT reservas.fecha, reservas.hora
            FROM reservas
            JOIN canchas ON reservas.cancha_id = canchas.id
            WHERE canchas.administrador_id = ?
              AND reservas.cancha_id = ?
              AND substr(reservas.fecha, 1, 7) = ?
              AND reservas.estado IN ('confirmada', 'pendiente')
            """,
            (administrador_id, int(cancha_id), mes),
        ).fetchall()
    else:
        total_canchas = max(
            1,
            conexion.execute(
                "SELECT COUNT(*) AS n FROM canchas WHERE administrador_id = ?",
                (administrador_id,),
            ).fetchone()["n"],
        )
        filas = conexion.execute(
            """
            SELECT reservas.fecha, reservas.hora
            FROM reservas
            JOIN canchas ON reservas.cancha_id = canchas.id
            WHERE canchas.administrador_id = ?
              AND substr(reservas.fecha, 1, 7) = ?
              AND reservas.estado IN ('confirmada', 'pendiente')
            """,
            (administrador_id, mes),
        ).fetchall()
    conexion.close()

    conteo = {}
    for f in filas:
        try:
            dw = date.fromisoformat(f["fecha"]).weekday()
            conteo[(dw, f["hora"])] = conteo.get((dw, f["hora"]), 0) + 1
        except ValueError:
            continue

    matriz = []
    lista_franjas = []
    nombres_dia = {idx: nombre for idx, nombre, _ in DIAS_SEMANA}

    for hora in HORAS_DISPONIBLES:
        celdas = []
        for dw, _, abrev in DIAS_SEMANA:
            capacidad = max(1, ocurrencias_dia[dw] * total_canchas)
            usados = conteo.get((dw, hora), 0)
            pct = min(100, round((usados / capacidad) * 100))
            nivel = 0 if pct == 0 else (1 if pct < 35 else (2 if pct < 70 else 3))
            celdas.append({"dia": dw, "abrev": abrev, "pct": pct, "usados": usados, "nivel": nivel})
            lista_franjas.append({
                "dia_nombre": nombres_dia[dw],
                "hora": hora,
                "pct": pct,
                "usados": usados,
                "capacidad": capacidad,
            })
        matriz.append({"hora": hora, "celdas": celdas})

    # Ordenadas de menor a mayor ocupación (horas muertas primero)
    lista_franjas.sort(key=lambda x: (x["pct"], x["hora"]))
    return {
        "mes": mes,
        "dias_cabecera": [abrev for _, _, abrev in DIAS_SEMANA],
        "matriz": matriz,
        "horas_muertas": lista_franjas[:8],
    }


# ---------------- FASE 7: RECORDATORIOS ASISTIDOS POR WHATSAPP ----------------

def construir_enlace_whatsapp_recordatorio(nombre_cliente, telefono, nombre_cancha, fecha_iso, hora_hm):
    """
    Construye el enlace wa.me prellenado para recordatorio manual en Colombia (+57).
    Separado en función propia para poder reemplazarse luego por la WhatsApp Business Cloud API.
    """
    tel_wa = telefono_whatsapp_co(telefono)
    if not tel_wa:
        return ""
    mensaje = (
        f"Hola {nombre_cliente}, te recordamos tu reserva en {nombre_cancha} "
        f"el {fecha_iso} a las {hora_hm}. ¡Te esperamos! — Ready Match"
    )
    return f"https://wa.me/{tel_wa}?text={quote(mensaje)}"


def obtener_recordatorios_admin(administrador_id):
    """Devuelve reservas confirmadas de hoy y mañana (hora Colombia) que tienen celular válido."""
    hoy = hoy_colombia()
    manana = hoy + timedelta(days=1)

    conexion = obtener_conexion()
    filas = conexion.execute(
        """
        SELECT reservas.*, canchas.nombre AS nombre_cancha,
               usuarios.nombre AS nombre_usuario, usuarios.telefono AS telefono_usuario
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        JOIN usuarios ON reservas.usuario_id = usuarios.id
        WHERE canchas.administrador_id = ?
          AND reservas.estado IN ('confirmada', 'pendiente')
          AND reservas.fecha IN (?, ?)
        ORDER BY reservas.fecha ASC, reservas.hora ASC
        """,
        (administrador_id, hoy.isoformat(), manana.isoformat()),
    ).fetchall()
    conexion.close()

    recordatorios = []
    for r in filas:
        tel = normalizar_celular_colombiano(r["telefono_reserva"] or r["telefono_usuario"] or "")
        if not tel:
            continue
        nombre = (r["nombre_reserva"] or r["nombre_usuario"] or "Jugador").strip()
        enlace = construir_enlace_whatsapp_recordatorio(nombre, tel, r["nombre_cancha"], r["fecha"], r["hora"])
        recordatorios.append({
            "id": r["id"],
            "cliente": nombre,
            "telefono": tel,
            "cancha": r["nombre_cancha"],
            "fecha": r["fecha"],
            "es_hoy": r["fecha"] == hoy.isoformat(),
            "hora": r["hora"],
            "enviado": bool(r["recordatorio_enviado_en"]),
            "enviado_en": r["recordatorio_enviado_en"] or "",
            "enlace_wa": enlace,
        })
    return recordatorios


def marcar_recordatorio_enviado(reserva_id, administrador_id):
    """Registra la fecha/hora de envío del recordatorio evitando dobles registros."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    fila = cursor.execute(
        """
        SELECT reservas.id, reservas.recordatorio_enviado_en
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        WHERE reservas.id = ? AND canchas.administrador_id = ?
        """,
        (reserva_id, administrador_id),
    ).fetchone()
    if not fila:
        conexion.close()
        return False, "Reserva no encontrada."
    if fila["recordatorio_enviado_en"]:
        conexion.close()
        return False, "Ese recordatorio ya fue marcado como enviado."

    cursor.execute(
        "UPDATE reservas SET recordatorio_enviado_en = ? WHERE id = ?",
        (ahora_colombia().isoformat(), reserva_id),
    )
    conexion.commit()
    conexion.close()
    return True, "Recordatorio marcado como enviado."
