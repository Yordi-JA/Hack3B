> **RETO 1 · EXPEDIENTES**

# SISTEMA MULTIAGENTE PARA ANÁLISIS INTELIGENTE DE DOCUMENTOS

Construye un sistema multiagente con LangChain que revise el expediente legal de un inmueble, detecte lo que falta o no cuadra y emita una recomendación sustentada en evidencia.

| DOMINIO | INSUMO | SALIDA | STACK OBLIGATORIO |
| :--- | :--- | :--- | :--- |
| Documentación legal y administrativa de inmuebles | Expediente con 4 tipos documentales mínimos | Análisis del expediente con recomendación y evidencia | Arquitectura multiagente sobre LangChain |

---

## 01 EL PROBLEMA

Uno de los principales retos para el crecimiento de Tiendas 3B es identificar y habilitar locales comerciales e industriales que cumplan los requisitos para operar como nuevas tiendas o centros de distribución.

De cada inmueble se recibe y revisa documentación legal y administrativa. Hoy buena parte de esa revisión es manual: leer documentos, localizar información relevante, validar requisitos e identificar problemas antes de decidir si un expediente continúa. Ese tiempo es de personal especializado y limita cuántos expedientes se pueden procesar.

El reto es usar IA generativa y una arquitectura multiagente para automatizar la revisión inicial, de modo que los especialistas concentren su tiempo en los casos que realmente lo requieren.

---

## 02 QUÉ RECIBE TU SOLUCIÓN

Expedientes de inmuebles que incluyen, como mínimo, estos cuatro tipos documentales, y una guía por tipo con la información que debe localizarse y las reglas que deben evaluarse. Los criterios y reglas definitivos se entregan como parte de la información del reto.

### Escrituras
* Identificación del propietario o titular
* Dirección e identificación del inmueble
* Superficie del terreno
* Datos relevantes del inmueble
* Información que lo relaciona con el resto del expediente

### Predial
* Propietario o contribuyente
* Dirección del inmueble
* Cuenta o clave predial
* Superficie registrada
* Información que lo relaciona con los demás documentos

### Alineamiento y Número Oficial
* Dirección oficial del inmueble
* Número oficial asignado
* Identificación del predio
* Alineamiento determinado por la autoridad
* Fecha de emisión y vigencia, cuando corresponda
* Autoridad emisora

### Uso de Suelo
* Dirección e identificación del inmueble
* Uso de suelo autorizado
* Compatibilidad con el uso comercial requerido
* Restricciones o condicionantes
* Superficie aplicable
* Fecha de emisión y vigencia, cuando corresponda
* Autoridad emisora

---

## 03 QUÉ DEBE HACER TU SOLUCIÓN

Demuestra cómo distintos agentes especializados colaboran para:

* Identificar y clasificar automáticamente el tipo de documento recibido.
* Extraer la información relevante definida para cada tipo documental.
* Validar la información contra los criterios y reglas proporcionados.
* Detectar documentos incompletos, inconsistencias, riesgos o información faltante.
* Realizar validaciones cruzadas entre documentos del mismo inmueble: dirección, propietario, superficie, identificación del predio y otros datos relevantes.
* Anotar los hallazgos indicando qué información o evidencia dentro del documento sustenta cada observación.
* Generar una recomendación inicial: Cumple, Requiere revisión o No cumple.
* Explicar con claridad las razones de la recomendación para facilitar la revisión del equipo legal.

**Ejemplo:** ante un documento de Uso de Suelo, el sistema debe determinar si autoriza el uso comercial requerido, identificar condicionantes o restricciones y señalar la evidencia que sustenta esa conclusión.

### VALIDACIONES CRUZADAS

El análisis no se limita a revisar cada documento por separado: hay que relacionar el expediente completo y detectar inconsistencias como

* Diferencias en la dirección del inmueble.
* Diferencias en propietario o titular.
* Diferencias relevantes en superficies.
* Diferencias en número oficial.
* Información de identificación del predio que no coincide.
* Documentos que posiblemente correspondan a inmuebles diferentes.
* Documentos faltantes o que requieran revisión adicional.

> Cuando encuentres una discrepancia, muestra **qué documentos** la presentan, **qué información** encontraste en cada uno y **dónde está la evidencia.**

---

## 04 QUÉ ENTREGAS

Un prototipo funcional que permita ingresar un expediente, ejecutar automáticamente su análisis y presentar al usuario:

* Documentos recibidos y documentos faltantes.
* Datos relevantes extraídos.
* Criterios y validaciones realizadas.
* Inconsistencias detectadas entre documentos.
* Requisitos cumplidos y no cumplidos.
* Evidencia que sustenta cada hallazgo.
* Nivel de confianza del análisis.
* Recomendación inicial: `Cumple` · `Requiere revisión` · `No cumple`.

Además, cada equipo presenta un **pitch de 3 minutos** ante el jurado, que cuenta como criterio de evaluación.

---

## 06 REGLAS Y RESTRICCIONES

* La solución debe apoyarse en una arquitectura multiagente construida con LangChain.
* Las conclusiones deben ser trazables y estar sustentadas en evidencia proveniente de los documentos originales.
* Los documentos del reto se usan solo dentro del reto: no se suben a otros servicios ni se comparten fuera del equipo.
* Los criterios y reglas definitivos por tipo documental se entregan junto con los datos del reto.