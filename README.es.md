# Fusion Local Backup

*[Read in English](README.md)*

Script para Autodesk Fusion que guarda una copia local de tus diseños: los saca de la nube a tu disco en F3D/F3Z y STEP.

## Qué hace

- **Formatos:** archivo de Fusion (F3D, o F3Z si el diseño tiene referencias externas) y STEP.
- **Alcance:** marca los proyectos que quieres copiar, o todos los proyectos del hub activo. El script recuerda tu selección, así que la siguiente copia es abrir y Aceptar.
- **Estructura:** reproduce en disco `Hub / Proyecto / Carpetas / Diseño`.
- **Registro:** al terminar guarda un `export_log_FECHA.csv` con el resultado de cada fichero y la duración total.
- **Incremental:** un índice en la carpeta de destino (`fusion-local-backup.json`) anota qué versión de cada diseño se exportó, por formato. Las siguientes ejecuciones solo abren y exportan los diseños nuevos o modificados, así que usa siempre la misma carpeta de destino. En disco solo se conserva la última versión.
- **Renombrados y movidos:** los diseños se siguen por su id de Fusion, así que si renombras o mueves uno en Fusion sus ficheros locales se mueven en vez de duplicarse.
- **No se borra nada:** un diseño eliminado en Fusion aparece en el registro como "no está en la nube" y su copia local se conserva.
- **Referencias desactualizadas:** cuando un ensamblaje usa una versión antigua de una pieza enlazada, el registro indica cuál.
- **F3Z en segundo plano:** Autodesk empaqueta cada F3Z en la nube y tarda decenas de segundos. El script lo pide, sigue con el siguiente diseño y coloca cada F3Z cuando llega, con un máximo de 5 peticiones en curso.
- **Escritura segura:** cada fichero se exporta a una carpeta temporal y se mueve al terminar, de modo que una ejecución interrumpida nunca deja un fichero a medias en su sitio.
- **Idioma:** la interfaz sale en español si Fusion está en español, y en inglés en cualquier otro caso.

## Instalación

1. Descarga este repositorio (Code > Download ZIP) y descomprímelo.
2. En Fusion: **UTILIDADES > Complementos > Scripts y complementos**.
3. Pulsa **+** y elige "Script o complemento desde el dispositivo".
4. Selecciona la carpeta `FusionLocalBackup` (la que contiene `FusionLocalBackup.py`).

## Uso

1. Ejecuta el script desde la lista de scripts.
2. En "Selecciona los proyectos", marca los que quieres copiar, o marca "Todos los proyectos del hub".
3. Marca los formatos y la carpeta de destino. El script recuerda la última carpeta usada.
4. Pulsa Aceptar y deja Fusion trabajar. Primero rastrea los proyectos, mostrando cuántos ficheros lleva encontrados, y después abre, exporta y cierra cada diseño que lo necesite. Al final espera a los F3Z que aún estén en camino.
5. Para mantener la copia al día, vuelve a ejecutarlo con la misma carpeta de destino: solo exporta lo nuevo y lo modificado.

La casilla "Exportar de nuevo aunque esté al día" fuerza a regenerar todo lo seleccionado. Puedes cancelar en cualquier momento: lo ya exportado queda anotado y la siguiente ejecución continúa desde ahí.

## Cuánto tarda

Datos orientativos, medidos en un equipo y una conexión concretos:

- **Primera copia de un proyecto:** hay que abrir cada diseño una vez. Un proyecto de 177 ficheros (169 diseños, 106 MB) tardó 20 minutos, unos 7 segundos por diseño. Un proyecto de más de mil ficheros es cosa de un par de horas; conviene dejarlo trabajando solo.
- **Copias siguientes:** solo se rastrean los proyectos y se abren los diseños modificados. El mismo proyecto de 177 ficheros, sin cambios, se revisa en menos de un minuto.

## Limitaciones conocidas

- Fusion queda ocupado mientras dura el proceso.
- Solo se exportan diseños 3D (`.f3d`). Planos, electrónica y otros ficheros se omiten y quedan anotados en el registro.
- "Todos los proyectos" significa todos los del hub activo. Para otro hub, cámbialo en el panel de datos y vuelve a ejecutar.
- **F3Z usa un comando no documentado.** La API pública de Fusion no exporta F3Z; el script usa el comando de texto `data.fileExport`. Funciona (el F3Z resultante se ha reimportado en Fusion con los vínculos correctos), pero puede dejar de hacerlo con una actualización. Si falla, el error queda en el registro y el STEP se exporta igualmente.
- **Cada F3Z genera un correo de Autodesk.** El F3Z se empaqueta en la nube de Autodesk, que envía un correo "is ready to be downloaded" por cada uno. No hace falta usar ese enlace: el fichero ya queda guardado en la carpeta de destino. Los F3D y STEP no envían ningún correo. Si tienes muchos ensamblajes, crea un filtro en tu correo para esos mensajes.
- **Los ensamblajes duplican contenido.** Al exportar un proyecto con ensamblajes obtienes el F3D de cada pieza enlazada y, además, el F3Z del ensamblaje, que ya lleva esas mismas piezas dentro. Es normal: así cada diseño queda disponible por separado y el ensamblaje queda completo en un solo fichero.
- **Los ensamblajes se guardan tal como están.** Un F3Z lleva la versión de cada pieza enlazada que el ensamblaje tiene fijada, no la última. Se vuelve a exportar cuando el propio ensamblaje tiene una versión nueva, es decir, después de abrirlo, aceptar la actualización y guardar.
- Usa siempre la misma carpeta de destino. Si eliges otra, o una carpeta sin el fichero de índice, se hace una copia completa nueva.
- En STEP solo se incluyen los cuerpos visibles.

## Hoja de ruta

- Otros tipos de fichero (planos, electrónica, etc.).

## Licencia

MIT. Consulta el fichero `LICENSE`.
