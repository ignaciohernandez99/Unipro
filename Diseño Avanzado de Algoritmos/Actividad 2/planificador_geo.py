import sys
import json
import time
import math
import psutil
import os
from collections import defaultdict

# Parámetros globales del script
BATERIA_MAXIMA = 50
UMBRAL_RECARGA = 30
FACTOR_PODA = 1.25
MAX_RECURSION = 5000

# Función para obtener el uso actual de memoria en MB
def memoria_mb():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

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
    return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

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
def cruza_no_fly(p1, p2, zonas):
    for zona in zonas:
        pol = zona['poligono']
        for i in range(len(pol)):
            a = (pol[i]['x'], pol[i]['y'])
            b = (pol[(i + 1) % len(pol)]['x'], pol[(i + 1) % len(pol)]['y'])
            if intersect(p1, p2, a, b):
                return True
    return False

# Función para calcular el grafo visible eliminando las aristas que coinciden con las zonas no-fly
def grafo_visible(puntos, grafo_base, zonas):
    grafo = defaultdict(dict)

    for u in grafo_base:
        for v, peso in grafo_base[u].items():
            p1 = (puntos[u]['x'], puntos[u]['y'])
            p2 = (puntos[v]['x'], puntos[v]['y'])

            if not cruza_no_fly(p1, p2, zonas):
                grafo[u][v] = peso
    return grafo

# Función para calcular el consumo de la ruta final.
def calculo_consumo(ruta, grafo):
    consumo = 0
    for i in range(len(ruta) - 1):
        p1 = ruta[i]
        p2 = ruta[i + 1]
       
        # Verificamos si la arista existe en el grafo visible
        if p2 in grafo[p1]:
            consumo += grafo[p1][p2]['consumo']
        # Comprobamos también el sentido contrario de la arista
        else:
            consumo += grafo[p2][p1]['consumo']
    return consumo

# Función para encontrar el punto de recarga más cercano y accesible
def encontrar_recarga_cercana(punto_actual, bateria_actual, puntos, puntos_recarga, grafo):
    
    mejor_recarga = None
    mejor_distancia = float('inf')
    
    for recarga in puntos_recarga:
        # Comprobamos si hay conexión directa
        if recarga in grafo[punto_actual]:
            datos = grafo[punto_actual][recarga]
            
            # Comprobamos si se puede llegar con la batería actual
            if bateria_actual >= datos['consumo']:
                if datos['distancia'] < mejor_distancia:
                    mejor_distancia = datos['distancia']
                    mejor_recarga = (recarga, datos)
    
    return mejor_recarga

# Función de implementación del planificador mediante algoritmos geométricos
def calculo_ruta(puntos, puntos_entrega, puntos_recarga, grafo, tiempo_limite, estrategia):
    mejor = None
    mejor_dist = float('inf')
    mejor_riesgo = float('inf')
    inicio = time.time()
    max_mem = 0
    estados_visitados = set()
    llamadas_recursivas = [0]

    # Calculamos las entregas restantes
    def entregas_restantes(nodo, visitados):
        return (len(puntos_entrega) - len(visitados)) * 20

    def bt(ruta, visitados, dist, riesgo, bateria, recargas, profundidad, necesita_recarga_urgente=False):
        nonlocal mejor, mejor_dist, mejor_riesgo, max_mem
        
        llamadas_recursivas[0] += 1
        max_mem = max(max_mem, memoria_mb())
        
        # Comprobamos como vamos de tiempo y paramos si es encesario
        if time.time() - inicio > tiempo_limite:
            return True
        
        # Comprobamos el límite de recursión establecido
        if profundidad > MAX_RECURSION:
            return False
        
        # Podamos los estados que no dan buenos resultados si han hecho muchos movimientos pero no han completado entregas
        if len(ruta) > len(puntos_entrega) * 2 + 10:
            # Si hemos hecho muchos movimientos pero pocas entregas
            entregas_realizadas = len(visitados)
            if entregas_realizadas < len(ruta) / 3:
                return False
        
        # Revisamos los últimos movimientos para evitar ciclos
        ultimos_movimientos = tuple(ruta[-5:]) if len(ruta) >= 5 else tuple(ruta)
        firma = (ruta[-1], frozenset(visitados), int(bateria), ultimos_movimientos)
        if firma in estados_visitados:
            return False
        estados_visitados.add(firma)
        
        # Todas las entregas visitadas
        if len(visitados) == len(puntos_entrega):
            u = ruta[-1]
            if 'HUB' in grafo[u]:
                peso = grafo[u]['HUB']
                if bateria >= peso['consumo']:
                    total_dist = dist + peso['distancia']
                    total_riesgo = riesgo + peso['riesgo']
                    
                    # Evaluamos según la estrategia elegida
                    if estrategia == "1":
                        valor_actual = total_dist
                        mejor_valor = mejor_dist
                    elif estrategia == "2":
                        valor_actual = total_riesgo
                        mejor_valor = mejor_riesgo
                    else:
                        valor_actual = total_dist + total_riesgo * 50
                        mejor_valor = mejor_dist + mejor_riesgo * 50
                    
                    if mejor is None or valor_actual < mejor_valor:
                        mejor_dist = total_dist
                        mejor_riesgo = total_riesgo
                        mejor = {
                            'ruta': ruta + ['HUB'],
                            'distancia': total_dist,
                            'riesgo': total_riesgo,
                            'recargas': recargas,
                            'consumo': BATERIA_MAXIMA * recargas + (BATERIA_MAXIMA - bateria),
                            'tiempo_ejecucion': time.time() - inicio,
                            'memoria_maxima_mb': max_mem
                        }
            return False

        u = ruta[-1]
        
        # Configuramos el umbral de recarga según la estrategia elegida
        if estrategia == "4":
            umbral_actual = UMBRAL_RECARGA + 15
        elif estrategia == "5":
            umbral_actual = UMBRAL_RECARGA - 10
        else:
            umbral_actual = UMBRAL_RECARGA
        
        # Si la batería está por debajo del umbral y no estamos ya yendo a una recarga buscamos un punto de recarga cercano
        if bateria < umbral_actual and not necesita_recarga_urgente:
            
            recarga_cercana = encontrar_recarga_cercana(u, bateria, puntos, puntos_recarga, grafo)
            
            if recarga_cercana:
                vecino, datos = recarga_cercana
                nueva_bateria = BATERIA_MAXIMA

                detener = bt(
                    ruta + [vecino],
                    visitados.copy(),
                    dist + datos['distancia'],
                    riesgo + datos['riesgo'],
                    nueva_bateria,
                    recargas + 1,
                    profundidad + 1,
                    necesita_recarga_urgente=False
                )
                
                if detener:
                    return True
        
        # Ordenamos los vecinos según la estrategía elegida
        vecinos = []
        for v, peso in grafo[u].items():
            if v == 'HUB' and len(visitados) < len(puntos_entrega):
                continue
            
            # Si un vecino es un punto de entrega que ya hemos visitado, lo ignoramos
            if v in puntos_entrega and v in visitados:
                continue
            
            if peso['consumo'] > bateria:
                continue
            
            if v in puntos_recarga:
                # Revisamos si hay un bucle local en caso de que los dos últimos movimientos fueron entre las dos mismas recargas
                if len(ruta) >= 2:
                    if ruta[-1] in puntos_recarga and ruta[-2] in puntos_recarga:
                        if v == ruta[-2]:
                            continue
                if ruta.count(v) > 2: 
                    continue
            else:
                if v in ruta[-3:]:
                    continue
            
            # Calculamos prioridad la según la estrategia elegida o el valor de la carga si este está por debajo del umbral
            prioridad = 0
            
            # Si la batería está baja damos prioridad a puntos de recarga penalizando los puntos de entrega
            if bateria < umbral_actual:
                if v in puntos_recarga:
                    prioridad = peso['distancia'] * 0.01
                else:
                    prioridad = peso['distancia'] * 5.0
            # Si la batería no está por debajo del umbral
            else:
                if estrategia == "1":
                    prioridad = peso['distancia']
                elif estrategia == "2":
                    prioridad = peso['distancia'] + peso['riesgo'] * 50
                elif estrategia == "4":
                    prioridad = peso['riesgo'] * 40 + peso['consumo'] * 10
                elif estrategia == "5":
                    prioridad = peso['distancia'] + peso['riesgo'] * 100 - peso['consumo'] * 5
                else:
                    prioridad = peso['distancia'] + peso['riesgo'] * 50
            
            # Priorizamos los puntos de entrega no visitados
            if v in puntos_entrega and v not in visitados:
                prioridad *= 0.3
            
            # Comprobamos los puntos de recarga y los penalizamos si ya hemos pasado por ellos
            if v in puntos_recarga:
                visitas_recarga = ruta.count(v)
                if visitas_recarga > 1:
                    prioridad *= (visitas_recarga + 1)
                recargas_seguidas = 0
                for i in range(min(3, len(ruta))):
                    if ruta[-i-1] in puntos_recarga:
                        recargas_seguidas += 1
                if recargas_seguidas >= 2 and v in puntos_recarga:
                    prioridad *= 2.0
            
            vecinos.append((prioridad, v, peso))
        
        # Ordenamos según la prioridad establecida por la estrategia
        vecinos.sort(key=lambda x: x[0])
        
        # Creamos una lista de posibles candidatos y, en función de las necesidades y las orioridades los priorizamos
        entregas_candidatas = [(p, v, peso) for p, v, peso in vecinos if v in puntos_entrega]
        recargas_candidatas = [(p, v, peso) for p, v, peso in vecinos if v in puntos_recarga]
        candidatos_seleccionados = []
        
        if bateria > umbral_actual and entregas_candidatas:
            candidatos_seleccionados.extend(entregas_candidatas[:1])
            if recargas_candidatas and bateria < umbral_actual * 1.5:
                candidatos_seleccionados.append(recargas_candidatas[0])
        else:
            if recargas_candidatas:
                candidatos_seleccionados.extend(recargas_candidatas[:1])
                
        if len(candidatos_seleccionados) < 2:
            candidatos_seleccionados = vecinos[:2]
        
        for prioridad, v, peso in candidatos_seleccionados:
            nueva_bateria = bateria - peso['consumo']
            nuevas_recargas = recargas
            
            if v in puntos_recarga and nueva_bateria < umbral_actual:
                nueva_bateria = BATERIA_MAXIMA
                nuevas_recargas += 1

            estimacion = dist + peso['distancia'] + entregas_restantes(v, visitados)
            if mejor and estimacion > mejor_dist * FACTOR_PODA:
                continue
            
            nuevos_visitados = set(visitados)
            if v in puntos_entrega and v not in visitados:
                nuevos_visitados.add(v)
            
            # Determinamos si necesitamos recargar urgentemente
            siguiente_necesita_recarga = (nueva_bateria < umbral_actual) and (v not in puntos_recarga)
            
            detener = bt(ruta + [v], nuevos_visitados, dist + peso['distancia'], riesgo + peso['riesgo'], nueva_bateria, nuevas_recargas, profundidad + 1, siguiente_necesita_recarga)
            
            # Si el tiempo se ha agotado, finalizamos la ejecución al acabar la iteración
            if detener:
                return True

        return False

    tiempo_inicio = time.time()
    
    bt(['HUB'], set(), 0, 0, BATERIA_MAXIMA, 0, 0, necesita_recarga_urgente=False)
    
    tiempo_total = time.time() - tiempo_inicio
    
    if mejor:
        mejor['tiempo'] = tiempo_total
        mejor['memoria_mb'] = max_mem
    
    return mejor

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

puntos, puntos_entrega, puntos_recarga, grafo_base, zonas = cargar_instancia(archivo_json)
tiempo_limite = int(sys.argv[2])

print()
print("="*100)
print("BUSQUEDA DE RUTA POR ALGORITMO GEOMÉTRICO BASADO EN VISIBILIDAD E INTERSECCIÓN DE SEGMENTOS")
print("="*100)
print(f"Tiempo límite: {tiempo_limite} segundos")
print(f"Batería máxima: {BATERIA_MAXIMA}%")
print(f"Umbral de recarga: {UMBRAL_RECARGA}%")
print(f"Vértices totales (sin HUB): {len(puntos) - 1}")
print(f"Puntos de entrega: {len(puntos_entrega)}")
print(f"Puntos de recarga: {len(puntos_recarga)}")

# Calculamos el grafo visible eliminando todas aquellas aristas que coincidan con alguna zona no-fly
grafo = grafo_visible(puntos, grafo_base, zonas)

# Ejecutamos el algoritmo de planificación
res = calculo_ruta(puntos, puntos_entrega, puntos_recarga, grafo, tiempo_limite, estrategia)

# Mostramos los resultados
if res:
    print(f"\nRuta encontrada ({len(res['ruta'])} nodos):")
    print(f"Ruta: {' -> '.join(res['ruta'])}")
    print(f"Distancia recorrida: {res['distancia']:.2f}")
    riesgo_tramo = round(res['riesgo']/len(res['ruta']), 2)
    print(f"Riesgo por tramo: {riesgo_tramo}")
    print(f"Consumo total: {calculo_consumo(res['ruta'], grafo)}")
    print(f"Tiempo ejecución: {res['tiempo']:.2f} segundos")
    print(f"Memoria máxima utilizada: {res['memoria_mb']:.2f} MB")
    entregas_visitadas = sum(1 for p in res['ruta'] if p in puntos_entrega)
    print(f"Puntos de entrega visitados: {entregas_visitadas}/{len(puntos_entrega)}")
    print(f"Recargas efectuadas: {res['recargas']}")
    print()
else:
    print("\nNo se ha podido encontrar una solución válida completa en el tiempo establecido.\n")