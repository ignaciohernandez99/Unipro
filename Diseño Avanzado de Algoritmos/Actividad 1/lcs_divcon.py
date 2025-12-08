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

def lcs_divcon_len(A, B):
    # Algoritmo para calcular la última fila de la tabla
    # DP del LCS entre ambas cadenas y encontrar el punto
    # óptimo para cortar la cadena B
    la, lb = len(A), len(B)

    # X es la línea anterior de la matriz de programacion
    # dinámica y Y es la actual
    X = [0] * (lb + 1)
    Y = [0] * (lb + 1)

    # Comparamos cuantos caracteres estarían en la misma posicion
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if A[i-1] == B[j-1]:
                Y[j] = X[j-1] + 1
            else:
                Y[j] = max(X[j], Y[j-1])
        
        # Alternamos las filas para la siguiente iteración
        X, Y = Y, X
        Y = [0] * (lb + 1)
    
    return X

def lcs_divcon(A, B):

    # Sacamos las longitudes de ambas cadenas
    la, lb = len(A), len(B)
    
    # Declaramos los pasos base.
    # Si alguna de las cadenas está vacía se devuelve una cadena vacía
    if 0 in (la,lb): return ""

    # Si alguna de las cadenas tiene solo un elemento se devuelve ese
    # elemento si esta dentro de la otra cadena
    if la == 1:
        return A if A in B else ""  
    if lb == 1:
        return B if B in A else ""
    
    # Dividimos la primera cadena en funcion de su punto medio entero
    piv = la//2
    A1, A2 = A[:piv], A[piv:]
    
    # Calculamos la primera mitad
    L1 = lcs_divcon_len(A1, B)
    
    # Calculamos la segunda mitad
    A2_rev = A2[::-1]
    B_rev = B[::-1]
    L2 = lcs_divcon_len(A2_rev, B_rev)
    
    # Con el resultado de la primera función buscamos
    # el punto de corte óptimo
    k = 0
    max_sum = -1
    
    for i in range(lb + 1):
        current_sum = L1[i] + L2[lb - i]
        if current_sum > max_sum:
            max_sum = current_sum
            j = i
    
    B1, B2 = B[:j], B[j:]
    
    # Llamamos de manera recursiva a esta misma función para sacar
    # las soluciones parciales y luego combinarlas en la solución final
    return (lcs_divcon(A1, B1) + lcs_divcon(A2, B2))

# Las pareja de cadenas a utilizar estará en un archivo de texto externo
# separadas en dos líneas diferentes
entrada = sys.argv[1]
with open(entrada,"r", encoding="utf-8") as f:
    cadenas = f.readlines()
A = cadenas[0].strip()
B = cadenas[1].strip()

# Calculamos el resultado
res = lcs_divcon(A,B)

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
