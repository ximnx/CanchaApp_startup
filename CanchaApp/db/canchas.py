"""Operaciones de base de datos para canchas, tarifas por horario, agenda unificada y reservas."""

from datetime import date, timedelta
import sqlite3

from config import (
    ESTADOS_PAGO,
    HORAS_DISPONIBLES,
    HORAS_MIN_CANCELACION,
    ahora_colombia,
    fecha_hora_colombia,
    hoy_colombia,
)
from db.connection import obtener_conexion


# ---------------- DEPORTES POR ESTABLECIMIENTO ----------------

def guardar_deportes_cancha(cancha_id, deporte_principal, deportes_extra=None):
    """Registra los deportes disponibles en un establecimiento (principal + adicionales)."""
    lista = [deporte_principal]
    if deportes_extra:
        for dep in deportes_extra:
            if dep and dep not in lista:
                lista.append(dep)

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM cancha_deportes WHERE cancha_id = ?", (cancha_id,))
    for dep in lista:
        cursor.execute(
            "INSERT INTO cancha_deportes (cancha_id, deporte) VALUES (?, ?)",
            (cancha_id, dep),
        )
    conexion.commit()
    conexion.close()


def obtener_deportes_de_cancha(cancha_id, deporte_principal="Fútbol"):
    """Devuelve la lista ordenada de deportes ofrecidos por una cancha."""
    conexion = obtener_conexion()
    filas = conexion.execute(
        "SELECT deporte FROM cancha_deportes WHERE cancha_id = ? ORDER BY id ASC",
        (cancha_id,),
    ).fetchall()
    conexion.close()

    deportes = [f["deporte"] for f in filas]
    if deporte_principal and deporte_principal not in deportes:
        deportes.insert(0, deporte_principal)
    return deportes


# ---------------- TARIFAS POR HORARIO (FASE 3) ----------------

def obtener_tarifas_cancha(cancha_id):
    """Devuelve las tarifas configuradas por día y franja horaria de una cancha."""
    conexion = obtener_conexion()
    filas = conexion.execute(
        "SELECT * FROM tarifas_cancha WHERE cancha_id = ? ORDER BY hora_inicio ASC, id ASC",
        (cancha_id,),
    ).fetchall()
    conexion.close()
    return filas


def crear_tarifa_cancha(cancha_id, administrador_id, dias_lista, hora_inicio, hora_fin, precio):
    """Crea una tarifa validando propiedad, precio positivo y que no se solape con otra."""
    if precio <= 0:
        return False, "El precio debe ser mayor a cero."
    if hora_inicio > hora_fin or hora_inicio not in HORAS_DISPONIBLES or hora_fin not in HORAS_DISPONIBLES:
        return False, "El rango de horas no es válido."

    dias_unicos = sorted({int(d) for d in dias_lista if str(d).isdigit() and 0 <= int(d) <= 6})
    if not dias_unicos:
        return False, "Selecciona al menos un día de la semana."

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cancha = cursor.execute(
        "SELECT id FROM canchas WHERE id = ? AND administrador_id = ?",
        (cancha_id, administrador_id),
    ).fetchone()
    if not cancha:
        conexion.close()
        return False, "No puedes modificar tarifas de una cancha que no te pertenece."

    # Validamos que no haya solapamiento de día + franja horaria con tarifas existentes
    existentes = cursor.execute(
        "SELECT dias_semana, hora_inicio, hora_fin FROM tarifas_cancha WHERE cancha_id = ?",
        (cancha_id,),
    ).fetchall()
    dias_set = set(dias_unicos)
    for tar in existentes:
        tar_dias = {int(x) for x in tar["dias_semana"].split(",") if x.isdigit()}
        if dias_set & tar_dias:
            # Dos rangos cerrados [a, b] y [c, d] se solapan si a <= d y c <= b
            if hora_inicio <= tar["hora_fin"] and tar["hora_inicio"] <= hora_fin:
                conexion.close()
                return False, "Ese rango horario se cruza con otra tarifa en los mismos días."

    cursor.execute(
        """
        INSERT INTO tarifas_cancha (cancha_id, dias_semana, hora_inicio, hora_fin, precio)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cancha_id, ",".join(str(d) for d in dias_unicos), hora_inicio, hora_fin, int(precio)),
    )
    conexion.commit()
    conexion.close()
    return True, "Tarifa guardada correctamente."


def eliminar_tarifa_cancha(tarifa_id, administrador_id):
    """Elimina una tarifa solo si pertenece a una cancha del administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    fila = cursor.execute(
        """
        SELECT tarifas_cancha.id
        FROM tarifas_cancha
        JOIN canchas ON tarifas_cancha.cancha_id = canchas.id
        WHERE tarifas_cancha.id = ? AND canchas.administrador_id = ?
        """,
        (tarifa_id, administrador_id),
    ).fetchone()
    if not fila:
        conexion.close()
        return False
    cursor.execute("DELETE FROM tarifas_cancha WHERE id = ?", (tarifa_id,))
    conexion.commit()
    conexion.close()
    return True


def calcular_precio_turno(cancha_id, fecha_iso, hora_hm, precio_base=None, conexion_externa=None):
    """Calcula el precio aplicable según tarifas por día/hora o usa el precio base de la cancha."""
    cerrar = conexion_externa is None
    conexion = conexion_externa or obtener_conexion()

    if precio_base is None:
        fila = conexion.execute("SELECT precio FROM canchas WHERE id = ?", (cancha_id,)).fetchone()
        precio_base = int(fila["precio"]) if fila else 0

    try:
        dia_semana = date.fromisoformat(fecha_iso).weekday()
    except ValueError:
        if cerrar:
            conexion.close()
        return int(precio_base)

    tarifas = conexion.execute(
        "SELECT dias_semana, hora_inicio, hora_fin, precio FROM tarifas_cancha WHERE cancha_id = ?",
        (cancha_id,),
    ).fetchall()
    if cerrar:
        conexion.close()

    for tar in tarifas:
        dias = {int(x) for x in tar["dias_semana"].split(",") if x.isdigit()}
        if dia_semana in dias and tar["hora_inicio"] <= hora_hm <= tar["hora_fin"]:
            return int(tar["precio"])

    return int(precio_base)


def obtener_precio_minimo_cancha(cancha_id, precio_base):
    """Devuelve el precio más bajo disponible (base o tarifa especial) para mostrar 'Desde $X'."""
    conexion = obtener_conexion()
    fila = conexion.execute(
        "SELECT MIN(precio) AS minimo, COUNT(*) AS total FROM tarifas_cancha WHERE cancha_id = ?",
        (cancha_id,),
    ).fetchone()
    conexion.close()

    if fila and fila["total"] > 0 and fila["minimo"] is not None:
        return min(int(precio_base), int(fila["minimo"])), True
    return int(precio_base), False


# ---------------- CRUD DE CANCHAS ----------------

def crear_cancha(
    nombre,
    direccion,
    precio,
    tipo_futbol,
    imagen,
    administrador_id,
    deporte="Fútbol",
    deportes_extra=None,
    tipo_cancha="Sintética",
    descripcion="",
    caracteristicas="",
    telefono="",
):
    """Registra un nuevo establecimiento deportivo asociado a su administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        INSERT INTO canchas (
            nombre, direccion, precio, tipo_futbol, imagen, administrador_id,
            deporte, tipo_cancha, descripcion, caracteristicas, telefono
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            nombre,
            direccion,
            precio,
            tipo_futbol,
            imagen,
            administrador_id,
            deporte,
            tipo_cancha,
            descripcion,
            caracteristicas,
            telefono,
        ),
    )
    cancha_id = cursor.lastrowid
    conexion.commit()
    conexion.close()
    guardar_deportes_cancha(cancha_id, deporte, deportes_extra)
    return cancha_id


def obtener_todas_las_canchas(
    tipo_futbol=None,
    busqueda=None,
    deporte=None,
    fecha=None,
    hora=None,
    precio_min=None,
    precio_max=None,
    tipo_cancha=None,
    ubicacion=None,
    solo_favoritas_usuario_id=None,
):
    """Consulta canchas con filtros combinables reales sobre la agenda unificada."""
    conexion = obtener_conexion()
    consulta = """
        SELECT canchas.*, usuarios.nombre AS nombre_administrador
        FROM canchas
        JOIN usuarios ON canchas.administrador_id = usuarios.id
        WHERE 1 = 1
    """
    parametros = []

    if solo_favoritas_usuario_id:
        consulta += " AND canchas.id IN (SELECT cancha_id FROM favoritos WHERE usuario_id = ?)"
        parametros.append(solo_favoritas_usuario_id)

    if deporte:
        consulta += """
            AND (
                canchas.deporte = ?
                OR canchas.id IN (SELECT cancha_id FROM cancha_deportes WHERE deporte = ?)
            )
        """
        parametros.extend([deporte, deporte])

    if tipo_futbol:
        consulta += " AND canchas.tipo_futbol = ?"
        parametros.append(tipo_futbol)

    if tipo_cancha:
        consulta += " AND canchas.tipo_cancha = ?"
        parametros.append(tipo_cancha)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        consulta += " AND (LOWER(canchas.nombre) LIKE ? OR LOWER(canchas.direccion) LIKE ? OR LOWER(canchas.descripcion) LIKE ?)"
        parametros.extend([patron, patron, patron])

    if ubicacion:
        patron_ub = f"%{ubicacion.lower()}%"
        consulta += " AND LOWER(canchas.direccion) LIKE ?"
        parametros.append(patron_ub)

    if precio_min is not None:
        consulta += """
            AND (
                canchas.precio >= ?
                OR EXISTS (SELECT 1 FROM tarifas_cancha tc WHERE tc.cancha_id = canchas.id AND tc.precio >= ?)
            )
        """
        parametros.extend([int(precio_min), int(precio_min)])

    if precio_max is not None:
        consulta += """
            AND (
                canchas.precio <= ?
                OR EXISTS (SELECT 1 FROM tarifas_cancha tc WHERE tc.cancha_id = canchas.id AND tc.precio <= ?)
            )
        """
        parametros.extend([int(precio_max), int(precio_max)])

    # Filtro unificado de disponibilidad: el turno no debe estar bloqueado ni reservado
    if fecha and hora:
        consulta += """
            AND NOT EXISTS (
                SELECT 1 FROM horarios h
                WHERE h.cancha_id = canchas.id AND h.fecha = ? AND h.hora = ? AND h.bloqueado = 1
            )
            AND NOT EXISTS (
                SELECT 1 FROM reservas r
                WHERE r.cancha_id = canchas.id AND r.fecha = ? AND r.hora = ? AND r.estado IN ('confirmada', 'pendiente')
            )
        """
        parametros.extend([fecha, hora, fecha, hora])
    elif fecha:
        consulta += """
            AND (
                SELECT COUNT(*) FROM reservas r
                WHERE r.cancha_id = canchas.id AND r.fecha = ? AND r.estado IN ('confirmada', 'pendiente')
            ) + (
                SELECT COUNT(*) FROM horarios h
                WHERE h.cancha_id = canchas.id AND h.fecha = ? AND h.bloqueado = 1
            ) < ?
        """
        parametros.extend([fecha, fecha, len(HORAS_DISPONIBLES)])

    consulta += " ORDER BY canchas.id DESC"
    canchas = conexion.execute(consulta, parametros).fetchall()
    conexion.close()
    return canchas


def contar_horarios_disponibles_hoy(cancha_id):
    """Cuenta cuántos turnos libres quedan hoy (hora Colombia) en la agenda unificada."""
    hoy_iso = hoy_colombia().isoformat()
    franjas = obtener_agenda_dia(cancha_id, hoy_iso)
    return sum(1 for f in franjas if f["disponible_jugador"])


def enriquecer_cancha(cancha, fecha_hoy, favoritos_ids, deporte_contexto=None):
    """Prepara los datos listos para presentar una cancha (precio desde, disponibilidad real)."""
    deporte_principal = cancha["deporte"] if cancha["deporte"] else "Fútbol"
    deportes_ofrecidos = obtener_deportes_de_cancha(cancha["id"], deporte_principal)

    if deporte_contexto and deporte_contexto in deportes_ofrecidos and deporte_contexto != deporte_principal:
        deporte_visible = deporte_contexto
        modalidad_visible = "Multideporte"
    else:
        deporte_visible = deporte_principal
        modalidad_visible = cancha["tipo_futbol"]

    precio_desde, tiene_tarifas = obtener_precio_minimo_cancha(cancha["id"], cancha["precio"])
    disponibles_hoy = contar_horarios_disponibles_hoy(cancha["id"])
    # Si ya pasó el último turno de hoy, mostramos los turnos libres de mañana
    etiqueta_disp = f"{disponibles_hoy} hoy"
    if disponibles_hoy == 0:
        manana_iso = (hoy_colombia() + timedelta(days=1)).isoformat()
        disp_manana = sum(1 for f in obtener_agenda_dia(cancha["id"], manana_iso) if f["disponible_jugador"])
        disponibles_hoy = disp_manana
        etiqueta_disp = f"{disp_manana} mañana" if disp_manana > 0 else "Sin turnos"

    return {
        "id": cancha["id"],
        "nombre": cancha["nombre"],
        "direccion": cancha["direccion"],
        "precio": cancha["precio"],
        "precio_desde": precio_desde,
        "tiene_tarifas": tiene_tarifas,
        "tipo_futbol": modalidad_visible,
        "deporte": deporte_visible,
        "deportes_ofrecidos": deportes_ofrecidos,
        "tipo_cancha": cancha["tipo_cancha"] if cancha["tipo_cancha"] else "Sintética",
        "descripcion": cancha["descripcion"] or "",
        "caracteristicas": cancha["caracteristicas"] or "",
        "telefono": cancha["telefono"] or "",
        "imagen": cancha["imagen"],
        "disponibles": disponibles_hoy,
        "etiqueta_disponibles": etiqueta_disp,
        "es_favorita": cancha["id"] in favoritos_ids,
    }


def obtener_canchas_por_administrador(administrador_id):
    """Devuelve únicamente los establecimientos del administrador autenticado."""
    conexion = obtener_conexion()
    canchas = conexion.execute(
        "SELECT * FROM canchas WHERE administrador_id = ? ORDER BY id DESC",
        (administrador_id,),
    ).fetchall()
    conexion.close()
    return canchas


def obtener_cancha_por_id(cancha_id):
    """Busca un establecimiento por su ID junto con el nombre de su administrador."""
    conexion = obtener_conexion()
    cancha = conexion.execute(
        """
        SELECT canchas.*, usuarios.nombre AS nombre_administrador
        FROM canchas
        JOIN usuarios ON canchas.administrador_id = usuarios.id
        WHERE canchas.id = ?
        """,
        (cancha_id,),
    ).fetchone()
    conexion.close()
    return cancha


def actualizar_cancha(
    cancha_id,
    administrador_id,
    nombre,
    direccion,
    precio,
    tipo_futbol,
    imagen,
    deporte="Fútbol",
    deportes_extra=None,
    tipo_cancha="Sintética",
    descripcion="",
    caracteristicas="",
    telefono="",
):
    """Actualiza un escenario solo si pertenece al administrador indicado."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        """
        UPDATE canchas
        SET nombre = ?, direccion = ?, precio = ?, tipo_futbol = ?, imagen = ?,
            deporte = ?, tipo_cancha = ?, descripcion = ?, caracteristicas = ?, telefono = ?
        WHERE id = ? AND administrador_id = ?
        """,
        (
            nombre,
            direccion,
            precio,
            tipo_futbol,
            imagen,
            deporte,
            tipo_cancha,
            descripcion,
            caracteristicas,
            telefono,
            cancha_id,
            administrador_id,
        ),
    )
    actualizadas = cursor.rowcount
    conexion.commit()
    conexion.close()
    if actualizadas > 0:
        guardar_deportes_cancha(cancha_id, deporte, deportes_extra)
        return True
    return False


def eliminar_cancha(cancha_id, administrador_id):
    """Elimina un establecimiento y todas sus dependencias si pertenece al administrador."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    if not cursor.execute(
        "SELECT id FROM canchas WHERE id = ? AND administrador_id = ?",
        (cancha_id, administrador_id),
    ).fetchone():
        conexion.close()
        return False

    fijas_ids = [
        f["id"]
        for f in cursor.execute("SELECT id FROM reservas_fijas WHERE cancha_id = ?", (cancha_id,)).fetchall()
    ]
    if fijas_ids:
        ph = ",".join("?" for _ in fijas_ids)
        cursor.execute(f"DELETE FROM reservas_fijas_excepciones WHERE reserva_fija_id IN ({ph})", fijas_ids)
    cursor.execute("DELETE FROM reservas_fijas WHERE cancha_id = ?", (cancha_id,))
    cursor.execute("DELETE FROM tarifas_cancha WHERE cancha_id = ?", (cancha_id,))
    cursor.execute("DELETE FROM favoritos WHERE cancha_id = ?", (cancha_id,))
    cursor.execute("DELETE FROM reservas WHERE cancha_id = ?", (cancha_id,))
    cursor.execute("DELETE FROM horarios WHERE cancha_id = ?", (cancha_id,))
    cursor.execute("DELETE FROM cancha_deportes WHERE cancha_id = ?", (cancha_id,))
    cursor.execute(
        "DELETE FROM canchas WHERE id = ? AND administrador_id = ?",
        (cancha_id, administrador_id),
    )
    conexion.commit()
    conexion.close()
    return True


# ---------------- AGENDA UNIFICADA Y BLOQUEOS (FASE 1) ----------------

def obtener_agenda_dia(cancha_id, fecha_iso):
    """
    Fuente única de verdad de disponibilidad por día y hora para una cancha.
    Combina horarios (bloqueos), reservas activas (confirmada/pendiente) y canceladas.
    """
    conexion = obtener_conexion()
    cancha = conexion.execute("SELECT precio FROM canchas WHERE id = ?", (cancha_id,)).fetchone()
    if not cancha:
        conexion.close()
        return []
    precio_base = int(cancha["precio"])

    bloqueos = {
        h["hora"]: h["id"]
        for h in conexion.execute(
            "SELECT id, hora FROM horarios WHERE cancha_id = ? AND fecha = ? AND bloqueado = 1",
            (cancha_id, fecha_iso),
        ).fetchall()
    }

    reservas_dia = conexion.execute(
        """
        SELECT reservas.*, usuarios.nombre AS nombre_usuario, usuarios.telefono AS telefono_usuario
        FROM reservas
        JOIN usuarios ON reservas.usuario_id = usuarios.id
        WHERE reservas.cancha_id = ? AND reservas.fecha = ?
        ORDER BY reservas.id DESC
        """,
        (cancha_id, fecha_iso),
    ).fetchall()

    activas = {}
    canceladas = {}
    for r in reservas_dia:
        hora = r["hora"]
        if r["estado"] in ("confirmada", "pendiente") and hora not in activas:
            activas[hora] = r
        elif r["estado"] == "cancelada" and hora not in canceladas:
            canceladas[hora] = r

    ahora = ahora_colombia()
    franjas = []
    for hora in HORAS_DISPONIBLES:
        precio_turno = calcular_precio_turno(cancha_id, fecha_iso, hora, precio_base, conexion)
        dt_turno = fecha_hora_colombia(fecha_iso, hora)
        pasado = dt_turno <= ahora

        reserva_activa = activas.get(hora)
        bloqueo_id = bloqueos.get(hora)
        reserva_cancelada = canceladas.get(hora)

        if reserva_activa:
            estado = "reservado"
        elif bloqueo_id:
            estado = "bloqueado"
        elif reserva_cancelada:
            estado = "cancelado"
        else:
            estado = "libre"

        # Para jugadores: libre o cancelado (ya liberado) y en el futuro
        disponible_jugador = (estado in ("libre", "cancelado")) and not pasado

        franjas.append({
            "fecha": fecha_iso,
            "hora": hora,
            "estado": estado,
            "precio": precio_turno,
            "pasado": pasado,
            "disponible_jugador": disponible_jugador,
            "bloqueo_id": bloqueo_id,
            "reserva": reserva_activa,
            "cancelada": reserva_cancelada,
        })

    conexion.close()
    return franjas


def alternar_bloqueo_turno(cancha_id, fecha_iso, hora_hm, administrador_id):
    """Bloquea o desbloquea un turno directamente desde la agenda de la cancha."""
    if hora_hm not in HORAS_DISPONIBLES:
        return False, "Hora no válida."

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cancha = cursor.execute(
        "SELECT id FROM canchas WHERE id = ? AND administrador_id = ?",
        (cancha_id, administrador_id),
    ).fetchone()
    if not cancha:
        conexion.close()
        return False, "No puedes modificar esta cancha."

    existente = cursor.execute(
        "SELECT id, bloqueado FROM horarios WHERE cancha_id = ? AND fecha = ? AND hora = ?",
        (cancha_id, fecha_iso, hora_hm),
    ).fetchone()

    if existente and existente["bloqueado"]:
        cursor.execute("UPDATE horarios SET bloqueado = 0 WHERE id = ?", (existente["id"],))
        conexion.commit()
        conexion.close()
        return True, f"Horario {hora_hm} desbloqueado."

    # No permitir bloquear un turno que ya tiene reserva activa
    activa = cursor.execute(
        """
        SELECT id FROM reservas
        WHERE cancha_id = ? AND fecha = ? AND hora = ? AND estado IN ('confirmada', 'pendiente')
        """,
        (cancha_id, fecha_iso, hora_hm),
    ).fetchone()
    if activa:
        conexion.close()
        return False, "Ese turno ya tiene una reserva activa. Cancélala primero si necesitas bloquearlo."

    if existente:
        cursor.execute("UPDATE horarios SET bloqueado = 1 WHERE id = ?", (existente["id"],))
    else:
        cursor.execute(
            "INSERT INTO horarios (cancha_id, fecha, hora, bloqueado) VALUES (?, ?, ?, 1)",
            (cancha_id, fecha_iso, hora_hm),
        )
    conexion.commit()
    conexion.close()
    return True, f"Horario {hora_hm} bloqueado."


# ---------------- RESERVAS ATÓMICAS, PAGOS Y CANCELACIONES (FASES 1 Y 2) ----------------

def crear_reserva_atomica(
    usuario_id,
    cancha_id,
    fecha_iso,
    hora_hm,
    nombre_reserva="",
    identificacion="",
    deporte_reserva="",
    modalidad_reserva="",
    origen="web",
    telefono_reserva="",
    reserva_fija_id=None,
    estado_pago="pendiente",
    monto_abonado=0,
):
    """
    Crea una reserva confirmada de inmediato dentro de una transacción BEGIN IMMEDIATE.
    Impide cruces de horario incluso ante peticiones simultáneas gracias al índice único parcial.
    Devuelve (ok: bool, mensaje_o_error: str, reserva_id: int | None, precio_aplicado: int).
    """
    if hora_hm not in HORAS_DISPONIBLES:
        return False, "La hora seleccionada no es válida.", None, 0

    if estado_pago not in ESTADOS_PAGO:
        estado_pago = "pendiente"

    conexion = obtener_conexion()
    try:
        conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.cursor()

        cancha = cursor.execute(
            "SELECT id, nombre, precio, deporte, tipo_futbol, administrador_id FROM canchas WHERE id = ?",
            (cancha_id,),
        ).fetchone()
        if not cancha:
            conexion.rollback()
            return False, "La cancha seleccionada no existe.", None, 0

        # Verificar si el horario está bloqueado
        bloqueado = cursor.execute(
            "SELECT id FROM horarios WHERE cancha_id = ? AND fecha = ? AND hora = ? AND bloqueado = 1",
            (cancha_id, fecha_iso, hora_hm),
        ).fetchone()
        if bloqueado:
            conexion.rollback()
            return False, "Ese horario está bloqueado por la cancha.", None, 0

        # Verificar reserva activa previa
        ocupada = cursor.execute(
            """
            SELECT id FROM reservas
            WHERE cancha_id = ? AND fecha = ? AND hora = ? AND estado IN ('confirmada', 'pendiente')
            """,
            (cancha_id, fecha_iso, hora_hm),
        ).fetchone()
        if ocupada:
            conexion.rollback()
            return False, "Ese turno ya fue reservado. Elige otra hora.", None, 0

        precio_aplicado = calcular_precio_turno(cancha_id, fecha_iso, hora_hm, cancha["precio"], conexion)
        deporte_final = deporte_reserva or cancha["deporte"] or "Fútbol"
        modalidad_final = modalidad_reserva or cancha["tipo_futbol"]

        monto_final = 0
        if estado_pago == "pagado":
            monto_final = precio_aplicado
        elif estado_pago == "abonado":
            monto_final = max(0, min(int(monto_abonado or 0), precio_aplicado))

        cursor.execute(
            """
            INSERT INTO reservas (
                usuario_id, cancha_id, fecha, hora, estado,
                nombre_reserva, identificacion, deporte_reserva, modalidad_reserva,
                origen, estado_pago, monto_abonado, precio_aplicado,
                telefono_reserva, reserva_fija_id
            )
            VALUES (?, ?, ?, ?, 'confirmada', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario_id,
                cancha_id,
                fecha_iso,
                hora_hm,
                nombre_reserva,
                identificacion,
                deporte_final,
                modalidad_final,
                origen,
                estado_pago,
                monto_final,
                precio_aplicado,
                telefono_reserva,
                reserva_fija_id,
            ),
        )
        reserva_id = cursor.lastrowid
        conexion.commit()
        return True, "Reserva confirmada.", reserva_id, precio_aplicado
    except sqlite3.IntegrityError:
        conexion.rollback()
        return False, "Ese turno acaba de ser reservado por otra persona.", None, 0
    finally:
        conexion.close()


def actualizar_estado_pago(reserva_id, administrador_id, nuevo_estado, monto_abonado=None):
    """Permite al administrador cambiar el estado de pago (pendiente, abonado, pagado)."""
    if nuevo_estado not in ESTADOS_PAGO:
        return False, "Estado de pago no válido."

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    reserva = cursor.execute(
        """
        SELECT reservas.id, reservas.precio_aplicado, reservas.monto_abonado, canchas.precio AS precio_base
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        WHERE reservas.id = ? AND canchas.administrador_id = ?
        """,
        (reserva_id, administrador_id),
    ).fetchone()
    if not reserva:
        conexion.close()
        return False, "No puedes modificar una reserva que no pertenece a tus canchas."

    precio = int(reserva["precio_aplicado"] or reserva["precio_base"] or 0)
    if nuevo_estado == "pendiente":
        monto = 0
    elif nuevo_estado == "pagado":
        monto = precio
    else:
        # Abonado: usamos el monto enviado si es válido; si no, conservamos previo o 50 %
        if monto_abonado is not None and str(monto_abonado).strip().isdigit() and int(monto_abonado) > 0:
            monto = min(int(monto_abonado), precio)
        elif int(reserva["monto_abonado"] or 0) > 0 and int(reserva["monto_abonado"]) < precio:
            monto = int(reserva["monto_abonado"])
        else:
            monto = precio // 2

    cursor.execute(
        "UPDATE reservas SET estado_pago = ?, monto_abonado = ? WHERE id = ?",
        (nuevo_estado, monto, reserva_id),
    )
    conexion.commit()
    conexion.close()
    return True, "Estado de pago actualizado."


def puede_cancelar_jugador(fecha_iso, hora_hm):
    """
    Valida en zona America/Bogota si un jugador puede cancelar su reserva:
    - No puede cancelar una reserva que ya pasó.
    - Debe faltar al menos HORAS_MIN_CANCELACION (3 horas) para el inicio.
    """
    ahora = ahora_colombia()
    inicio_turno = fecha_hora_colombia(fecha_iso, hora_hm)
    if inicio_turno <= ahora:
        return False, "Esta reserva ya pasó y no se puede cancelar."

    limite = inicio_turno - timedelta(hours=HORAS_MIN_CANCELACION)
    if ahora > limite:
        return False, "Ya no puedes cancelar. Comunícate con la cancha."

    return True, ""


def cancelar_reserva(reserva_id, actor_rol, actor_id, motivo=""):
    """
    Cancela una reserva validando rol, propiedad y regla de 3 horas para jugadores.
    Registra quién canceló, cuándo y motivo, y agrega excepción si pertenece a una reserva fija.
    """
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    reserva = cursor.execute(
        """
        SELECT reservas.*, canchas.nombre AS nombre_cancha,
               canchas.administrador_id AS administrador_id,
               canchas.direccion AS direccion_cancha,
               canchas.telefono AS telefono_cancha
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        WHERE reservas.id = ?
        """,
        (reserva_id,),
    ).fetchone()

    if not reserva:
        conexion.close()
        return False, "La reserva no existe.", None

    if reserva["estado"] not in ("confirmada", "pendiente"):
        conexion.close()
        return False, "Esta reserva ya no está activa.", None

    if actor_rol == "jugador":
        if reserva["usuario_id"] != actor_id or reserva["origen"] == "admin":
            conexion.close()
            return False, "No puedes cancelar esta reserva.", None
        permitido, msg_error = puede_cancelar_jugador(reserva["fecha"], reserva["hora"])
        if not permitido:
            conexion.close()
            return False, msg_error, reserva
    elif actor_rol == "administrador":
        if reserva["administrador_id"] != actor_id:
            conexion.close()
            return False, "No puedes cancelar reservas de una cancha que no te pertenece.", None
    else:
        conexion.close()
        return False, "Acción no autorizada.", None

    ahora_iso = ahora_colombia().isoformat()
    motivo_limpio = (motivo or "").strip()[:200]

    cursor.execute(
        """
        UPDATE reservas
        SET estado = 'cancelada',
            cancelada_por_rol = ?,
            cancelada_por_id = ?,
            cancelada_en = ?,
            motivo_cancelacion = ?
        WHERE id = ?
        """,
        (actor_rol, actor_id, ahora_iso, motivo_limpio, reserva_id),
    )

    # Si pertenece a una reserva fija, registramos la excepción para que no se regenere esa fecha
    if reserva["reserva_fija_id"]:
        cursor.execute(
            """
            INSERT OR IGNORE INTO reservas_fijas_excepciones (reserva_fija_id, fecha, motivo, creada_en)
            VALUES (?, ?, ?, ?)
            """,
            (reserva["reserva_fija_id"], reserva["fecha"], motivo_limpio, ahora_iso),
        )

    conexion.commit()
    conexion.close()
    return True, "Reserva cancelada correctamente.", reserva


def obtener_reservas_por_usuario(usuario_id):
    """Devuelve las reservas propias de un jugador (excluye agendadas manualmente por admin)."""
    conexion = obtener_conexion()
    reservas = conexion.execute(
        """
        SELECT reservas.*, canchas.nombre AS nombre_cancha,
               canchas.direccion AS direccion_cancha,
               canchas.telefono AS telefono_cancha,
               canchas.precio AS precio_cancha,
               canchas.tipo_futbol AS tipo_futbol,
               canchas.deporte AS deporte_cancha
        FROM reservas
        JOIN canchas ON reservas.cancha_id = canchas.id
        WHERE reservas.usuario_id = ? AND reservas.origen != 'admin'
        ORDER BY reservas.fecha DESC, reservas.hora DESC, reservas.id DESC
        """,
        (usuario_id,),
    ).fetchall()
    conexion.close()
    return reservas

