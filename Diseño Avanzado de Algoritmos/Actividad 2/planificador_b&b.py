import sys
import json
import math
import time
import random
from collections import defaultdict
import psutil
import os

# Parámetros globales del script
BATERIA_MAXIMA = 50
UMBRAL_RECARGA = 30
ratio_profundidad = 1.25

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

# Función para comprobar la intersección de la ruta con la zona no-fly
def cruza_no_fly(p1, p2, zonas):
    for zona in zonas:
        pol = zona['poligono']
        for i in range(len(pol)):
            a = (pol[i]['x'], pol[i]['y'])
            b = (pol[(i + 1) % len(pol)]['x'], pol[(i + 1) % len(pol)]['y'])
            if intersect(p1, p2, a, b):
                return True
    return False

# Función de implementación del algoritmo mediante Backtracking
def calculo_ruta(puntos, puntos_entrega, puntos_recarga, grafo, no_fly_zones, BATERIA_MAXIMA, tiempo_limite, estrategia):
    
    # Seguimiento de uso máximo de memoria
    max_memoria = 0
    
    # Función para actualizar el máximo de memoria
    def actualizar_max_memoria():
        nonlocal max_memoria
        memoria_actual = get_memoria()
        if memoria_actual > max_memoria:
            max_memoria = memoria_actual
        return memoria_actual
    
    # Actualizamos memoria inicial
    actualizar_max_memoria()
    
    # Creamos una caché para guardar las rutas que ya hemos comprobado y evitar repetir cálculos y bucles
    cache_seguridad = {}
    
    # Función para comprobar si la ruta interseca con alguna zona no-fly
    def es_segura(puntos, ruta_actual, vertice_siguiente, no_fly_zones, cache_seguridad):
        
        # Trabajamos con los 3 últimos vértices para descartar bucles
        if len(ruta_actual) >= 3:
            clave = (tuple(ruta_actual[-3:]), vertice_siguiente)
        else:
            clave = (tuple(ruta_actual), vertice_siguiente)
        
        # En el primer movimiento, incluimos el HUB, que siempre va a ser seguro
        if not ruta_actual:
            cache_seguridad[clave] = True
            return True
        
        # Antes de calcular, comprobamos la caché
        if clave in cache_seguridad:
            return cache_seguridad[clave]

        # Obtenemos las coordenadas del último vértice y del siguiente
        ultimo_vertice = ruta_actual[-1]
        x1, y1 = puntos[ultimo_vertice]['x'], puntos[ultimo_vertice]['y']
        x2, y2 = puntos[vertice_siguiente]['x'], puntos[vertice_siguiente]['y']
        
        # Verificamos si interseca con alguna de las zonas no-fly
        for zona in no_fly_zones:
            p1_coords = (x1, y1)
            p2_coords = (x2, y2)
            if cruza_no_fly(p1_coords, p2_coords, no_fly_zones):
                cache_seguridad[clave] = False
                return False
        
        # Si llegamos hasta aquí se han pasado todas las verificaciones y, por tanto, es seguro
        cache_seguridad[clave] = True
        return True
    
    mejor_solucion = None
    mejor_distancia = float('inf')
    mejor_riesgo = float('inf')
    max_profundidad = len(puntos) * ratio_profundidad
    posibilidades_exploradas = 0
    tiempo_inicio = time.time()
    
    # Buscamos candidatos mediante el método de poda 
    def explorar(ruta_actual, visitados, distancia_actual, riesgo_actual, consumo_actual, bateria_actual, profundidad, recargas):
        nonlocal mejor_solucion, mejor_distancia, mejor_riesgo, posibilidades_exploradas
        
        # Actualizamos la memoria periódicamente
        if posibilidades_exploradas % 100 == 0:
            actualizar_max_memoria()
        
        posibilidades_exploradas += 1
        
        # Comprobamos como vamos de tiempo
        if time.time() - tiempo_inicio > tiempo_limite:
            return
        
        # Verificamos si la profundidad actual es superior a la máxima
        if profundidad > max_profundidad:
            return
        
        # Si tenemos una buena solución hacemos una poda más agresiva
        if mejor_solucion and posibilidades_exploradas > 10000 and distancia_actual > mejor_distancia * 1.5:
            return
        
        # Comprobamos si se han visitado ya todos los destinos (puntos de entrega)
        if all(p in visitados for p in puntos_entrega):
        
            # Si el último nodo visitado es el HUB, entonces la solución es completa y válida
            ultimo = ruta_actual[-1]
            if 'HUB' not in grafo[ultimo]:
                return
            
            datos_hub = grafo[ultimo]['HUB']
            dist_final = distancia_actual + datos_hub['distancia']
            riesgo_final = riesgo_actual + datos_hub['riesgo']
            consumo_final = consumo_actual + datos_hub['consumo']
            
            # Comprobamos que tengamos batería para realizar el último paso
            if bateria_actual < datos_hub['consumo']:
                return
            
            # Comprobamos que la ruta actual no cruza ninguna zona no-fly
            if not es_segura(puntos, [ultimo], 'HUB', no_fly_zones, cache_seguridad):
                return
            
            # Evaluamos si la solución actual es mejor que la anterior o si todavía no hay ninguna
            # Dependiendo de la estrategia, evaluamos diferente
            if estrategia == "1":
                valor_actual = dist_final
                mejor_valor = mejor_distancia
            elif estrategia == "2":
                valor_actual = riesgo_final
                mejor_valor = mejor_riesgo
            else:
                valor_actual = dist_final + riesgo_final * 50
                mejor_valor = mejor_distancia + mejor_riesgo * 50
            
            if mejor_solucion is None or valor_actual < mejor_valor:
                mejor_solucion = {
                    'ruta': ruta_actual + ['HUB'],
                    'distancia': dist_final,
                    'riesgo': riesgo_final,
                    'consumo': consumo_actual + datos_hub['consumo'],
                    'posibilidades_exploradas': posibilidades_exploradas,
                    'recargas': recargas,
                    'estrategia': estrategia
                }
                mejor_distancia = dist_final
                mejor_riesgo = riesgo_final
            return
            
        punto_actual = ruta_actual[-1]
        
        # Configuramos el umbral de recarga según la estrategia elegida
        if estrategia == "4":
            umbral_actual = UMBRAL_RECARGA + 15
        elif estrategia == "5":
            umbral_actual = UMBRAL_RECARGA - 10
        else:
            umbral_actual = UMBRAL_RECARGA
                        
        candidatos = []
        
        for vecino, datos in grafo[punto_actual].items():
            if vecino == 'HUB':
                continue
                
            # Si el siguiente punto de entrega candidato ya ha sido visitado, lo ignoramos
            if vecino in puntos_entrega and vecino in visitados:
                continue
            
            # Si no tuviesemos suficiente combustible para realizar el paso y el siguiente punto no es un punto de recarga, lo ignoramos
            nueva_bateria = bateria_actual - datos['consumo']
            if nueva_bateria < 0 and vecino not in puntos_recarga:
                continue
            
            # Si la ruta candidata cruza alguna zona no-fly, la ignoramos
            if not es_segura(puntos, ruta_actual, vecino, no_fly_zones, cache_seguridad):
                continue
            
            # Calculamos cuantos puntos de entrega nos falta por visitar y estimamos un posible costo para llegar a ellos (cota)
            restantes = len(puntos_entrega) - len(visitados)
            estimacion = distancia_actual + datos['distancia'] + (restantes * 25)
            
            # Si la estimación tiene un coste mayor que la mejor actual, la ignoramos
            if mejor_solucion and estimacion > mejor_distancia * 1.3:
                continue
            
            # Calculamos prioridad la según la estrategia elegida o el valor de la carga si este está por debajo del umbral
            prioridad = 0
            
            # Si la batería está baja damos prioridad a puntos de recarga penalizando los puntos de entrega
            if bateria_actual < umbral_actual:
                if vecino in puntos_recarga:
                    prioridad = datos['distancia'] * 0.01
                else:
                    prioridad = datos['distancia'] * 5.0
            # Si la batería no está por debajo del umbral
            else:
                if estrategia == "1":
                    prioridad = datos['distancia']
                elif estrategia == "2":
                    prioridad = datos['distancia'] + datos['riesgo'] * 50
                elif estrategia == "4":
                    prioridad = datos['distancia'] + datos['riesgo'] * 40 + datos['consumo'] * 10
                elif estrategia == "5":
                    prioridad = datos['distancia'] + datos['riesgo'] * 100 - datos['consumo'] * 5
                else:
                    prioridad = datos['distancia'] + datos['riesgo'] * 50
            
            # Priorizamos los puntos de entrega no visitados
            if vecino in puntos_entrega and vecino not in visitados:
                prioridad *= 0.3 
            
            candidatos.append((prioridad, vecino, datos, nueva_bateria))
        
        # Ordenamos según la prioridad establecida por la estrategia
        candidatos.sort(key=lambda x: x[0])
        
        # Limitamos la búsqueda a los mejores 3 candidatos
        for _, vecino, datos, nueva_bateria in candidatos[:3]:
            nuevas_recargas = recargas
            nueva_bateria_despues_movimiento = nueva_bateria
            
            # Solo contamos una recarga si se pasa por un punto de recarga teniendo la batería por debajo del umbral
            if vecino in puntos_recarga and nueva_bateria < umbral_actual:
                nueva_bateria_despues_movimiento = BATERIA_MAXIMA 
                nuevas_recargas = recargas + 1
                
            # Si pasamos por un punto de recarga pero no necesitamos recargar no lo contamos
            elif vecino in puntos_recarga and nueva_bateria >= umbral_actual:
                nueva_bateria_despues_movimiento = nueva_bateria
                nuevas_recargas = recargas
            
            nuevo_visitados = visitados.copy()
            if vecino in puntos_entrega:
                nuevo_visitados.add(vecino)
            
            # Determinamos si necesitamos recarga urgente en el siguiente paso
            siguiente_necesita_recarga = (nueva_bateria_despues_movimiento < umbral_actual) and (vecino not in puntos_recarga)
            
            # Proseguimos la búsqueda de forma recursiva
            explorar(
                ruta_actual + [vecino],
                nuevo_visitados,
                distancia_actual + datos['distancia'],
                riesgo_actual + datos['riesgo'],
                consumo_actual + datos['consumo'],
                nueva_bateria_despues_movimiento,
                profundidad + 1,
                nuevas_recargas
            )
            
    # Iniciamos la búsqueda de candidatos
    explorar(['HUB'], set(), 0, 0, 0, BATERIA_MAXIMA, 0, 0)
    
    tiempo_total = time.time() - tiempo_inicio
    
    # Última actualización de memoria
    actualizar_max_memoria()
    
    if mejor_solucion:
        mejor_solucion['tiempo_ejecucion'] = tiempo_total
        mejor_solucion['memoria_maxima_mb'] = max_memoria
    
    return mejor_solucion

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
    print("Uso: python planificador_geom.py <instancia.json> <tiempo> [estrategia (1,2,3,4,5)]")
    sys.exit(1)
    
puntos, puntos_entrega, puntos_recarga, grafo, no_fly_zones = cargar_instancia(archivo_json)

print()
print("="*100)
print("BUSQUEDA DE RUTA POR BACKTRACKING / BRANCH-AND-BOUND CON PODA GUIADA POR COTAS HEURÍSTICAS")
print("="*100)
print(f"Tiempo límite: {tiempo_limite} segundos")
print(f"Batería máxima: {BATERIA_MAXIMA}%")
print(f"Umbral de recarga: {UMBRAL_RECARGA}%")
print(f"Vértices totales (sin HUB): {len(puntos)-1}")
print(f"Puntos de entrega: {len(puntos_entrega)}")
print(f"Puntos de recarga: {len(puntos_recarga)}")

# Ejecutamos el algoritmo de planificación
res = calculo_ruta(puntos, puntos_entrega, puntos_recarga, grafo, no_fly_zones, BATERIA_MAXIMA, tiempo_limite, estrategia)

# Mostramos los resultados
if res:
    print(f"\nRuta encontrada:")
    print(f"Ruta: {' -> '.join(res['ruta'])}")
    print(f"Distancia recorrida: {res['distancia']:.2f}")
    riesgo_tramo = round(res['riesgo']/len(res['ruta']), 2)
    print(f"Riesgo por tramo: {riesgo_tramo}")
    print(f"Consumo total: {res['consumo']:.2f}")
    print(f"Tiempo ejecución: {res['tiempo_ejecucion']:.2f} segundos")
    print(f"Memoria máxima utilizada: {res['memoria_maxima_mb']:.2f} MB")
    entregas_visitadas = sum(1 for p in res['ruta'] if p in puntos_entrega)
    print(f"Puntos de entrega visitados: {entregas_visitadas}/{len(puntos_entrega)}")
    print(f"Recargas efectuadas: {res['recargas']}")
    print()
else:
    print("\nNo se ha podido encontrar una solución válida completa en el tiempo establecido.\n")

