# Prompt propuesto

## System

You are a concise market analyst monitoring Chilean auto-insurance prices. Write in professional Latin American Spanish for a Chilean business audience. Use clear, plain language with an executive tone. Avoid bullet lists and headings in the output. Use flowing prose only. Be specific about what changed on the target date versus the prior 7-day context. Do not invent facts beyond the KPI inputs.

## User

Here are the KPI snapshots for {date} from a Chilean auto-insurance price monitor.
The data covers two portals (Falabella, Santander) and roughly 10 insurers.

{kpi_json}

Write a 3 to 5 sentence daily market summary in Spanish for a Chilean professional customer. Focus on:
- floor price movements by portal
- which insurer appears to be leading on recent 7-day win rate
- any unusual volatility or instability
- the overall market direction

Keep the tone neutral, analytical, and commercially useful. Prefer concrete comparisons to the previous week. If the signals are mixed, say so plainly. Do not use bullets, titles, or markdown lists in the output.

# Demo briefings

## 2025-08-24

En la última semana, el mercado de seguros automotrices en Chile se mantuvo relativamente estable, aunque Falabella volvió a mostrar una baja en su piso diario, mientras Santander siguió casi plano. En términos competitivos, Cardif continuó liderando con claridad en Falabella en la ventana de 7 días, mientras Sura sostuvo un dominio prácticamente total en Santander. La principal señal de riesgo sigue viniendo por volatilidad y dispersión de precios: Fid y Sura se mantienen entre las aseguradoras más inestables, especialmente en Falabella. En conjunto, el cierre del día sugiere un mercado sin quiebres estructurales, pero con presión competitiva todavía concentrada en pocos jugadores.

## 2025-08-25

El 25 de agosto mostró un rebote del piso en Falabella, después de la caída observada el día anterior, mientras Santander permaneció prácticamente sin cambios y siguió entregando una señal de continuidad. Aun con ese ajuste, el liderazgo competitivo no cambió: Cardif siguió encabezando Falabella en win rate de 7 días y Sura mantuvo una posición dominante en Santander. La lectura de volatilidad sigue siendo exigente en Falabella, donde Fid, Sura y Hdi exhibieron mayor variación intradiaria que el resto del mercado. Para un cliente profesional, la señal es de mercado todavía ordenado a nivel agregado, pero con mayor sensibilidad táctica en Falabella que en Santander.

## 2025-08-26

La jornada del 26 de agosto destacó por una caída relevante del piso diario en Falabella, lo que sugiere una intensificación competitiva en ese portal, mientras Santander continuó operando sin un cambio material en su nivel base. Pese a ese movimiento, la estructura de liderazgo se mantuvo estable: Cardif siguió al frente en Falabella y Sura conservó un dominio total en Santander al mirar la ventana de 7 días. La volatilidad sigue concentrada en algunos actores, especialmente Fid y Sura en Falabella, con Zurich también mostrando mayor dispersión de precios en esta fecha. El mercado, por tanto, se ve mixto: más agresivo en Falabella, pero todavía muy controlado y predecible en Santander.

## 2025-08-27

El 27 de agosto mostró un repunte del piso tanto en Falabella como, con mayor fuerza, en Santander, lo que apunta a una pausa en la presión bajista observada días antes. Aun así, el liderazgo competitivo siguió altamente concentrado: Cardif mantuvo la delantera en Falabella y Sura continuó capturando prácticamente todo el win rate en Santander. En volatilidad, Falabella volvió a exhibir un patrón más movedizo, con Fid, Sura y Consorcio entre los nombres con mayor dispersión intradiaria, mientras en Santander la principal anomalía volvió a ser Fid. La señal para negocio es de recuperación de precios mínimos en ambos portales, pero sin cambio todavía en los incumbentes que están marcando el piso efectivo del mercado.

## 2025-08-28

Durante el 28 de agosto, los pisos diarios corrigieron levemente a la baja tanto en Falabella como en Santander, aunque sin configurar un evento de mercado significativo. El cuadro competitivo siguió siendo muy estable: Cardif fortaleció su liderazgo reciente en Falabella y Sura continuó prácticamente sin presión en Santander. La mayor atención sigue estando en la dispersión de precios, donde Fid continúa destacando como el actor más volátil en ambos portales, mientras Zurich y Sura mantienen variabilidad elevada en Falabella. En síntesis, el mercado muestra una corrección menor en precios mínimos, pero no un cambio de régimen competitivo.

## 2025-08-29

El 29 de agosto cerró con pisos diarios casi planos en ambos portales, lo que refuerza una lectura de estabilización después de varios movimientos en la semana. En esa base más estable, Cardif amplió con fuerza su ventaja en Falabella dentro de la métrica de win rate de 7 días, mientras Sura siguió liderando de forma total en Santander. La volatilidad diaria continuó concentrándose en un grupo acotado, particularmente Fid y Sura en Falabella, sin que Santander mostrara un deterioro comparable fuera del comportamiento habitual de Fid. Para un cliente chileno del sector, la conclusión es clara: hoy el mercado se ve estable en nivel, pero con una competencia muy asimétrica entre portales.

## 2025-08-30

El 30 de agosto mostró un nuevo aumento del piso diario en Falabella y una variación acotada al alza en Santander, cerrando la semana con una señal algo más firme en precios mínimos. A pesar de ese repunte, no hubo cambio en el mapa competitivo: Cardif siguió siendo el claro referente en Falabella y Sura mantuvo una supremacía prácticamente total en Santander al observar la ventana de 7 días. La volatilidad estructural continúa concentrada en Falabella, especialmente en Fid y Sura, mientras Santander se mantiene comparativamente más ordenado salvo por la persistente dispersión de Fid. En conjunto, el cierre semanal sugiere un mercado más estable en Santander y todavía más táctico, sensible y disputado en Falabella.
