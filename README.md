# Gato teclista 🐈‍⬛⌨️

Un gato negro programador que vive en tu escritorio de Windows: teclea cuando tú
tecleas, mueve el mouse cuando tú lo mueves y abre la boca cuando hablas.

## Qué hace

- **Teclado 75%**: pulsa la misma tecla que tú, en su sitio. Reconoce las teclas
  por posición física, así que funciona con teclados en español (la Ñ incluida).
  El teclado está girado hacia el gato, porque te mira de frente.
- **Dos patas**: escribe con las dos; cuando usas el mouse, una pata se va al
  mouse y la otra escribe todo. Tras 2 s sin mouse vuelven las dos al teclado.
- **Mouse en espejo**: sigue tu cursor, y en juegos que bloquean el cursor usa
  el movimiento físico del mouse (Raw Input).
- **Micrófono (opcional)**: mueve la boca y enseña los colmillos cuando hablas.
  Solo mide el volumen en tu PC; no graba ni envía nada.
- Audífonos, taza de café con vapor, ojos que siguen el cursor y parpadeo.
- Siempre encima de las ventanas (también de juegos en modo *ventana sin bordes*).

## Cómo usarlo

Necesitas Windows y [Python 3](https://www.python.org/) (con tkinter, que viene
incluido). No hace falta instalar nada más.

- Doble clic en **`Iniciar gato.bat`** (o en `gato.pyw`).
- **Arrastrar** con clic izquierdo: moverlo de sitio.
- **Rueda del mouse** sobre el gato: más grande o más pequeño.
- **Clic derecho**: tamaño, activar/desactivar micrófono y Salir.

El tamaño, la posición y el micrófono se guardan en `gato_config.json`.
