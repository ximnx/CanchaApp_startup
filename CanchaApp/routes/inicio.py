"""Blueprint de la pantalla de Inicio (limpia: saludo, deportes, destacadas y ver todas)."""

from flask import Blueprint, render_template, session

from config import DEPORTES_CATALOGO, hoy_colombia
from db.canchas import enriquecer_cancha, obtener_todas_las_canchas
from db.usuarios import obtener_ids_favoritos

inicio_bp = Blueprint("inicio", __name__)


@inicio_bp.route("/")
def inicio():
    fecha_hoy = hoy_colombia().isoformat()
    favoritos_ids = obtener_ids_favoritos(session.get("usuario_id"))
    canchas_bd = obtener_todas_las_canchas()[:5]
    canchas_destacadas = [enriquecer_cancha(c, fecha_hoy, favoritos_ids) for c in canchas_bd]

    return render_template(
        "index.html",
        deportes=DEPORTES_CATALOGO,
        canchas=canchas_destacadas,
    )
