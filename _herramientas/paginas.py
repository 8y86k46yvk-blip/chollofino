#!/usr/bin/env python3
"""Chollo Fino · genera las páginas que Google puede leer, a partir de las ofertas de index.html.

Uso (desde la raíz del repo): python3 _herramientas/paginas.py
Lee CONFIG, OFERTAS e ICONOS de index.html (con node) y escribe:
  ofertas/index.html                     (todas las categorías)
  ofertas/<categoría>/index.html         (una por categoría de CONFIG)
  ofertas/menos-de-10-euros/index.html, ofertas/menos-de-20-euros/index.html
  black-friday/index.html                (especial Black Friday, estático)
  assets/web/estilo.css                  (los estilos de index.html, para estas páginas)
  sitemap.xml y robots.txt
No toca index.html. Lo ejecuta la tarea diaria de ofertas después de cambiar OFERTAS.
La carpeta _herramientas no se publica (GitHub Pages ignora las carpetas que empiezan por «_»).
"""
import datetime
import html
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
DOMINIO = "https://chollofino.com"
TRACKER = ('<script>function loadScript(a){var b=document.getElementsByTagName("head")[0],c=document.createElement("script");'
           'c.type="text/javascript",c.src="https://tracker.metricool.com/resources/be.js",c.onreadystatechange=a,c.onload=a,'
           'b.appendChild(c)}loadScript(function(){beTracker.t({hash:"55207af0a8783139bf290ab2c45ab449"})});</script>')
POSES = ["fino-4-pulgar-guino", "fino-2-sorpresa", "fino-3-senala", "fino-6-piensa", "fino-1-saludo", "fino-0-base"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]

# Textos de cada categoría (propios, para Google y para quien llega)
TEXTOS = {
    "Tecnología": ("Chollos de tecnología en Amazon", "Auriculares, cargadores, monitores, teclados y gadgets con descuento real."),
    "Hogar": ("Chollos para el hogar en Amazon", "Robots aspiradores, limpieza, organización y todo lo de casa, a buen precio."),
    "Cocina": ("Chollos de cocina en Amazon", "Freidoras de aire, cuchillos, menaje y pequeños electrodomésticos con rebaja."),
    "Belleza": ("Chollos de belleza en Amazon", "Cuidado del pelo, de la piel y maquillaje de marcas conocidas, con descuento."),
    "Deporte": ("Chollos de deporte en Amazon", "Zapatillas, relojes deportivos, ropa y material para entrenar, rebajados."),
    "Juguetes": ("Chollos de juguetes en Amazon", "Juguetes, juegos de mesa y construcciones con descuento, para acertar en Navidad."),
    "Moda": ("Chollos de moda en Amazon", "Zapatillas, botas y ropa de marca con descuento real."),
    "Regalos": ("Ideas de regalo baratas en Amazon", "Detalles y regalos con descuento para Navidad, cumpleaños o amigo invisible."),
}


def slug(txt):
    t = unicodedata.normalize("NFD", txt.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def leer_datos(index):
    def bloque(patron):
        m = re.search(patron, index)
        if not m:
            raise SystemExit(f"No encuentro {patron!r} en index.html")
        return m.group(0)
    js = "\n".join([bloque(r"const CONFIG = \{[\s\S]*?\n\};"), bloque(r"const OFERTAS = \[[\s\S]*?\n\];"),
                    bloque(r"const ICONOS = \{[\s\S]*?\n\};"),
                    "console.log(JSON.stringify({CONFIG, OFERTAS, ICONOS}));"])
    salida = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(salida)


def euros(x):
    if x is None:
        return ""
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if re.fullmatch(r"\d\.\d{3},\d{2}", s):  # es-ES no agrupa los miles con 4 cifras
        s = s.replace(".", "")
    return s + " €"


def dto(o):
    return round((1 - o["precio"] / o["antes"]) * 100) if o.get("precio") and o.get("antes") and o["antes"] > o["precio"] else 0


def fecha_larga(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def fecha_oferta(iso):
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
        return f"{d.day} {MESES[d.month - 1][:3]} {d.year}"
    except ValueError:
        return ""


def url_segura(u):
    u = str(u or "").strip()
    return u if re.match(r"^https?://", u, re.I) else ""


E = lambda s: html.escape(str(s if s is not None else ""), quote=True)  # noqa: E731


def tarjeta(o, i, iconos, categorias):
    cat = o.get("categoria") if o.get("categoria") in iconos else categorias[0]
    d = dto(o)
    if d:
        fondo = f'<span class="grande">-{d}%<small>de descuento</small></span>'
    else:
        fondo = ('<svg class="icono-cat" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="5" '
                 f'stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">{iconos.get(cat, "")}</svg>')
    fondo += f'<img class="mascota" src="/assets/web/{POSES[i % len(POSES)]}.webp" alt="" loading="lazy">'
    chapa = f'<span class="chapa"><span class="numero">Nº {E(o["numero"])}</span></span>'
    precios = f'<div class="precios"><span class="precio">{euros(o.get("precio"))}</span>'
    if o.get("antes"):
        precios += f'<span class="antes"><span class="oculto">Antes </span>{euros(o["antes"])}</span>'
    if d:
        precios += f'<span class="descuento">-{d} %</span>'
    precios += "</div>"
    ahorro = (o["antes"] - o["precio"]) if d else 0
    if ahorro >= 1:
        precios += f'<p class="ahorro">Te ahorras {euros(ahorro)}</p>'
    fo = fecha_oferta(o.get("fecha"))
    nota = f'<p class="nota">Precio a {fo}. Puede cambiar.</p>' if fo else ""
    enlace = url_segura(o.get("enlace"))
    boton = (f'<a class="boton" href="{E(enlace)}" target="_blank" rel="sponsored nofollow noopener">Ver en Amazon'
             '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7"/><path d="M8 7h9v9"/></svg></a>'
             if enlace else '<span class="boton pendiente">Enlace pendiente</span>')
    ficha = f'/#oferta-{E(o["numero"])}'
    return (f'<article class="tarjeta"><a class="cartel {E(cat)}" href="{ficha}" tabindex="-1" aria-hidden="true">'
            f'{fondo}{chapa}</a><div class="cuerpo"><span class="categoria">{E(o.get("categoria"))}</span>'
            f'<h3><a href="{ficha}">{E(o.get("producto"))}</a></h3>{precios}{nota}{boton}</div></article>')


CSS_EXTRA = """
/* ---------- Páginas de categoría (generadas por _herramientas/paginas.py) ---------- */
.menu-texto a{white-space:nowrap;padding:0 8px;font-size:14px}
@media (max-width:360px){.logo{font-size:20px}.logo svg{width:30px;height:30px}}
.migas{font-size:13.5px;color:#C9D3CE;margin:0 0 10px}
.migas a{color:var(--menta);text-decoration:none;font-weight:700}
.cabeza-cat{background:var(--verde);color:var(--crema);padding:22px 0 26px;position:relative;overflow:hidden;isolation:isolate}
.cabeza-cat::before{content:"";position:absolute;right:-120px;top:-140px;width:420px;height:420px;border-radius:50%;background:radial-gradient(closest-side,rgba(126,226,168,.32),transparent);z-index:-1}
.cabeza-cat h1{margin:0 0 8px;font-weight:900;font-size:clamp(30px,7vw,52px);line-height:1.02;letter-spacing:-0.045em;text-wrap:balance;max-width:20ch}
.cabeza-cat p{margin:0;color:#D6E2DB;max-width:60ch}
.cabeza-cat .actualizado{margin-top:10px;font-size:13px;color:var(--menta);font-weight:700}
.cabeza-cat.bf{background:#0B0F0D}
.cabeza-cat.bf::before{background:radial-gradient(closest-side,rgba(255,90,60,.35),transparent)}
.cabeza-cat.bf h1 em{font-style:normal;color:var(--coral)}
.enlaces-cat{display:flex;flex-wrap:nowrap;gap:8px;overflow-x:auto;scrollbar-width:none;padding:14px 2px 6px}
.enlaces-cat::-webkit-scrollbar{display:none}
.enlaces-cat a{flex:0 0 auto;display:inline-flex;align-items:center;min-height:42px;padding:0 15px;border-radius:999px;border:1.5px solid var(--linea);background:var(--blanco);color:var(--tinta);font-weight:700;font-size:14.5px;text-decoration:none}
.enlaces-cat a[aria-current="page"]{background:var(--verde);border-color:var(--verde);color:var(--crema)}
.lista-cat{padding:16px 0 10px}
.mas-info{background:var(--crema);border:1px solid var(--linea);border-radius:20px;padding:18px 20px;margin:16px 0 34px;color:var(--gris);font-size:15px}
.mas-info h2{margin:0 0 6px;font-size:18px;color:var(--tinta);letter-spacing:-0.02em}
.mas-info p{margin:0 0 8px}
.ir-especial{display:inline-flex;margin:4px 0 0;min-height:48px;align-items:center;padding:0 18px;border-radius:14px;background:var(--coral);color:#fff;font-weight:800;text-decoration:none}
.indice-cat{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:18px 0 34px}
@media (min-width:760px){.indice-cat{grid-template-columns:repeat(4,minmax(0,1fr))}}
.indice-cat a{display:flex;flex-direction:column;gap:2px;padding:16px;border-radius:18px;background:var(--blanco);border:1px solid var(--linea);box-shadow:var(--sombra);text-decoration:none;font-weight:800;font-size:17px}
.indice-cat a small{font-weight:600;font-size:13px;color:var(--gris)}
"""

JS_TAG = ('<script>(function(){var T={ig:"chollofinoig-21",fb:"chollofinofb-21",tk:"chollofinotk-21",pin:"chollofinopin-21",tg:"chollofinotg-21"},d="";'
          'try{d=(new URLSearchParams(location.search).get("d")||"").toLowerCase()}catch(e){}'
          'if(!T[d]){var u=navigator.userAgent||"";if(/Instagram/i.test(u))d="ig";else if(/FBAN|FBAV|FB_IAB|FBIOS/i.test(u))d="fb";'
          'else if(/musical_ly|BytedanceWebview|TikTok/i.test(u))d="tk";else if(/Pinterest/i.test(u))d="pin";else if(/Telegram/i.test(u))d="tg"}'
          'if(!T[d])return;document.querySelectorAll(\'a[href*="amazon.es"]\').forEach(function(a){try{var x=new URL(a.href);'
          'x.searchParams.set("tag",T[d]);a.href=x.toString()}catch(e){}})})();</script>')

LOGO = ('<svg width="36" height="36" viewBox="0 0 120 120" aria-hidden="true"><path d="M64 10 H104 A6 6 0 0 1 110 16 V56 L58 108 '
        'A8 8 0 0 1 47 108 L12 73 A8 8 0 0 1 12 62 Z" fill="none" stroke="#F4F1E8" stroke-width="9" stroke-linejoin="round">'
        '</path><circle cx="90" cy="30" r="8" fill="#F4F1E8"></circle><path d="M36 64 L50 78 L76 50" fill="none" '
        'stroke="#7EE2A8" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"></path></svg>')


def pagina(ruta, titulo, descripcion, cabeza, cuerpo, actual=None, enlaces=None, bf=False):
    url = f"{DOMINIO}/{ruta}"
    nav = ""
    if enlaces:
        actual_attr = ' aria-current="page"'
        nav = '<nav class="enlaces-cat" aria-label="Categorías">' + "".join(
            f'<a href="/{r}"{actual_attr if r == actual else ""}>{E(t)}</a>' for r, t in enlaces) + "</nav>"
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{E(titulo)}</title>
<meta name="description" content="{E(descripcion)}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#0F3D2E">
<meta property="og:type" content="website">
<meta property="og:title" content="{E(titulo)}">
<meta property="og:description" content="{E(descripcion)}">
<meta property="og:image" content="{DOMINIO}/assets/web/compartir.jpg">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/web/icono.png">
<link rel="apple-touch-icon" href="/assets/web/icono.png">
<link rel="stylesheet" href="/assets/web/estilo.css">
<!-- Contador de visitas de Metricool (sin cookies) -->
{TRACKER}
</head>
<body>
<header class="cabecera">
  <div class="wrap">
    <a class="logo" href="/" aria-label="Chollo Fino, ir al inicio">{LOGO}<span>chollo <span class="fino">fino</span></span></a>
    <nav class="menu menu-texto" aria-label="Menú"><a href="/">Chollos</a><a href="/black-friday/">Black Friday</a></nav>
  </div>
</header>
<div class="aviso-afiliado"><div class="wrap"><p>En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los requisitos aplicables.</p></div></div>
<main>
  <div class="cabeza-cat{' bf' if bf else ''}"><div class="wrap">{cabeza}</div></div>
  <div class="wrap">{nav}{cuerpo}</div>
</main>
<footer class="pie">
  <div class="wrap">
    <span class="logo"><span>chollo <span class="fino" style="color:#7EE2A8">fino</span></span></span>
    <p><strong>Enlaces de afiliado.</strong> En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los requisitos aplicables. Para ti el precio es el mismo.</p>
    <p>Precio y disponibilidad a la fecha indicada en cada oferta; pueden cambiar. Se aplicará el precio que figure en Amazon en el momento de la compra.</p>
    <p>Amazon y el logotipo de Amazon son marcas comerciales de Amazon.com, Inc. o de sus filiales.</p>
    <p>Titular: Adrián Méndez · NIF: 42264958C · Contacto: <a href="mailto:chollofino7@gmail.com">chollofino7@gmail.com</a></p>
    <nav class="legal" aria-label="Textos legales"><a href="/aviso-legal.html#aviso">Aviso legal</a><a href="/aviso-legal.html#privacidad">Privacidad</a><a href="/aviso-legal.html#cookies">Cookies</a></nav>
    <p>© {datetime.date.today().year} Chollo Fino</p>
  </div>
</footer>
{JS_TAG}
</body>
</html>
"""


def rejilla(lista, iconos, categorias, vacio):
    if not lista:
        return (f'<div class="rejilla lista-cat"><div class="vacio"><img src="/assets/web/fino-6-piensa.webp" alt="" width="211" '
                f'height="400"><strong>{E(vacio)}</strong><span>Fino busca ofertas nuevas cada mañana.</span>'
                '<a class="boton" href="/">Ver todos los chollos de hoy</a></div></div>')
    return '<div class="rejilla lista-cat">' + "".join(tarjeta(o, i, iconos, categorias) for i, o in enumerate(lista)) + "</div>"


def main():
    index = (RAIZ / "index.html").read_text(encoding="utf-8")
    datos = leer_datos(index)
    categorias, iconos = datos["CONFIG"]["categorias"], datos["ICONOS"]
    ofertas = [o for o in datos["OFERTAS"] if not o.get("ejemplo") and o.get("producto")]
    ofertas.sort(key=lambda o: -(o.get("numero") or 0))
    hoy = datetime.datetime.now(ZoneInfo("Atlantic/Canary")).date()
    actualizado = f'<p class="actualizado">Actualizado el {fecha_larga(hoy)} · {{n}}</p>'

    # Estilos: los mismos de index.html, con rutas absolutas, más los de estas páginas
    css = re.search(r"<style>([\s\S]*?)</style>", index).group(1).replace("url(assets/", "url(/assets/")
    (RAIZ / "assets/web/estilo.css").write_text(css.strip() + "\n" + CSS_EXTRA, encoding="utf-8")

    def cuantas(n):
        return "1 chollo" if n == 1 else f"{n} chollos"

    enlaces = [(f"ofertas/{slug(c)}/", c) for c in categorias] + [
        ("ofertas/menos-de-10-euros/", "Menos de 10 €"), ("ofertas/menos-de-20-euros/", "Menos de 20 €"),
        ("black-friday/", "Black Friday")]
    paginas = []

    def escribir(ruta, contenido):
        destino = RAIZ / ruta / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        paginas.append(ruta)

    texto_fino = ('<section class="mas-info"><h2>Cómo elige Fino los chollos</h2><p>Cada mañana se revisan ofertas de Amazon.es '
                  'publicadas por medios de ofertas españoles. Solo entran productos útiles, de marcas conocidas o bien '
                  'valorados y con un descuento real. El precio es el de la fecha de cada oferta y puede cambiar: el que '
                  'vale es el que veas en Amazon al pagar.</p><p>¿Vienes de un vídeo? Busca el número en '
                  '<a href="/">chollofino.com</a>.</p></section>')

    for c in categorias:
        lista = [o for o in ofertas if o.get("categoria") == c]
        h1, intro = TEXTOS.get(c, (f"Chollos de {c.lower()} en Amazon", "Ofertas con descuento real, revisadas a mano."))
        cabeza = (f'<p class="migas"><a href="/">Inicio</a> › <a href="/ofertas/">Chollos</a> › {E(c)}</p><h1>{E(h1)}</h1>'
                  f'<p>{E(intro)} Fino revisa a mano las ofertas de Amazon.es cada día y solo deja las que merecen la pena.</p>'
                  + actualizado.format(n=cuantas(len(lista))))
        ruta = f"ofertas/{slug(c)}/"
        escribir(ruta, pagina(ruta, f"{h1} hoy · Chollo Fino", f"{intro} Revisados a mano cada día en Chollo Fino.",
                              cabeza, rejilla(lista, iconos, categorias, f"Hoy no hay chollos de {c.lower()}.") + texto_fino,
                              ruta, enlaces))

    for tope in (10, 20):
        lista = sorted([o for o in ofertas if o.get("precio") is not None and o["precio"] < tope],
                       key=lambda o: (o["precio"], -dto(o)))
        h1 = f"Chollos de Amazon por menos de {tope} €"
        intro = (f"Cosas útiles por menos de {tope} €: accesorios, regalos pequeños, cocina, belleza y caprichos con "
                 "descuento real.")
        cabeza = (f'<p class="migas"><a href="/">Inicio</a> › <a href="/ofertas/">Chollos</a> › Menos de {tope} €</p>'
                  f'<h1>{E(h1)}</h1><p>{E(intro)} Ordenados del más barato al más caro.</p>'
                  + actualizado.format(n=cuantas(len(lista))))
        ruta = f"ofertas/menos-de-{tope}-euros/"
        escribir(ruta, pagina(ruta, f"{h1} · Chollo Fino", intro, cabeza,
                              rejilla(lista, iconos, categorias, f"Hoy no hay chollos de menos de {tope} €.") + texto_fino,
                              ruta, enlaces))

    # Black Friday: lo mejor de cada categoría y los mayores descuentos
    mejor = lambda o: (-dto(o), -(o.get("numero") or 0))  # noqa: E731
    por_cat = [sorted([o for o in ofertas if o.get("categoria") == c], key=mejor)[0]
               for c in categorias if any(o.get("categoria") == c for o in ofertas)]
    resto = sorted([o for o in ofertas if o not in por_cat and dto(o) > 0], key=mejor)[:8]
    cabeza = ('<p class="migas"><a href="/">Inicio</a> › Black Friday</p><span class="bf-sello">Black Friday 2026</span>'
              '<h1>Lo mejor del <em>Black Friday</em> en Amazon</h1><p>La Semana de Black Friday de Amazon va del jueves 19 '
              'al lunes 30 de noviembre de 2026 (Black Friday, el viernes 27; Cyber Monday, el lunes 30). Aquí tienes lo '
              'mejor de cada categoría, revisado a mano.</p>' + actualizado.format(n=cuantas(len(por_cat) + len(resto)))
              + '<p><a class="ir-especial" href="/#black-friday">Ver la cuenta atrás y el especial</a></p>')
    cuerpo = ('<div class="titulo-seccion" style="margin-top:22px"><div><h2>Lo mejor de cada categoría</h2></div></div>'
              + rejilla(por_cat, iconos, categorias, "Todavía no hay chollos.")
              + ('<div class="titulo-seccion"><div><h2>Los mayores descuentos</h2></div></div>'
                 + rejilla(resto, iconos, categorias, "") if resto else "") + texto_fino)
    escribir("black-friday/", pagina("black-friday/", "Black Friday 2026 en Amazon: los mejores chollos · Chollo Fino",
                                     "Lo mejor de la Semana de Black Friday de Amazon (19 al 30 de noviembre de 2026), "
                                     "categoría por categoría, revisado a mano.", cabeza, cuerpo, "black-friday/",
                                     enlaces, bf=True))

    # Índice de categorías
    tarjetas = "".join(
        f'<a href="/{r}">{E(t)}<small>{cuantas(n)}</small></a>' for (r, t), n in zip(
            enlaces, [sum(o.get("categoria") == c for o in ofertas) for c in categorias]
            + [sum((o.get("precio") or 1e9) < 10 for o in ofertas), sum((o.get("precio") or 1e9) < 20 for o in ofertas),
               len(por_cat) + len(resto)]))
    cabeza = ('<p class="migas"><a href="/">Inicio</a> › Chollos</p><h1>Chollos de Amazon por categoría</h1>'
              '<p>Tecnología, hogar, cocina, belleza, deporte, juguetes, moda y regalos con descuento real, revisados a mano '
              'cada día.</p>' + actualizado.format(n=cuantas(len(ofertas))))
    escribir("ofertas/", pagina("ofertas/", "Chollos de Amazon por categoría · Chollo Fino",
                                "Todas las categorías de Chollo Fino: chollos de Amazon con descuento real, revisados a mano.",
                                cabeza, f'<div class="indice-cat">{tarjetas}</div>' + texto_fino))

    # Mapa de la web y robots.txt
    urls = [""] + paginas + ["aviso-legal.html"]
    mapa = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        mapa.append(f"  <url><loc>{DOMINIO}/{u}</loc><lastmod>{hoy.isoformat()}</lastmod></url>")
    mapa.append("</urlset>")
    (RAIZ / "sitemap.xml").write_text("\n".join(mapa) + "\n", encoding="utf-8")
    (RAIZ / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {DOMINIO}/sitemap.xml\n", encoding="utf-8")
    print(f"{len(paginas)} páginas, {len(ofertas)} ofertas · sitemap.xml y robots.txt")


if __name__ == "__main__":
    main()
