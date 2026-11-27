/* Ready Match — PWA, notificaciones, paneles inferiores y microinteracciones vanilla */

(function () {
    var registroSW = null;
    var eventoInstalacion = null;
    var usuarioLogueado = document.body && document.body.dataset.usuarioLogueado === "1";
    var reducirMovimiento = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function obtenerTokenCsrf() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    // 1. Service Worker (PWA)
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function () {
            navigator.serviceWorker.register("/sw.js", { scope: "/" })
                .then(function (reg) {
                    registroSW = reg;
                    iniciarNotificaciones();
                })
                .catch(function () {
                    iniciarNotificaciones();
                });
        });
    } else {
        iniciarNotificaciones();
    }

    // 2. Instalación PWA desde Perfil -> Configuración
    var btnInstalar = document.getElementById("btnInstalarApp");
    window.addEventListener("beforeinstallprompt", function (e) {
        e.preventDefault();
        eventoInstalacion = e;
        if (btnInstalar) btnInstalar.style.display = "inline-flex";
    });

    if (btnInstalar) {
        btnInstalar.addEventListener("click", function () {
            if (!eventoInstalacion) return;
            eventoInstalacion.prompt();
            eventoInstalacion.userChoice.then(function () {
                eventoInstalacion = null;
                btnInstalar.style.display = "none";
            });
        });
    }

    // 3. Indicador deslizante de la barra inferior fija
    function posicionarIndicadorNav() {
        var barra = document.querySelector(".app-bottom-inner");
        var indicador = document.getElementById("navIndicador");
        if (!barra || !indicador) return;
        var items = barra.querySelectorAll(".nav-item");
        var indiceActivo = 0;
        for (var i = 0; i < items.length; i++) {
            if (items[i].classList.contains("activo")) {
                indiceActivo = i;
                break;
            }
        }
        // Si venimos de otra pestaña, animamos desde el índice previo guardado
        var previo = parseInt(sessionStorage.getItem("rm_nav_idx") || String(indiceActivo), 10);
        if (!reducirMovimiento && !isNaN(previo) && previo !== indiceActivo) {
            indicador.style.transition = "none";
            indicador.style.transform = "translateX(" + (previo * 100) + "%)";
            indicador.offsetWidth; // fuerza reflow
            indicador.style.transition = "";
        }
        indicador.style.transform = "translateX(" + (indiceActivo * 100) + "%)";
        sessionStorage.setItem("rm_nav_idx", String(indiceActivo));
    }
    posicionarIndicadorNav();

    // 4. Píldora deslizante en controles segmentados
    function iniciarSegmentados() {
        var grupos = document.querySelectorAll(".segmentado");
        for (var g = 0; g < grupos.length; g++) {
            var seg = grupos[g];
            var enlaces = seg.querySelectorAll("a");
            var pill = seg.querySelector(".segmentado-pill");
            if (!pill || enlaces.length === 0) continue;

            var activoIdx = 0;
            for (var i = 0; i < enlaces.length; i++) {
                if (enlaces[i].classList.contains("activo")) {
                    activoIdx = i;
                    break;
                }
            }

            var anchoPorc = (100 / enlaces.length);
            pill.style.width = "calc(" + anchoPorc + "% - " + (8 / enlaces.length) + "px)";

            var clave = "rm_seg_" + window.location.pathname;
            var previo = parseInt(sessionStorage.getItem(clave) || String(activoIdx), 10);
            if (!reducirMovimiento && !isNaN(previo) && previo !== activoIdx) {
                pill.style.transition = "none";
                pill.style.transform = "translateX(" + (previo * 100) + "%)";
                pill.offsetWidth;
                pill.style.transition = "";
            }
            pill.style.transform = "translateX(" + (activoIdx * 100) + "%)";
            sessionStorage.setItem(clave, String(activoIdx));
        }
    }
    iniciarSegmentados();

    // 5. Carrusel de canchas destacadas en Inicio (auto-avance 4.5s, pausa al tocar, puntos suaves)
    function iniciarCarruselDestacadas() {
        var pista = document.getElementById("carruselDestacadas");
        if (!pista) return;
        var slides = pista.querySelectorAll(".destacada-slide");
        var puntos = document.querySelectorAll("#carruselPuntos .carrusel-punto");
        if (slides.length === 0) return;

        var indiceActual = 0;
        var timerAuto = null;
        var timerReanudar = null;

        function marcarSlideActiva(idx) {
            indiceActual = idx;
            for (var i = 0; i < slides.length; i++) {
                slides[i].classList.toggle("activa", i === idx);
            }
            for (var j = 0; j < puntos.length; j++) {
                puntos[j].classList.toggle("activo", j === idx);
            }
        }

        function irASlide(idx) {
            var destino = (idx + slides.length) % slides.length;
            var slide = slides[destino];
            if (!slide) return;
            pista.scrollTo({
                left: slide.offsetLeft - 16,
                behavior: reducirMovimiento ? "auto" : "smooth"
            });
            marcarSlideActiva(destino);
        }

        function detenerAuto() {
            if (timerAuto) {
                clearInterval(timerAuto);
                timerAuto = null;
            }
        }

        function iniciarAuto() {
            if (reducirMovimiento || slides.length <= 1) return;
            detenerAuto();
            timerAuto = setInterval(function () {
                irASlide(indiceActual + 1);
            }, 4500);
        }

        function pausarYProgramarReanudacion() {
            detenerAuto();
            if (timerReanudar) clearTimeout(timerReanudar);
            if (!reducirMovimiento) {
                timerReanudar = setTimeout(iniciarAuto, 5500);
            }
        }

        // Detecta qué tarjeta está más centrada al deslizar con el dedo
        var scrollDebounce = null;
        pista.addEventListener("scroll", function () {
            if (scrollDebounce) clearTimeout(scrollDebounce);
            scrollDebounce = setTimeout(function () {
                var mejorIdx = 0;
                var menorDist = Infinity;
                for (var i = 0; i < slides.length; i++) {
                    var dist = Math.abs((slides[i].offsetLeft - 16) - pista.scrollLeft);
                    if (dist < menorDist) {
                        menorDist = dist;
                        mejorIdx = i;
                    }
                }
                marcarSlideActiva(mejorIdx);
            }, 90);
        }, { passive: true });

        pista.addEventListener("touchstart", pausarYProgramarReanudacion, { passive: true });
        pista.addEventListener("pointerdown", pausarYProgramarReanudacion, { passive: true });
        pista.addEventListener("wheel", pausarYProgramarReanudacion, { passive: true });

        for (var p = 0; p < puntos.length; p++) {
            (function (idxPunto) {
                puntos[idxPunto].addEventListener("click", function () {
                    irASlide(idxPunto);
                    pausarYProgramarReanudacion();
                });
            })(p);
        }

        marcarSlideActiva(0);
        iniciarAuto();
    }
    iniciarCarruselDestacadas();

    // 6. Control global de paneles inferiores (bottom sheets)
    window.abrirSheet = function (idSheet) {
        var el = document.getElementById(idSheet);
        if (!el) return;
        if (el.parentElement !== document.body) {
            document.body.appendChild(el);
            el.offsetWidth;
        }
        el.classList.add("abierto");
        document.body.style.overflow = "hidden";
    };

    window.cerrarSheet = function (idSheet) {
        var el = document.getElementById(idSheet);
        if (!el) return;
        el.classList.remove("abierto");
        document.body.style.overflow = "";
    };

    document.addEventListener("click", function (e) {
        if (e.target && e.target.classList && e.target.classList.contains("sheet-backdrop")) {
            e.target.classList.remove("abierto");
            document.body.style.overflow = "";
        }
        // Efecto "pop" al tocar el corazón de favorita
        var favBtn = e.target && e.target.closest ? e.target.closest(".btn-fav-mini") : null;
        if (favBtn) {
            favBtn.classList.remove("pop");
            favBtn.offsetWidth;
            favBtn.classList.add("pop");
        }
    });

    // 7. Notificaciones nativas + panel único con esqueleto shimmer al cargar
    function mostrarNotificacionNativa(notif) {
        if (!("Notification" in window) || Notification.permission !== "granted") return;
        var opciones = {
            body: notif.mensaje,
            icon: "/static/imagenes/icon-192.png",
            badge: "/static/imagenes/icon-192.png",
            tag: "ready-match-" + notif.id,
            data: { url: notif.url || "/" }
        };
        if (registroSW && typeof registroSW.showNotification === "function") {
            registroSW.showNotification(notif.titulo, opciones);
        } else {
            var n = new Notification(notif.titulo, opciones);
            n.onclick = function () {
                window.focus();
                if (notif.url) window.location.href = notif.url;
            };
        }
    }

    function revisarNotificacionesPendientes() {
        if (!usuarioLogueado) return;
        fetch("/api/notificaciones/pendientes", { credentials: "same-origin" })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (datos) {
                var punto = document.getElementById("puntoNotif");
                if (!datos || !datos.notificaciones || datos.notificaciones.length === 0) {
                    if (punto) punto.style.display = "none";
                    return;
                }
                if (punto) punto.style.display = "block";
                if ("Notification" in window && Notification.permission === "granted") {
                    var ids = [];
                    for (var i = 0; i < datos.notificaciones.length; i++) {
                        mostrarNotificacionNativa(datos.notificaciones[i]);
                        ids.push(datos.notificaciones[i].id);
                    }
                    fetch("/api/notificaciones/marcar_enviadas", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRF-Token": obtenerTokenCsrf()
                        },
                        credentials: "same-origin",
                        body: JSON.stringify({ ids: ids })
                    });
                }
            })
            .catch(function () {});
    }

    function actualizarEstadoNotifUI() {
        var texto = document.getElementById("estadoNotifTexto");
        var btnActivar = document.getElementById("btnActivarNotif");
        var btnProbar = document.getElementById("btnProbarNotif");
        var soportado = "Notification" in window;
        var permiso = soportado ? Notification.permission : "unsupported";

        if (texto) {
            if (!soportado) texto.textContent = "Este navegador no admite notificaciones emergentes.";
            else if (permiso === "granted") texto.textContent = "Activas: recibirás avisos de partidos, reservas y novedades.";
            else if (permiso === "denied") texto.textContent = "Bloqueadas en el navegador. Actívalas desde la barra de dirección.";
            else texto.textContent = "Desactivadas. Actívalas para recibir avisos al instante.";
        }
        if (btnActivar) btnActivar.style.display = (soportado && permiso === "default") ? "inline-flex" : "none";
        if (btnProbar) btnProbar.style.display = (soportado && permiso === "granted") ? "inline-flex" : "none";
    }

    function iniciarNotificaciones() {
        actualizarEstadoNotifUI();
        if (usuarioLogueado) {
            revisarNotificacionesPendientes();
            setInterval(revisarNotificacionesPendientes, 30000);
        }
    }

    window.abrirNotificaciones = function () {
        actualizarEstadoNotifUI();
        window.abrirSheet("sheetNotificaciones");
        var lista = document.getElementById("listaNotificaciones");
        if (!lista || !usuarioLogueado) return;
        // Esqueletos shimmer mientras cargan los avisos
        lista.innerHTML = '<div class="skeleton-wrap"><div class="skeleton-linea"></div><div class="skeleton-linea"></div><div class="skeleton-linea"></div></div>';
        fetch("/api/notificaciones/recientes", { credentials: "same-origin" })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (datos) {
                if (!datos || !datos.notificaciones || datos.notificaciones.length === 0) {
                    lista.innerHTML = '<div class="estado-vacio"><strong>Sin notificaciones</strong><p>Aquí verás avisos de tus reservas y partidos.</p></div>';
                    return;
                }
                lista.innerHTML = "";
                for (var i = 0; i < datos.notificaciones.length; i++) {
                    var n = datos.notificaciones[i];
                    var enlace = document.createElement("a");
                    enlace.href = n.url || "/";
                    enlace.className = "fila-registro";
                    enlace.style.display = "block";
                    enlace.style.marginBottom = "8px";
                    var t = document.createElement("strong");
                    t.className = "fila-registro-titulo";
                    t.textContent = n.titulo;
                    var m = document.createElement("p");
                    m.className = "texto-apoyo";
                    m.style.marginTop = "2px";
                    m.textContent = n.mensaje;
                    enlace.appendChild(t);
                    enlace.appendChild(m);
                    lista.appendChild(enlace);
                }
            })
            .catch(function () {
                lista.innerHTML = '<p class="texto-apoyo">No se pudieron cargar las notificaciones.</p>';
            });
    };

    window.activarNotificacionesReadyMatch = function () {
        if (!("Notification" in window)) return;
        Notification.requestPermission().then(function (permiso) {
            actualizarEstadoNotifUI();
            if (permiso === "granted") revisarNotificacionesPendientes();
        });
    };

    window.probarNotificacionReadyMatch = function () {
        if (!("Notification" in window) || Notification.permission !== "granted") {
            window.activarNotificacionesReadyMatch();
            return;
        }
        fetch("/api/notificaciones/prueba", {
            method: "POST",
            headers: { "X-CSRF-Token": obtenerTokenCsrf() },
            credentials: "same-origin"
        }).then(function () {
            revisarNotificacionesPendientes();
        });
    };

    // 8. Utilidades generales
    window.mostrarNombreArchivo = function (input, idEtiqueta) {
        var etiqueta = document.getElementById(idEtiqueta);
        if (!etiqueta) return;
        etiqueta.textContent = (input.files && input.files.length > 0) ? input.files[0].name : "Ninguna imagen";
    };

    document.addEventListener("submit", function (evento) {
        if (evento.defaultPrevented) return;
        var boton = evento.target.querySelector('button[type="submit"]');
        if (boton && !boton.classList.contains("btn-fav-mini") && !boton.classList.contains("btn-mini-inline")) {
            boton.classList.add("cargando");
            boton.disabled = true;
        }
    });

    var toasts = document.querySelectorAll(".toast");
    if (toasts.length > 0) {
        setTimeout(function () {
            for (var i = 0; i < toasts.length; i++) {
                toasts[i].style.opacity = "0";
                toasts[i].style.transform = "translateY(-8px)";
            }
        }, 4200);
        setTimeout(function () {
            for (var j = 0; j < toasts.length; j++) {
                toasts[j].style.display = "none";
            }
        }, 4500);
    }
})();
