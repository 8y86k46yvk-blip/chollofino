#!/usr/bin/env python3
"""Canales de Telegram de Adrian (@chollofino y @precioridiculo): publica solo lo de cada día.

Lo ejecuta el taller .github/workflows/telegram.yml cada media hora (8:05-22:35 UTC). Necesita la variable de
entorno TELEGRAM_BOT_TOKEN (secreto del repo chollofino). Desde la raíz del repo:

  python3 _herramientas/telegram.py comprobar
      Dice si el bot existe y si puede publicar en los dos canales. No publica nada.

  python3 _herramientas/telegram.py publicar CARPETA [COLA_PR] [WEB_PR]
      CARPETA es la rama «telegram» de este repo: cola.json (vídeos de Chollo Fino que apunta la tarea diaria de
      redes) y publicado.json (lo ya publicado, lo escribe este script). COLA_PR es cola.json de la rama «telegram»
      del repo Precioridiculo- (vídeos de Precio Ridículo).

Qué se publica:
  · Vídeos de la cola (los mismos que van a las redes), a su hora o en cuanto pase, solo los del día.
  · @precioridiculo: los cupones de AliExpress en vigor (cupones.json de la web), en un mensaje a las 12:30 los días
    en que la lista de códigos cambia (con enlace a elprecioridiculo.com/cupones/).
  · Mensajes sueltos de la cola (piezas con "tipo": "mensaje"): {"id", "fecha", "hora", "tipo": "mensaje",
    "texto" (HTML de Telegram), "fijar": true (opcional: lo fija arriba del canal)}. Para avisos como el del 11.11.
  · @precioridiculo: cada oferta de hoy de elprecioridiculo.com (AliExpress con precio ≈ y Hacoo; nunca las que llevan
    "solo_web": true, como las de Joom), con su pin de Ridi
    o la foto de la tienda y el enlace de Admitad con subid=tg; WEB_PR es index.html de esa web (rama main).
  · @chollofino: además, cada oferta de hoy de la web (OFERTAS de index.html) con su foto de Fino (el pin de
    public/chollofino/pines/AAAA-MM-DD-cf-pines/n<numero>.jpg) y el enlace con el ID chollofinotg-21, repartidas
    de 11:00 a 21:59 (hora de Canarias). Una oferta que ya sale sola en un vídeo «chollo» de hoy no se repite, y un
    mismo ASIN no se publica dos veces en 5 días.

Formato de cola.json: {"piezas": [{"id": "2026-11-11-cf-dia-rowenta", "fecha": "2026-11-11", "hora": "13:30",
  "url": "https://shorts.todo-picks-academy.pages.dev/chollofino/shorts/<id>.mp4", "titulo": "<gancho>",
  "numeros": [31]}]}. En Precio Ridículo, en vez de "numeros", "texto" (1-2 frases) y, solo en fase 2, "enlace"
  (enlace de afiliado de Hacoo). Precio, enlace con ID, #publi y pie los pone este script.

Con la variable SIMULAR=1 no se manda nada: enseña los mensajes (para probar).
"""
import datetime
import html
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paginas import RAIZ, leer_datos, euros, dto  # noqa: E402

CANALES = {"chollofino": "@chollofino", "precioridiculo": "@precioridiculo"}
TAG = "chollofinotg-21"
PINES = "https://shorts.todo-picks-academy.pages.dev/chollofino/pines/{fecha}-cf-pines/n{numero}.jpg"
PINES_PR = "https://shorts.todo-picks-academy.pages.dev/precioridiculo/pines/{fecha}-pr-pines/n{numero}.jpg"
INICIO_OFERTAS, FIN_OFERTAS = 11 * 60, 21 * 60 + 59   # minutos del día, hora de Canarias
MAX_OFERTAS_POR_VEZ = 3
ESPERAR_FOTO_HASTA = 13 * 60  # si el pin aún no está, la oferta espera; desde las 13:00 sale sin él
MAX_VIDEOS_POR_VEZ = 2
DIAS_SIN_REPETIR_ASIN = 5
ZONA = ZoneInfo("Atlantic/Canary")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
E = lambda s: html.escape(str(s if s is not None else ""), quote=False)  # noqa: E731


# ---------- Telegram ----------

def api(metodo, **datos):
    if os.environ.get("SIMULAR"):
        print(f"--- {metodo} {datos.get('chat_id', '')} {datos.get('photo') or datos.get('video') or ''}")
        print(datos.get("caption") or datos.get("text") or "")
        return {"ok": True, "result": {"message_id": 0, "id": 0, "username": "simulado", "status": "administrator",
                                       "can_post_messages": True}}
    peticion = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{metodo}",
                                      data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # Telegram explica el error en el cuerpo (nunca sale el token)
        try:
            return json.load(e)
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "description": type(e).__name__}


def api_archivo(metodo, campo, url, **datos):
    """Si Telegram no puede bajar el archivo por su cuenta, lo bajamos aquí y se lo subimos (máx. 50 MB)."""
    r = api(metodo, **{campo: url}, **datos)
    if r.get("ok") or os.environ.get("SIMULAR"):
        return r
    print(f"   Telegram no pudo bajar {url} ({r.get('description')}): lo subo desde aquí")
    try:
        with urllib.request.urlopen(url, timeout=120) as f:
            contenido, tipo = f.read(), f.headers.get("Content-Type", "application/octet-stream")
    except Exception as e:
        return {"ok": False, "description": f"no se pudo bajar el archivo ({type(e).__name__})"}
    limite = "----cf" + os.urandom(8).hex()
    cuerpo = b""
    for k, v in datos.items():
        v = json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
        cuerpo += f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    nombre = url.rsplit("/", 1)[-1]
    cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo}\"; filename=\"{nombre}\"\r\n"
               f"Content-Type: {tipo}\r\n\r\n").encode() + contenido + f"\r\n--{limite}--\r\n".encode()
    peticion = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{metodo}", data=cuerpo,
                                      headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    try:
        with urllib.request.urlopen(peticion, timeout=180) as r2:
            return json.load(r2)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "description": type(e).__name__}


def es_imagen(url, contar=False):
    """Cloudflare Pages contesta 200 con la portada si el archivo no existe: hay que mirar el tipo."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CholloFinoBot/1.0)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tipo = r.headers.get("Content-Type", "")
            r.read(1)
            ok = r.status == 200 and tipo.startswith("image/")
            motivo = f"HTTP {r.status}, {tipo}"
    except urllib.error.HTTPError as e:
        ok, motivo = False, f"HTTP {e.code}"
    except Exception as e:
        ok, motivo = False, type(e).__name__
    if contar:
        print(f"   {'✅' if ok else '❌'} foto {url.rsplit('/', 2)[-2]}/{url.rsplit('/', 1)[-1]}: {motivo}")
    return ok


def visible(t):
    return len(html.unescape(re.sub(r"<[^>]+>", "", t)))


# ---------- textos ----------

def con_tag(enlace):
    u = urllib.parse.urlsplit(enlace)
    q = dict(urllib.parse.parse_qsl(u.query))
    q["tag"] = TAG
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), ""))


def asin(o):
    m = re.search(r"/dp/([A-Z0-9]{10})", o.get("enlace") or "")
    return m.group(1) if m else None


def precio_linea(o):
    d, a = dto(o), ("≈" if o.get("aprox") else "")
    t = f"💶 <b>{a}{E(euros(o['precio']))}</b>"
    if o.get("antes") and d:
        t += f"   <s>{a}{E(euros(o['antes']))}</s>   −{d} %"
    return t


def con_subid(enlace, subid="tg"):
    """Enlaces de Admitad: subid dice en el informe de Admitad de dónde vino la venta (web, tg…)."""
    u = urllib.parse.urlsplit(enlace)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if k != "subid"] + [("subid", subid)]
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), ""))


def tienda(o):
    return str(o.get("tienda") or "la tienda").strip()


def pie_pr(fecha, aprox, con_publi=True, nombre_tienda="la tienda"):
    f = datetime.date.fromisoformat(fecha)
    t = "🛍️ <a href=\"https://elprecioridiculo.com\">Más chollos en elprecioridiculo.com</a>"
    if con_publi:
        nota = (f"Precio aproximado del {f.day}/{f.month} (pasado de dólares); el final, en {E(nombre_tienda)}."
                if aprox else f"Precio del {f.day}/{f.month}, puede cambiar.")
        t += f"\n<i>#publi · Enlace de afiliado. {nota}</i>"
    return t


def texto_oferta_pr(o, con_descripcion=True):
    partes = [f"🔥 <b>{E(o['producto'])}</b>", "", precio_linea(o)]
    if con_descripcion and o.get("descripcion"):
        partes.append(E(o["descripcion"]))
    partes += ["", f"👉 <a href=\"{E(con_subid(o['enlace']))}\">Ver en {E(tienda(o))}</a>", "",
               f"Nº {E(o['numero'])} en la web", pie_pr(o["fecha"][:10], o.get("aprox"), True, tienda(o))]
    return "\n".join(partes)


def pie_cf(fecha):
    f = datetime.date.fromisoformat(fecha)
    return (f"🏷️ <a href=\"https://chollofino.com/?d=tg\">Más chollos en chollofino.com</a>\n"
            f"<i>#publi · Enlace de afiliado. Precio del {f.day}/{f.month}, puede cambiar.</i>")


def texto_oferta(o, con_descripcion=True):
    partes = [f"🔥 <b>{E(o['producto'])}</b>", "", precio_linea(o)]
    if con_descripcion and o.get("descripcion"):
        partes.append(E(o["descripcion"]))
    partes += ["", f"👉 <a href=\"{E(con_tag(o['enlace']))}\">Ver en Amazon</a>", "",
               f"Nº {E(o['numero'])} en la web", pie_cf(o["fecha"][:10])]
    return "\n".join(partes)


def texto_video_cf(p, por_numero):
    productos = [por_numero[n] for n in p.get("numeros", []) if n in por_numero]
    partes = [f"🎬 <b>{E(corto(p.get('titulo'), 120) or 'Chollo Fino')}</b>", ""]
    if len(productos) == 1:
        o = productos[0]
        partes += [f"🔥 <b>{E(o['producto'])}</b>", precio_linea(o), "",
                   f"👉 <a href=\"{E(con_tag(o['enlace']))}\">Ver en Amazon</a> · Nº {E(o['numero'])}", ""]
    elif productos:
        for i, o in enumerate(productos, 1):
            partes.append(f"{i}. {E(o['producto'])}: <b>{E(euros(o['precio']))}</b> → "
                          f"<a href=\"{E(con_tag(o['enlace']))}\">Ver en Amazon</a>")
        partes.append("")
    partes.append(pie_cf(p["fecha"]))
    return "\n".join(partes)


def texto_video_pr(p, por_numero=None):
    productos = [por_numero[n] for n in p.get("numeros", []) if por_numero and n in por_numero]
    partes = [f"🎬 <b>{E(corto(p.get('titulo'), 120) or 'Precio Ridículo')}</b>"]
    if p.get("texto"):
        partes += ["", E(corto(p["texto"], 600))]
    if productos:
        for o in productos:
            partes += ["", f"🔥 <b>{E(o['producto'])}</b>", precio_linea(o),
                       f"👉 <a href=\"{E(con_subid(o['enlace']))}\">Ver en {E(tienda(o))}</a> · Nº {E(o['numero'])}"]
        o = productos[0]
        partes += ["", pie_pr(p["fecha"], any(x.get("aprox") for x in productos), True, tienda(o))]
        return "\n".join(partes)
    if p.get("enlace"):
        partes += ["", f"👉 <a href=\"{E(p['enlace'])}\">Ver en Hacoo</a>"]
    partes += ["", "🛍️ <a href=\"https://elprecioridiculo.com\">Más en elprecioridiculo.com</a>"]
    if p.get("enlace"):
        f = datetime.date.fromisoformat(p["fecha"])
        partes.append(f"<i>#publi · Enlace de afiliado. Precio del {f.day}/{f.month}, puede cambiar.</i>")
    return "\n".join(partes)


def corto(t, n):
    t = str(t or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# ---------- estado ----------

def leer_json(ruta, vacio):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except Exception:
        return vacio


MAX_FALLOS = 3  # una pieza que falla 3 veces se deja (y el taller deja de dar error por ella)


def ya(estado, canal, clave):
    return (any(x["clave"] == clave for x in estado.get(canal, []))
            or estado.get("fallos", {}).get(f"{canal}:{clave}", 0) >= MAX_FALLOS)


def fallo(estado, canal, clave):
    f = estado.setdefault("fallos", {})
    f[f"{canal}:{clave}"] = f.get(f"{canal}:{clave}", 0) + 1


def apuntar(estado, canal, clave, ahora, r, extra=None):
    d = {"clave": clave, "fecha": ahora.date().isoformat(), "hora": ahora.strftime("%H:%M"),
         "message_id": r["result"]["message_id"]}
    d.update(extra or {})
    estado.setdefault(canal, []).append(d)


# ---------- modos ----------

def comprobar():
    if not TOKEN:
        print("❌ Falta el secreto TELEGRAM_BOT_TOKEN en el repo.")
        return 1
    yo = api("getMe")
    if not yo.get("ok"):
        print("❌ El token no funciona:", yo.get("description"))
        return 1
    bot = yo["result"]
    print(f"✅ Bot: @{bot.get('username')} ({bot.get('first_name')})")
    fallo = 0
    for canal in CANALES.values():
        m = api("getChatMember", chat_id=canal, user_id=bot["id"])
        if not m.get("ok"):
            print(f"❌ {canal}: {m.get('description')}")
            fallo = 1
            continue
        r = m["result"]
        puede = r.get("status") == "creator" or (r.get("status") == "administrator" and r.get("can_post_messages", False))
        fija = r.get("status") == "creator" or (r.get("status") == "administrator" and r.get("can_edit_messages", False))
        print(f"{'✅' if puede else '❌'} {canal}: {r.get('status')}, puede publicar: {'sí' if puede else 'no'}, "
              f"puede fijar: {'sí' if fija else 'no'}")
        fallo |= not puede
    hoy = datetime.datetime.now(ZONA).date().isoformat()
    ofertas = leer_datos((RAIZ / "index.html").read_text(encoding="utf-8"))["OFERTAS"]
    for o in [o for o in ofertas if str(o.get("fecha", ""))[:10] == hoy][:3]:
        es_imagen(PINES.format(fecha=hoy, numero=o["numero"]), contar=True)
    return fallo


def publicar_videos(estado, canal, cola, ahora, crear_texto):
    hoy, ahora_txt, errores = ahora.date().isoformat(), ahora.strftime("%H:%M"), 0
    pendientes = sorted((p for p in cola.get("piezas", []) if p.get("fecha") == hoy and p.get("url")
                         and p.get("hora", "99:99") <= ahora_txt and not ya(estado, canal, "video-" + p["id"])),
                        key=lambda p: p["hora"])
    for p in pendientes[:MAX_VIDEOS_POR_VEZ]:
        texto = crear_texto(p)
        r = api_archivo("sendVideo", "video", p["url"], chat_id=CANALES[canal], caption=texto, parse_mode="HTML",
                        supports_streaming=True)
        if r.get("ok"):
            apuntar(estado, canal, "video-" + p["id"], ahora, r)
            print(f"✅ {canal}: vídeo {p['id']}")
        else:
            errores += 1
            fallo(estado, canal, "video-" + p["id"])
            print(f"❌ {canal}: vídeo {p['id']}: {r.get('description')}")
    return errores


def publicar_mensajes(estado, canal, cola, ahora):
    """Mensajes sueltos de la cola ("tipo": "mensaje"), a su hora; si llevan "fijar", se fijan en el canal."""
    hoy, ahora_txt, errores = ahora.date().isoformat(), ahora.strftime("%H:%M"), 0
    pendientes = sorted((p for p in cola.get("piezas", []) if p.get("tipo") == "mensaje" and p.get("fecha") == hoy
                         and p.get("texto") and p.get("hora", "99:99") <= ahora_txt
                         and not ya(estado, canal, "mensaje-" + p["id"])), key=lambda p: p["hora"])
    for p in pendientes[:2]:
        r = api("sendMessage", chat_id=CANALES[canal], text=p["texto"], parse_mode="HTML")
        if not r.get("ok"):
            errores += 1
            fallo(estado, canal, "mensaje-" + p["id"])
            print(f"❌ {canal}: mensaje {p['id']}: {r.get('description')}")
            continue
        extra = {}
        if p.get("fijar"):
            f = api("pinChatMessage", chat_id=CANALES[canal], message_id=r["result"]["message_id"])
            extra["fijado"] = bool(f.get("ok"))
            if not f.get("ok"):
                errores += 1
                print(f"❌ {canal}: mensaje {p['id']} publicado, pero no se pudo fijar: {f.get('description')}")
        apuntar(estado, canal, "mensaje-" + p["id"], ahora, r, extra)
        print(f"✅ {canal}: mensaje {p['id']}{' (fijado)' if extra.get('fijado') else ''}")
    return errores


HORA_CUPONES = "12:30"


def publicar_cupones_pr(estado, cupones_ruta, ahora):
    """Cupones en vigor de elprecioridiculo.com en @precioridiculo: un mensaje cuando cambia la lista de códigos."""
    if not cupones_ruta or ahora.strftime("%H:%M") < HORA_CUPONES:
        return 0
    hoy = ahora.date()
    lista = []
    for c in leer_json(cupones_ruta, {}).get("cupones", []):
        try:
            if c.get("hasta") and datetime.date.fromisoformat(str(c["hasta"])[:10]) < hoy:
                continue
        except ValueError:
            continue
        if str(c.get("enlace", "")).startswith("https://") and c.get("titulo"):
            lista.append(c)
    if not lista:
        return 0
    huella = "|".join(sorted(str(c.get("codigo") or c.get("titulo")) for c in lista))
    ultimo = next((x for x in reversed(estado.get("precioridiculo", [])) if x.get("clave", "").startswith("cupones-")), None)
    if (ultimo and ultimo.get("huella") == huella) or ya(estado, "precioridiculo", f"cupones-{hoy.isoformat()}"):
        return 0
    partes = ["🎟️ <b>CUPONES DE ALIEXPRESS PARA HOY</b>", "",
              "Cópialo y ponlo al pagar, en la casilla del cupón:", ""]
    for c in lista[:8]:
        linea = f"• <b>{E(c['titulo'])}</b>"
        if c.get("codigo"):
            linea += f"\n   Código: <code>{E(c['codigo'])}</code>"
        else:
            linea += f"\n   👉 <a href=\"{E(con_subid(c['enlace']))}\">Sin código: entra desde aquí</a>"
        if c.get("hasta"):
            f = datetime.date.fromisoformat(str(c["hasta"])[:10])
            linea += f" · hasta el {f.day}/{f.month}"
        partes.append(linea)
    partes += ["", "👉 <a href=\"https://elprecioridiculo.com/cupones/?d=tg\">Todos los cupones en elprecioridiculo.com</a>",
               "<i>Los pone AliExpress y pueden agotarse antes de su fecha. Enlaces de afiliado.</i>"]
    r = api("sendMessage", chat_id=CANALES["precioridiculo"], text="\n".join(partes), parse_mode="HTML",
            link_preview_options={"is_disabled": True})
    if r.get("ok"):
        apuntar(estado, "precioridiculo", f"cupones-{hoy.isoformat()}", ahora, r, {"huella": huella})
        print(f"✅ precioridiculo: {len(lista)} cupones")
        return 0
    fallo(estado, "precioridiculo", f"cupones-{hoy.isoformat()}")
    print(f"❌ precioridiculo: cupones: {r.get('description')}")
    return 1


def publicar_ofertas(estado, ofertas, cola, ahora):
    minuto = ahora.hour * 60 + ahora.minute
    if not (INICIO_OFERTAS <= minuto <= FIN_OFERTAS):
        print("Ofertas: fuera de horario (11:00-21:59).")
        return 0
    hoy = ahora.date().isoformat()
    hace = (ahora.date() - datetime.timedelta(days=DIAS_SIN_REPETIR_ASIN)).isoformat()
    asins_recientes = {x.get("asin") for x in estado.get("chollofino", []) if x.get("fecha", "") >= hace}
    en_video = {p["numeros"][0] for p in cola.get("piezas", []) if p.get("fecha") == hoy and len(p.get("numeros", [])) == 1}
    candidatas = [o for o in ofertas if not o.get("ejemplo") and str(o.get("fecha", ""))[:10] == hoy and asin(o)
                  and o.get("precio") is not None and o.get("numero") not in en_video
                  and asin(o) not in asins_recientes and not ya(estado, "chollofino", f"oferta-{hoy}-{o.get('numero')}")]
    candidatas.sort(key=lambda o: -(o.get("numero") or 0))
    turnos = max(1, (FIN_OFERTAS - minuto) // 30 + 1)
    cuantas = min(MAX_OFERTAS_POR_VEZ, math.ceil(len(candidatas) / turnos)) if candidatas else 0
    print(f"Ofertas: {len(candidatas)} por publicar hoy, {turnos} turnos, ahora {cuantas}")
    errores = 0
    for o in candidatas[:cuantas]:
        foto = PINES.format(fecha=hoy, numero=o["numero"])
        con_foto = es_imagen(foto, contar=True)
        if not con_foto and minuto < ESPERAR_FOTO_HASTA:
            print(f"   Nº {o['numero']}: espero a que esté su foto de Fino (hasta las 13:00)")
            continue
        if con_foto:  # el pie de foto admite 1024 caracteres: si no cabe, sin descripción
            texto = texto_oferta(o)
            if visible(texto) > 1024:
                texto = texto_oferta(o, con_descripcion=False)
            r = api_archivo("sendPhoto", "photo", foto, chat_id=CANALES["chollofino"], caption=texto, parse_mode="HTML")
        else:  # sin pin: la vista previa de Amazon hace de foto
            r = api("sendMessage", chat_id=CANALES["chollofino"], text=texto_oferta(o), parse_mode="HTML",
                    link_preview_options={"url": con_tag(o["enlace"]), "prefer_large_media": True})
        if r.get("ok"):
            apuntar(estado, "chollofino", f"oferta-{hoy}-{o['numero']}", ahora, r, {"asin": asin(o)})
            print(f"✅ chollofino: oferta Nº {o['numero']}{'' if con_foto else ' (sin foto de Fino)'}")
        else:
            errores += 1
            fallo(estado, "chollofino", f"oferta-{hoy}-{o['numero']}")
            print(f"❌ chollofino: oferta Nº {o['numero']}: {r.get('description')}")
    return errores


def publicar_ofertas_pr(estado, ofertas, cola, ahora):
    """Ofertas de hoy de elprecioridiculo.com en @precioridiculo, con su pin de Ridi o la foto de la tienda."""
    minuto = ahora.hour * 60 + ahora.minute
    if not (INICIO_OFERTAS <= minuto <= FIN_OFERTAS):
        return 0
    hoy = ahora.date().isoformat()
    hace = (ahora.date() - datetime.timedelta(days=DIAS_SIN_REPETIR_ASIN)).isoformat()
    recientes = {x.get("producto_id") for x in estado.get("precioridiculo", []) if x.get("fecha", "") >= hace}
    en_video = {n for p in cola.get("piezas", []) if p.get("fecha") == hoy for n in p.get("numeros", [])[:1]
                if len(p.get("numeros", [])) == 1}
    pid = lambda o: str(o.get("ali_id") or o.get("joom_id") or o.get("enlace") or o.get("numero"))  # noqa: E731
    # solo_web: ofertas que van solo en la web (Joom, hasta que su gestor apruebe publicarlas en redes y Telegram)
    candidatas = [o for o in ofertas if not o.get("ejemplo") and not o.get("solo_web") and str(o.get("fecha", ""))[:10] == hoy
                  and str(o.get("enlace", "")).startswith("https://") and o.get("precio") is not None
                  and o.get("numero") not in en_video and pid(o) not in recientes
                  and not ya(estado, "precioridiculo", f"oferta-{hoy}-{o.get('numero')}")]
    candidatas.sort(key=lambda o: -(o.get("numero") or 0))
    turnos = max(1, (FIN_OFERTAS - minuto) // 30 + 1)
    cuantas = min(MAX_OFERTAS_POR_VEZ, math.ceil(len(candidatas) / turnos)) if candidatas else 0
    print(f"Ofertas Precio Ridículo: {len(candidatas)} por publicar hoy, {turnos} turnos, ahora {cuantas}")
    errores = 0
    for o in candidatas[:cuantas]:
        pin = PINES_PR.format(fecha=hoy, numero=o["numero"])
        foto = pin if es_imagen(pin, contar=True) else (o.get("imagen") if str(o.get("imagen", "")).startswith("https://") else "")
        texto = texto_oferta_pr(o)
        if foto:
            if visible(texto) > 1024:
                texto = texto_oferta_pr(o, con_descripcion=False)
            r = api_archivo("sendPhoto", "photo", foto, chat_id=CANALES["precioridiculo"], caption=texto, parse_mode="HTML")
        else:
            r = api("sendMessage", chat_id=CANALES["precioridiculo"], text=texto, parse_mode="HTML",
                    link_preview_options={"is_disabled": True})
        if r.get("ok"):
            apuntar(estado, "precioridiculo", f"oferta-{hoy}-{o['numero']}", ahora, r, {"producto_id": pid(o)})
            print(f"✅ precioridiculo: oferta Nº {o['numero']}{'' if foto else ' (sin foto)'}")
        else:
            errores += 1
            fallo(estado, "precioridiculo", f"oferta-{hoy}-{o['numero']}")
            print(f"❌ precioridiculo: oferta Nº {o['numero']}: {r.get('description')}")
    return errores


def publicar(carpeta, cola_pr_ruta=None, web_pr_ruta=None):
    if not TOKEN:
        print("❌ Falta TELEGRAM_BOT_TOKEN: no se publica nada.")
        return 1
    ahora = datetime.datetime.now(ZONA)
    carpeta = Path(carpeta)
    estado = leer_json(carpeta / "publicado.json", {})
    cola_cf = leer_json(carpeta / "cola.json", {"piezas": []})
    cola_pr = leer_json(cola_pr_ruta, {"piezas": []}) if cola_pr_ruta else {"piezas": []}
    ofertas = leer_datos((RAIZ / "index.html").read_text(encoding="utf-8"))["OFERTAS"]
    por_numero = {o.get("numero"): o for o in ofertas if not o.get("ejemplo") and asin(o)}
    ofertas_pr = []
    if web_pr_ruta and Path(web_pr_ruta).exists():
        try:
            ofertas_pr = leer_datos(Path(web_pr_ruta).read_text(encoding="utf-8"))["OFERTAS"]
        except Exception as e:
            print("No pude leer las ofertas de Precio Ridículo:", type(e).__name__)
    por_numero_pr = {o.get("numero"): o for o in ofertas_pr if not o.get("ejemplo") and o.get("enlace")}
    print(f"Hora de Canarias: {ahora:%d/%m %H:%M}")

    errores = publicar_videos(estado, "chollofino", cola_cf, ahora, lambda p: texto_video_cf(p, por_numero))
    errores += publicar_videos(estado, "precioridiculo", cola_pr, ahora, lambda p: texto_video_pr(p, por_numero_pr))
    errores += publicar_mensajes(estado, "chollofino", cola_cf, ahora)
    errores += publicar_mensajes(estado, "precioridiculo", cola_pr, ahora)
    if web_pr_ruta:
        errores += publicar_cupones_pr(estado, Path(web_pr_ruta).parent / "cupones.json", ahora)
    errores += publicar_ofertas(estado, ofertas, cola_cf, ahora)
    errores += publicar_ofertas_pr(estado, ofertas_pr, cola_pr, ahora)

    limite = (ahora.date() - datetime.timedelta(days=30)).isoformat()
    hoy = ahora.date().isoformat()
    estado = {c: ([x for x in v if x.get("fecha", "") >= limite] if isinstance(v, list)
                  else {k: n for k, n in v.items() if hoy in k}) for c, v in estado.items()}
    (carpeta / "publicado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if errores else 0


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "comprobar"
    if modo == "comprobar":
        sys.exit(comprobar())
    sys.exit(publicar(sys.argv[2] if len(sys.argv) > 2 else ".", sys.argv[3] if len(sys.argv) > 3 else None,
                      sys.argv[4] if len(sys.argv) > 4 else None))
