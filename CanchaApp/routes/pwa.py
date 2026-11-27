"""Rutas PWA (Service Worker, manifest) y API de notificaciones."""

from datetime import datetime, timedelta
import os

from flask import Blueprint, jsonify, make_response, request, send_from_directory, session

from config import BASE_DIR, ahora_colombia, hoy_colombia
from db.partidos import (
    actualizar_ultimo_recordatorio,
    crear_notificacion,
    marcar_notificaciones_enviadas,
    obtener_notificaciones_pendientes,
    obtener_notificaciones_recientes,
    obtener_resumen_novedades,
)
from db.usuarios import buscar_usuario_por_id

pwa_bp = Blueprint("pwa", __name__)


def _construir_mensaje_recordatorio():
    resumen = obtener_resumen_novedades(hoy_colombia().isoformat())
    ultima_cancha = resumen["ultima_cancha"]
    total_turnos = resumen["total_turnos"]
    partido = resumen["partido_abierto"]

    if partido:
        return (
            "Equipos buscando rival",
            f"{partido['nombre_equipo']} busca partido el {partido['fecha']} a las {partido['hora']}.",
            "/rivales",
        )
    if ultima_cancha and total_turnos > 0:
        return (
            "Turnos disponibles en Ready Match",
            f"{ultima_cancha['nombre']} y {total_turnos} horarios activos te esperan.",
            "/canchas",
        )
    return (
        "Vuelve a jugar con Ready Match",
        "Explora canchas de fútbol, baloncesto y voleibol y arma tu partido.",
        "/canchas",
    )


def _generar_recordatorio_si_corresponde(usuario):
    ahora = ahora_colombia()
    ultimo_texto = usuario["ultimo_recordatorio"] or ""
    enviar_nuevo = not ultimo_texto
    if ultimo_texto:
        try:
            ultimo_dt = datetime.fromisoformat(ultimo_texto)
            ahora_cmp = ahora if ultimo_dt.tzinfo else ahora.replace(tzinfo=None)
            if (ahora_cmp - ultimo_dt) >= timedelta(hours=36):
                enviar_nuevo = True
        except ValueError:
            enviar_nuevo = True

    if enviar_nuevo:
        titulo, mensaje, url_destino = _construir_mensaje_recordatorio()
        crear_notificacion(usuario["id"], titulo, mensaje, url_destino, "recordatorio", ahora.isoformat())
        actualizar_ultimo_recordatorio(usuario["id"], ahora.isoformat())


@pwa_bp.route("/sw.js")
def service_worker():
    carpeta_static = os.path.join(BASE_DIR, "static")
    respuesta = make_response(send_from_directory(carpeta_static, "sw.js"))
    respuesta.headers["Content-Type"] = "application/javascript"
    respuesta.headers["Service-Worker-Allowed"] = "/"
    respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


@pwa_bp.route("/manifest.json")
def manifest_pwa():
    carpeta_static = os.path.join(BASE_DIR, "static")
    respuesta = make_response(send_from_directory(carpeta_static, "manifest.json"))
    respuesta.headers["Content-Type"] = "application/manifest+json"
    return respuesta


@pwa_bp.route("/api/notificaciones/pendientes")
def api_notificaciones_pendientes():
    if "usuario_id" not in session:
        return jsonify({"notificaciones": []})

    usuario = buscar_usuario_por_id(session["usuario_id"])
    if not usuario:
        return jsonify({"notificaciones": []})

    _generar_recordatorio_si_corresponde(usuario)
    filas = obtener_notificaciones_pendientes(usuario["id"])
    return jsonify({
        "notificaciones": [
            {
                "id": fila["id"],
                "titulo": fila["titulo"],
                "mensaje": fila["mensaje"],
                "url": fila["url"],
                "tipo": fila["tipo"],
            }
            for fila in filas
        ]
    })


@pwa_bp.route("/api/notificaciones/recientes")
def api_notificaciones_recientes():
    """Devuelve las últimas notificaciones para mostrarlas en el panel del icono de campana."""
    if "usuario_id" not in session:
        return jsonify({"notificaciones": []})

    filas = obtener_notificaciones_recientes(session["usuario_id"], limite=8)
    return jsonify({
        "notificaciones": [
            {
                "id": fila["id"],
                "titulo": fila["titulo"],
                "mensaje": fila["mensaje"],
                "url": fila["url"],
            }
            for fila in filas
        ]
    })


@pwa_bp.route("/api/notificaciones/marcar_enviadas", methods=["POST"])
def api_marcar_notificaciones_enviadas():
    if "usuario_id" not in session:
        return jsonify({"ok": False}), 401

    datos = request.get_json(silent=True) or {}
    ids_validos = [int(x) for x in datos.get("ids", []) if str(x).isdigit()]
    marcar_notificaciones_enviadas(session["usuario_id"], ids_validos)
    return jsonify({"ok": True})


@pwa_bp.route("/api/notificaciones/prueba", methods=["POST"])
def api_notificacion_prueba():
    if "usuario_id" not in session:
        return jsonify({"ok": False}), 401

    titulo, mensaje, url_destino = _construir_mensaje_recordatorio()
    crear_notificacion(
        session["usuario_id"],
        titulo,
        mensaje,
        url_destino,
        "prueba",
        ahora_colombia().isoformat(),
    )
    return jsonify({"ok": True})
