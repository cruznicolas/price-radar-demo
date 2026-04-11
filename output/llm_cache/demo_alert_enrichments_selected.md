# Prompt propuesto

## System

You are a concise market analyst monitoring Chilean auto-insurance prices. Write one short paragraph in professional Latin American Spanish for a Chilean business audience. Use a neutral, analytical, commercially useful tone. Keep the output to 2 to 4 sentences. Do not use bullets, headings, or markdown lists. Do not invent facts beyond the alert and KPI inputs.

## User

A price alert has fired for the Chilean auto-insurance market.

Alert details:
{alert_json}

7-day KPI context for {insurer} on portal {portal}:
{kpi_json}

Based on the 7-day context, write a 2 to 4 sentence paragraph in Spanish for a Chilean professional customer that explains:
1. Whether this event fits {insurer}'s prior pricing behaviour on {portal}.
2. The most likely explanation, such as catch-up after a stable period, market-wide move, tactical repricing, or outlier.
3. What metric or follow-up signal to watch next.

Be specific and concise. Do not repeat the alert numbers verbatim. Add interpretation, not just description.

# Demo enrichments

## alert_2.txt

En los siete días previos, Bci venía operando con un precio muy estable en Falabella y sin protagonismo competitivo, por lo que este salto luce más como un repricing puntual que como un cambio estructural de posicionamiento. El hecho de que el mismo día aparezca una amplitud inusualmente grande entre mínimo y máximo refuerza la lectura de un ajuste transitorio o una anomalía intradiaria. La señal a monitorear ahora es si el nivel alto se sostiene en las próximas corridas o si revierte rápidamente hacia su rango habitual.

## alert_13.txt

En Falabella, Fid ya venía mostrando una volatilidad superior al promedio durante la semana, por lo que esta caída se entiende mejor como una reversión fuerte después de un tramo de precios inflados que como un cambio aislado sin antecedentes. La dispersión observada el 25 de agosto sugiere un patrón de repricing agresivo dentro del mismo día más que una tendencia estable de mediano plazo. Conviene seguir si el precio logra sostenerse cerca del nuevo piso o si vuelve a rebotar rápidamente hacia la parte alta de su rango reciente.

## alert_31.txt

Zurich venía con una trayectoria muy estable en Falabella durante los días previos, con baja dispersión y sin liderazgo en win rate, por lo que este salto aparece fuera de su comportamiento reciente. Más que una mejora competitiva sostenible, el movimiento se parece a un outlier operativo o a un ajuste táctico de corta duración. Lo clave ahora es verificar si Zurich consolida un nuevo nivel en las siguientes corridas o si corrige rápidamente y vuelve a su rango previo.

## alert_38.txt

Esta caída rompe un patrón de alta estabilidad en Santander: Sura venía con dispersión casi nula y dominando completamente la tasa de victoria de 7 días, por lo que el movimiento sugiere una decisión competitiva deliberada más que ruido operativo. Dado su peso en el portal, una baja de este tipo probablemente profundiza su liderazgo y presiona el piso de mercado completo, no solo su propio posicionamiento. La métrica crítica a seguir es si el nuevo nivel se sostiene durante las próximas corridas y si arrastra reacciones defensivas del resto de aseguradoras.
