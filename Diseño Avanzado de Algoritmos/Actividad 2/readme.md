<h1>Actividad 2</h1> 
<h2>Instrucciones de ejecución</h2>

<ul>
  <li><b>planificador_b&b.py:</b> Backtracking/Branch-and-Bound con poda guiada por heurística</li>
  <li><b>planificador_geo.py:</b> Algoritmo geométrico basado en visibilidad</li>
  <li><b>planificador_metarand.py:</b> Metaheurística (Simmulated Annealing) con algoritmo Las Vegas</li>
</ul>

Asegurarse de tener instalado Python en el equipo y las librerías <em>psutil</em> y <em>random</em>
```
pip install psutil
pip install random
```

Tener los algoritmos .py y las instancias .json en la misma carpeta.<br>
Cada instancia tiene en su nombre el número de vértices totales de la instancia, sin contar el HUB central.<br>
Para ejecutar, lanzar desde la consola de comandos de Windows el script desde Python. 

<h3>Uso de los scripts</h3>

```
python planificador_geom.py <instancia.json> <tiempo> [estrategia (1,2,3,4,5)]
```

<h3>Ejemplo de ejecución</h3>

```
python .\planificador_metarand.py .\20.json 60 4

====================================================================================================
BUSQUEDA DE RUTA POR SIMULATED ANNEALING
====================================================================================================
Tiempo límite: 60 segundos
Batería máxima: 50%
Umbral de recarga: 30%
Vértices totales (sin HUB): 20
Puntos de entrega: 14
Puntos de recarga: 6

Ruta encontrada (23 nodos):
Ruta: HUB -> E14 -> C2 -> E12 -> E6 -> E2 -> E10 -> C5 -> E8 -> E1 -> E11 -> C4 -> E5 -> C4 -> C3 -> E7 -> E4 -> C3 -> E13 -> C6 -> E3 -> E9 -> HUB
Distancia recorrida: 459.50
Riesgo por tramo: 0.18
Consumo total: 166.00
Tiempo ejecución: 1.00 segundos
Memoria máxima utilizada: 18.42 MB
Puntos de entrega visitados: 14/14
Recargas efectuadas: 3
Total de intentos del algoritmo Las Vegas: 7
```
