# Fusion Local Backup

*[Read in English](README.md)*

Script para Autodesk Fusion que guarda una copia local de tus diseños: los saca de la nube a tu disco en F3D/F3Z y STEP.

## Qué hace (fase 1)

- **Formatos:** archivo de Fusion (F3D, o F3Z si el diseño tiene referencias externas) y STEP.
- **Alcance:** un grupo de ficheros de un proyecto, un proyecto entero o todos los proyectos del hub activo.
- **Estructura:** reproduce en disco `Hub / Proyecto / Carpetas / Diseño`.
- **Registro:** al terminar guarda un `export_log_FECHA.csv` con el resultado de cada fichero.
- **Reanudar:** la opción "Omitir los que ya existen en disco" permite continuar una exportación interrumpida.
- **Idioma:** la interfaz sale en español si Fusion está en español, y en inglés en cualquier otro caso.

## Instalación

1. Descarga este repositorio (Code > Download ZIP) y descomprímelo.
2. En Fusion: **UTILIDADES > Complementos > Scripts y complementos**.
3. Pulsa **+** y elige "Script o complemento desde el dispositivo".
4. Selecciona la carpeta `FusionLocalBackup` (la que contiene `FusionLocalBackup.py`).

## Uso

1. Ejecuta el script desde la lista de scripts.
2. Elige qué exportar: ficheros seleccionados, un proyecto o todo.
3. Marca los formatos y la carpeta de destino.
4. Pulsa Aceptar y deja Fusion trabajar. Abre cada diseño, lo exporta y lo cierra.

## Limitaciones conocidas

- Fusion queda ocupado mientras dura el proceso.
- Solo se exportan diseños 3D (`.f3d`). Planos, electrónica y otros ficheros se omiten y quedan anotados en el registro.
- "Todo" significa todos los proyectos del hub activo. Para otro hub, cámbialo en el panel de datos y vuelve a ejecutar.
- **F3Z usa un comando no documentado.** La API pública de Fusion no exporta F3Z; el script usa el comando de texto `data.fileExport`. Funciona (el F3Z resultante se ha reimportado en Fusion con los vínculos correctos), pero puede dejar de hacerlo con una actualización. Si falla, el error queda en el registro y el STEP se exporta igualmente.
- **Cada F3Z genera un correo de Autodesk.** El F3Z se empaqueta en la nube de Autodesk, que envía un correo "is ready to be downloaded" por cada uno. No hace falta usar ese enlace: el fichero ya queda guardado en la carpeta de destino. Los F3D y STEP no envían ningún correo.
- **Los ensamblajes duplican contenido.** Al exportar un proyecto con ensamblajes obtienes el F3D de cada pieza enlazada y, además, el F3Z del ensamblaje, que ya lleva esas mismas piezas dentro. Es normal: así cada diseño queda disponible por separado y el ensamblaje queda completo en un solo fichero.
- La opción de omitir existentes solo comprueba que haya un fichero con ese nombre. No detecta diseños modificados desde la última exportación.
- En STEP solo se incluyen los cuerpos visibles.

## Hoja de ruta

- Fase 2: exportación incremental (solo lo que ha cambiado desde la última vez, según el número de versión).
- Más adelante: otros tipos de fichero (planos, electrónica, etc.).

## Licencia

MIT. Consulta el fichero `LICENSE`.
