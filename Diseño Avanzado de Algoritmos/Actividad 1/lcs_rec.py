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

# Definición de la función recursiva para cálculo de LCS
def lcs_rec(A, B):
    # Paso base: Si la longitud de alguna de las cadenas es 0
    # se devuelve una cadena vacía
    if 0 in (len(A),len(B)): return ""
    
    # Si no, se comprueba si los últimos valores de las cadenas
    # coinciden y, si es así, se devuelve dicho valor.
    elif A[-1]==B[-1]: return lcs_rec(A[:-1],B[:-1]) + A[-1]
    
    # Si no, se aplica el método recursivo ignorando el último valor
    # de cada subcadena y comparándolas por separado.
    # Se utilizará aquella subcadena que se encuentre de mayor
    # longitud
    else:
        A_rec = lcs_rec(A[:-1],B)
        B_rec = lcs_rec(A,B[:-1])
        return A_rec if len(A_rec) > len(B_rec) else B_rec

# Las pareja de cadenas a utilizar estará en un archivo de texto externo
# separadas en dos líneas diferentes
entrada = sys.argv[1]
with open(entrada,"r", encoding="utf-8") as f:
    cadenas = f.readlines()
A = cadenas[0].strip()
B = cadenas[1].strip()

# Calculamos el resultado
res = lcs_rec(A,B)

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

