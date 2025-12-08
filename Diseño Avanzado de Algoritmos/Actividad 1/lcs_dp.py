# Librerías para realizar el tiempo de ejecución y el
# uso de recursos (CPU)
import psutil
import time
import os
import sys
import threading

# Inicializamos de las variables para medición de tiempo y recursos
max_mem = 0
running = True
pid = os.getpid()
proceso = psutil.Process(pid)

# Definimos la función utilizada para medir el máximo de memoria utilizada
def monitor_mem():
    global max_mem
    while running:
        mem = proceso.memory_info().rss   # Bytes de RAM usados
        if mem > max_mem:
            max_mem = mem
        time.sleep(0.05)  # pequeño intervalo para no saturar CPU

# Lanzar monitor
t = threading.Thread(target=monitor_mem)
t.start()
        
# Tomamos tiempo de inicio
inicio = time.time()

# Definimos la función de cálculo de LCS mediante programacion dinámica
def lcs_dp(A, B):

    # Calculamos las longitudes de las cadenas
    la = len(A)
    lb = len(B)
    
    # Creamos la matriz DP
    # En ella almacenaremos la longitud de LCS de las cadenas parciales
    matriz = [[0] * (lb + 1) for _ in range(la + 1)]
    
    # Llenamos la matriz DP 
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if A[i - 1] == B[j - 1]:
                matriz[i][j] = matriz[i - 1][j - 1] + 1
            else:
                matriz[i][j] = max(matriz[i - 1][j], matriz[i][j - 1])
    
    # Reconstruimos el LCS desde la matriz
    res = ""
    i, j = la, lb
    
    while i > 0 and j > 0:
        # Si los caracteres coinciden los añadimos al LCS resultado
        # Si no, seguimos recorriendo la tabla de arriba hacia abajo
        # y de izquierda a derecha buscando el valor mayor
        # de coincidencia
        if A[i - 1] == B[j - 1]:
            res = A[i - 1] + res
            i -= 1
            j -= 1
        elif matriz[i - 1][j] > matriz[i][j - 1]:
            i -= 1
        else:
            j -= 1
    
    return res

# Las pareja de cadenas a utilizar estará en un archivo de texto externo
# separadas en dos líneas diferentes
entrada = sys.argv[1]
with open(entrada,"r", encoding="utf-8") as f:
    cadenas = f.readlines()
A = cadenas[0].strip()
B = cadenas[1].strip()

# Calculamos el resultado
res = lcs_dp(A,B)

# Tomamos el tiempo de final
fin = time.time()

running = False
t.join()

max_mem_MB = max_mem / (1024*1024)
t_exec = fin - inicio

# Mostramos por pantalla el resultado e indicamos su longitud
# También indicamos el tiempo de ejecución y el uso medio de la CPU

print(res, "| Longitud de ", len(res))
print("Tiempo de ejecución: ", t_exec, "segundos.")
print("Uso máximo de memoria: ", max_mem_MB, "MB.")

