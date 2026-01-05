import sys
import json
import math
import random
import time
import psutil
import os
from collections import defaultdict
import copy

# Parámetros globales del script
BATERIA_MAXIMA = 50
UMBRAL_RECARGA = 30
TEMPERATURA_INICIAL = 1000
TEMPERATURA_FINAL = 0.1
FACTOR_ENFRIAMIENTO = 0.95
ITERACIONES_POR_TEMPERATURA = 100
MAX_ITERACIONES_SIN_MEJORA = 500
tiempo_inicio = time.time()

# Función para obtener el uso actual de memoria en MB
def get_memoria():
    proceso = psutil.Process(os.getpid())
    return proceso.memory_info().rss / 1024 / 1024

# Cargamos el JSON para procesar los datos (vertices, rutas, zonas no-fly, etc)
def cargar_instancia(archivo_json):
    with open(archivo_json, 'r') as f:
        datos = json.load(f)
    
    puntos = {}
    puntos_entrega = []
    puntos_recarga = []
    
    for v in datos['mapa']['vertices']:
        puntos[v['id']] = {
            'tipo': v['tipo'],
            'x': v['x'],
            'y': v['y']
        }
        if v['tipo'] == 'punto_entrega':
            puntos_entrega.append(v['id'])
        elif v['tipo'] == 'punto_recarga':
            puntos_recarga.append(v['id'])
    
    # Construimos un grafo de adyacencia para agilizar los cálculos
    grafo = defaultdict(dict)
    for r in datos['mapa']['rutas']:
        grafo[r['p1']][r['p2']] = r['peso']
        grafo[r['p2']][r['p1']] = r['peso']
    
    nf_zones = datos['mapa']['no_fly']
    
    return puntos, puntos_entrega, puntos_recarga, grafo, nf_zones

# Función para comprobar la posición relativa de los puntos A, B y C
def orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

# Función para comprobar si el punto C forma parte del segmento A-B
def on_segment(a, b, c):
    return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and
            min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

# Función para comprobar la intersección de la ruta con la zona no-fly
def intersect(a, b, c, d):
    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)

    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    if o1 == 0 and on_segment(a, b, c): return True
    if o2 == 0 and on_segment(a, b, d): return True
    if o3 == 0 and on_segment(c, d, a): return True
    if o4 == 0 and on_segment(c, d, b): return True
    return False

# Función para comprobar si un segmento delimitado por 2 puntos cruza una zona no-fly
def cruza_no_fly(p1, p2, zonas, puntos):
    a = (puntos[p1]['x'], puntos[p1]['y'])
    b = (puntos[p2]['x'], puntos[p2]['y'])
    
    for zona in zonas:
        pol = zona['poligono']
        for i in range(len(pol)):
            c = (pol[i]['x'], pol[i]['y'])
            d = (pol[(i + 1) % len(pol)]['x'], pol[(i + 1) % len(pol)]['y'])
            if intersect(a, b, c, d):
                return True
    return False

# Función para comprobar que una ruta no cruce ninguna zona no-fly
def es_ruta_segura(ruta, puntos, grafo, zonas_no_fly):
    for i in range(len(ruta) - 1):
        if cruza_no_fly(ruta[i], ruta[i+1], zonas_no_fly, puntos):
            return False
    return True

# Función para comprobar que un punto conecta con otro y que no cruza ninguna zona no-fly
def es_arista_valida(p1, p2, puntos, grafo, zonas_no_fly):
    if p2 not in grafo[p1]:
        return False
    return not cruza_no_fly(p1, p2, zonas_no_fly, puntos)

# Función para filtrar los tramos posibles para eliminar los no deseados y devolver los válidos
def obtener_vecinos_validos(punto_actual, puntos, grafo, zonas_no_fly, puntos_recarga, visitados=None):
    vecinos = []
    for vecino in grafo[punto_actual]:
        if vecino == punto_actual:
            continue
        if visitados and vecino in visitados and vecino not in puntos_recarga:
            continue
        if es_arista_valida(punto_actual, vecino, puntos, grafo, zonas_no_fly):
            vecinos.append(vecino)
    return vecinos

# Función para buscar y eliminar ciclos dentro de la ruta (ej. C1->C2->C1->C2)
def eliminar_ciclos(ruta):
    if len(ruta) < 4:
        return ruta.copy()
    nueva_ruta = ruta.copy()
    i = 0
    while i < len(nueva_ruta) - 3:
        if (nueva_ruta[i] == nueva_ruta[i+2] and 
            nueva_ruta[i+1] == nueva_ruta[i+3]):
            del nueva_ruta[i+2:i+4]
            continue
        if i < len(nueva_ruta) - 5:
            if (nueva_ruta[i] == nueva_ruta[i+3] and
                nueva_ruta[i+1] == nueva_ruta[i+4] and
                nueva_ruta[i+2] == nueva_ruta[i+5]):
                del nueva_ruta[i+3:i+6]
                continue
        i += 1
    return nueva_ruta

# Función para evalua la validez de una ruta, obtener sus métricas y establecer las prioridades en función de la estrategia
def evaluar_ruta(ruta, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, estrategia):
    if ruta[0] != "HUB" or ruta[-1] != "HUB":
        return None
    entregas_en_ruta = [p for p in ruta if p in puntos_entrega]
    if len(set(entregas_en_ruta)) != len(puntos_entrega):
        return None
    
    entregas_contadas = {}
    for punto in ruta[1:-1]:
        if punto in puntos_entrega:
            if punto in entregas_contadas:
                return None
            entregas_contadas[punto] = True
    if not es_ruta_segura(ruta, puntos, grafo, zonas_no_fly):
        return None

    distancia_total = 0
    riesgo_total = 0
    consumo_total = 0
    bateria = BATERIA_MAXIMA
    recargas = 0
    
    for i in range(len(ruta) - 1):
        p1 = ruta[i]
        p2 = ruta[i+1]
        
        if p2 not in grafo[p1]:
            if p1 not in grafo[p2]:
                return None
            peso = grafo[p2][p1]
        else:
            peso = grafo[p1][p2]

        if bateria < peso['consumo']:
            return None

        distancia_total += peso['distancia']
        riesgo_total += peso['riesgo']
        consumo_total += peso['consumo']
        bateria -= peso['consumo']

        if p2 in puntos_recarga and bateria < UMBRAL_RECARGA:
            bateria = BATERIA_MAXIMA
            recargas += 1
        
    # Establecemos las prioridades en función de la estrategia elegida
    if estrategia == "1":
        valor = distancia_total
    elif estrategia == "2":
        valor = distancia_total + riesgo_total * 50
    elif estrategia == "4":
        valor = distancia_total + riesgo_total * 40 + recargas * 20
    elif estrategia == "5":
        valor = distancia_total + riesgo_total * 100 - recargas * 10
    else:
        valor = distancia_total + riesgo_total * 50
    
    return (True, distancia_total, riesgo_total, recargas, consumo_total, valor)

# Función para eliminar ciclos de una ruta, evaluar su validez y sacar las métricas
def limpiar_ruta(ruta, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, estrategia):
    # Primero limpiar ciclos
    ruta_fix = eliminar_ciclos(ruta)
    
    # Luego evaluar normalmente
    return evaluar_ruta(ruta_fix, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, estrategia)

# Función para generar una primera ruta aleatoria con un algoritmo voraz
def generar_ruta_aleatoria(puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly):

    ruta = ["HUB"]
    bateria = BATERIA_MAXIMA
    visitados = set(["HUB"])
    entregas_realizadas = set()
    
    # Mezclamos las entregas para orden aleatorio
    entregas_por_visitar = puntos_entrega.copy()
    random.shuffle(entregas_por_visitar)
    
    # Añadimos los puntos de recarga como opciones adicionales
    puntos_disponibles = puntos_entrega + puntos_recarga
    
    max_intentos = 100
    intentos = 0
    
    while entregas_por_visitar and intentos < max_intentos:
        punto_actual = ruta[-1]
        
        # Si la batería está baja, priorizamos los puntos de recarga
        if bateria < UMBRAL_RECARGA:
            # Buscamos las recargas cercanas
            recargas_validas = []
            for recarga in puntos_recarga:
                if (recarga in grafo[punto_actual] and 
                    not cruza_no_fly(punto_actual, recarga, zonas_no_fly, puntos) and
                    bateria >= grafo[punto_actual][recarga]['consumo']):
                    recargas_validas.append(recarga)
            
            if recargas_validas:
                siguiente = random.choice(recargas_validas)
            else:
                vecinos_validos = obtener_vecinos_validos(punto_actual, puntos, grafo, zonas_no_fly, puntos_recarga, visitados)
                if not vecinos_validos:
                    break
                siguiente = random.choice(vecinos_validos)
        else:
            # Priorizamos las puntos de entrega que tenemos aún pendiente
            entregas_validas = []
            for entrega in entregas_por_visitar:
                if (entrega in grafo[punto_actual] and 
                    not cruza_no_fly(punto_actual, entrega, zonas_no_fly, puntos) and
                    bateria >= grafo[punto_actual][entrega]['consumo']):
                    entregas_validas.append(entrega)
            
            if entregas_validas:
                siguiente = random.choice(entregas_validas)
            else:
                vecinos_validos = obtener_vecinos_validos(punto_actual, puntos, grafo, zonas_no_fly, puntos_recarga, visitados)
                if not vecinos_validos:
                    break
                siguiente = random.choice(vecinos_validos)
        
        # Calculamos la batería tras el paso y comprobamos que esta no sea 0
        consumo = grafo[punto_actual][siguiente]['consumo']
        bateria -= consumo
        if bateria < 0:
            break
        
        # Si llegamos a una recarga con la batería por debajo del umbral, la recargamos
        if siguiente in puntos_recarga and bateria < UMBRAL_RECARGA:
            bateria = BATERIA_MAXIMA
        
        ruta.append(siguiente)
        visitados.add(siguiente)
        
        if siguiente in entregas_por_visitar:
            entregas_realizadas.add(siguiente)
            entregas_por_visitar.remove(siguiente)
        
        intentos += 1
    
    # Si se han visitado todos los puntos de entrega se intenta volver al HUB y se devuelve la ruta habiéndola limpiado
    # de posibles ciclos
    if entregas_realizadas == set(puntos_entrega):
        punto_actual = ruta[-1]
        if ("HUB" in grafo[punto_actual] and 
            not cruza_no_fly(punto_actual, "HUB",  zonas_no_fly, puntos) and
            bateria >= grafo[punto_actual]["HUB"]['consumo']):
            ruta.append("HUB")
            return eliminar_ciclos(ruta)
    
    return None

# Función base del simmulated annealing. Comprueba las vecindades de la ruta aleatoria inicialmente generada y
# trata de obtener un mejor resultado a partir de ellas
def generar_vecino(ruta, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly):

    if len(ruta) <= 3:
        return ruta.copy()
    
    nueva_ruta = ruta.copy()
    
    # 4 operaciones sobre los vértices de la ruta:
    #   - intercambiar para intercambiar las posiciones de dos vértices
    #   - invertir para darle la vuelta a todos los vértices de un tramo
    #   - mover para tomar un vértice de la ruta y colocarlo en otra posición sobreescribiendo el vértice original de la posición destino
    # La operación a realizar se escoge de forma aleatoria
    operacion = random.choice(['intercambiar', 'invertir', 'mover', 'mover_seguro'])
    
    indices_validos = list(range(1, len(ruta) - 1))
    if len(indices_validos) < 2:
        return nueva_ruta
    
    if operacion == 'intercambiar':
        i, j = random.sample(indices_validos, 2)
        nueva_ruta[i], nueva_ruta[j] = nueva_ruta[j], nueva_ruta[i]
    
    elif operacion == 'invertir':
        i = random.choice(indices_validos[:-1])
        j = random.choice([k for k in indices_validos if k > i])
        nueva_ruta[i:j+1] = reversed(nueva_ruta[i:j+1])
    
    elif operacion == 'mover':
        i = random.choice(indices_validos)
        elemento = nueva_ruta.pop(i)
        j = random.choice([k for k in range(1, len(nueva_ruta)) if k != i])
        nueva_ruta.insert(j, elemento)   
    
    # Nos aseguramos de que la ruta empiece y finalice en el HUB y quitamos los posibles ciclos antes de finalizar
    if nueva_ruta[0] != "HUB":
        nueva_ruta.insert(0, "HUB")
    if nueva_ruta[-1] != "HUB":
        nueva_ruta.append("HUB")
    return eliminar_ciclos(nueva_ruta)

# Implementación de simmulated annealing para la generación de la ruta
def calculo_ruta(puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, tiempo_limite, estrategia, max_memoria=None):
    max_mem = get_memoria()
    
    # Generamos una solución inicial de forma aleatoria mediante un algoritmo voraz
    solucion_actual = None
    intentos_iniciales = 0
    while solucion_actual is None and intentos_iniciales < 50:
        solucion_actual = generar_ruta_aleatoria(puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly)
        intentos_iniciales += 1
        if time.time() - tiempo_inicio > tiempo_limite:
            return None
    
    if solucion_actual is None:
        return None
    
    # Evaluamos la solución inicial eliminando los posibles ciclos
    eval_actual = limpiar_ruta(solucion_actual, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, estrategia)
    if eval_actual is None:
        return None
    es_valida_actual, dist_actual, riesgo_actual, recargas_actual, consumo_actual, valor_actual = eval_actual
    
    # Si es válida, la utilizamos para intentar mejorarla
    mejor_solucion = solucion_actual.copy()
    mejor_eval = eval_actual
    
    # Parámetros para el simmulated annealing
    temperatura = TEMPERATURA_INICIAL
    iteraciones_sin_mejora = 0
    iteraciones_totales = 0
    soluciones_generadas = 0
    soluciones_aceptadas = 0
    
    # Bucle principal del simulated annealing. Se hacen iteraciones hasta que la temperatura llege al mínimo definido y al final se devuelve
    # la mejor solución encontrada
    while temperatura > TEMPERATURA_FINAL and (time.time() - tiempo_inicio) < tiempo_limite:
        mejora_en_temperatura = False
        
        for _ in range(ITERACIONES_POR_TEMPERATURA):
            iteraciones_totales += 1
            soluciones_generadas += 1
            
            # Generamos vecinos de forma aleatoria y los evaluamos para comprobar que sea válido
            solucion_vecina = generar_vecino(solucion_actual, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly)
            eval_vecina = limpiar_ruta(solucion_vecina, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, estrategia)
            if eval_vecina is None:
                continue
            
            es_valida_vecina, dist_vecina, riesgo_vecina, recargas_vecina, consumo_vecina, valor_vecina = eval_vecina
            
            # Comprobamos la solución nueva para ver si es mejor o peor que la actual
            delta = valor_vecina - valor_actual
            
            # Si mejora, siempre la aceptamos directamente y la comparamos con la mejor solución que tenemos hasta ahora
            if delta < 0:
                solucion_actual = solucion_vecina
                valor_actual = valor_vecina
                eval_actual = eval_vecina
                soluciones_aceptadas += 1
                mejora_en_temperatura = True
                
                if valor_vecina < mejor_eval[5]:
                    mejor_solucion = solucion_vecina.copy()
                    mejor_eval = eval_vecina
                    iteraciones_sin_mejora = 0
                else:
                    iteraciones_sin_mejora += 1
            
            # Si empeora, la aceptamos también con una probabilidad para evitar caer en mínimos locales y
            # explorar una mayor parte del espacio de soluciones
            else:
                probabilidad = math.exp(-delta / temperatura)
                if random.random() < probabilidad:
                    solucion_actual = solucion_vecina
                    valor_actual = valor_vecina
                    eval_actual = eval_vecina
                    soluciones_aceptadas += 1
                    iteraciones_sin_mejora += 1
            
            # Actualizamos el uso de memoria
            max_mem = max(max_mem, get_memoria())
            
            # Comprobamos que nos quede tiempo
            if time.time() - tiempo_inicio > tiempo_limite:
                break
            
            # Si tras muchas iteraciones no se mejora, paramos la ejecución y enfriamos la temperatura
            if iteraciones_sin_mejora > MAX_ITERACIONES_SIN_MEJORA:
                break
                
        # Enfriamos
        temperatura *= FACTOR_ENFRIAMIENTO
        
        if time.time() - tiempo_inicio > tiempo_limite:
            break
    
    # Nos aseguramos de que la mejor solucion actual esté libre de ciclos y guardamos las métricas
    mejor_eval = limpiar_ruta(mejor_solucion, puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, estrategia) 
    es_valida, distancia, riesgo, recargas, consumo, valor = mejor_eval  
    
    res = {
        'ruta': mejor_solucion,
        'distancia': distancia,
        'riesgo': riesgo,
        'consumo': consumo,
        'recargas': recargas,
        'memoria_maxima_mb': max_mem,
        'iteraciones_totales': iteraciones_totales,
        'soluciones_generadas': soluciones_generadas,
        'soluciones_aceptadas': soluciones_aceptadas,
        'temperatura_final': temperatura,
        'valor_evaluacion': valor,
        'estrategia': estrategia
    }
    return res

# Validamos la entrada del script
if len(sys.argv) == 3:
    archivo_json = sys.argv[1]
    tiempo_limite = int(sys.argv[2])
    estrategia = "3"
elif len(sys.argv) == 4 and sys.argv[3] in ("1","2","3","4","5"):
    archivo_json = sys.argv[1]
    tiempo_limite = int(sys.argv[2])
    estrategia = sys.argv[3]
else:
    print("Uso: python planificador_geom.py <instancia.json> <tiempo> [estrategia]")
    sys.exit(1)
puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly = cargar_instancia(archivo_json)

print()
print("="*100)
print("BUSQUEDA DE RUTA POR SIMULATED ANNEALING")
print("="*100)
print(f"Tiempo límite: {tiempo_limite} segundos")
print(f"Batería máxima: {BATERIA_MAXIMA}%")
print(f"Umbral de recarga: {UMBRAL_RECARGA}%")
print(f"Vértices totales (sin HUB): {len(puntos)-1}")
print(f"Puntos de entrega: {len(puntos_entrega)}")
print(f"Puntos de recarga: {len(puntos_recarga)}")

# Ejecutamos el algoritmo de planificación aleatorio que puede no devolver resultado y únicamente paramos cuando se obtenga una ruta válida (Algoritmo Las Vegas)
intentos = 0
while True:
    intentos += 1
    res = calculo_ruta(puntos, puntos_entrega, puntos_recarga, grafo, zonas_no_fly, tiempo_limite, estrategia)  
    if res:
        # Paramos el tiempo de ejecución
        tiempo_total = time.time() - tiempo_inicio
        break
        
# Mostramos los resultados
print(f"\nRuta encontrada ({len(res['ruta'])} nodos):")
print(f"Ruta: {' -> '.join(res['ruta'])}")
print(f"Distancia recorrida: {res['distancia']:.2f}")
riesgo_tramo = round(res['riesgo']/len(res['ruta']), 2)
print(f"Riesgo por tramo: {riesgo_tramo}")
print(f"Consumo total: {res['consumo']:.2f}")
print(f"Tiempo ejecución: {tiempo_total:.2f} segundos")
print(f"Memoria máxima utilizada: {res['memoria_maxima_mb']:.2f} MB")
entregas_visitadas = sum(1 for p in res['ruta'] if p in puntos_entrega)
print(f"Puntos de entrega visitados: {entregas_visitadas}/{len(puntos_entrega)}")
print(f"Recargas efectuadas: {res['recargas']}")
print(f"Total de intentos del algoritmo Las Vegas: {intentos}")
print()

