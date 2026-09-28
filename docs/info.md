
## How it works

Este proyecto es un procesador RISC-V RV32I de **ciclo unico**, programable por UART en tiempo real -- no tiene ninguna instruccion pregrabada en el silicio. El chip arranca en modo de carga (LOAD), esperando recibir un programa completo por UART; una vez recibido, pasa a modo de ejecucion (RUN) y corre ese programa exactamente igual que cualquier microprocesador de ciclo unico convencional (un ciclo de reloj por instruccion, sin segmentacion).

Implementa el set de instrucciones RV32I completo (aritmetica y logica de registro-registro y registro-inmediato, desplazamientos, comparaciones con y sin signo, saltos y branches, cargas y almacenamientos de byte/media palabra/palabra completa, `lui`/`auipc`), ademas de dos perifericos mapeados en memoria:

- **UART**: usado tanto para *cargar* el programa (bootloader) como, una vez el programa esta corriendo, para que el software transmita y reciba datos en tiempo real (direcciones `0x40` TX y `0x44` RX).
- **SPI maestro** (modo 0, 8 bits): permite que el software hable con un periferico SPI externo (direccion `0x48`).

Todo el diseño fue validado de forma exhaustiva en una FPGA Basys3 antes de esta sintesis: las 37 instrucciones del set se probaron individualmente, junto con pruebas de estres (generacion de Fibonacci), interaccion UART en tiempo real (calculadoras interactivas por teclado), y el periferico SPI en loopback fisico.

### Especificaciones validadas

| Metrica | Valor |
| --- | --- |
| Instrucciones RV32I verificadas | 30/30 (set base) |
| Metodo de verificacion | Modelo cycle-accurate en Python + hardware real (FPGA Basys3) |
| Invariante de exclusion mutua | 0 violaciones en 136,353 ciclos simulados |
| Programas de categoria validados en FPGA | 10/10 (A, B, C, D, D2, E, F2, G, H_suma, H_resta) |
| Reloj | 10 MHz |
| Baudrate UART | 115200 bps |
| Memoria de instrucciones fisica | 8 palabras, encadenada por bloques via SPI |

## How to test

1. Carga un programa por UART (8N1, 115200 baudios) al pin de RX del proyecto: exactamente `INSTR_DEPTH` palabras de 32 bits (ver `info.yaml` para el numero exacto), enviadas byte por byte, LSB primero por palabra.
2. El chip transiciona automaticamente a modo RUN al recibir la ultima palabra (visible en `uo_out[7]`).
3. El programa cargado puede leer/escribir UART y SPI usando los registros mapeados en memoria (`0x40`, `0x44`, `0x48`), y leer entradas de proposito general en `0x50`.
4. Los resultados que el programa transmita por UART TX se reciben en cualquier terminal serial (por ejemplo RealTerm) conectada al mismo puerto.

## External hardware

- Un adaptador USB-Serial (o el propio USB del board de desarrollo si se usa passthrough) para hablar con el pin de UART.
- Opcionalmente, un periferico SPI (memoria, display, sensor) conectado a `uio[0:3]` siguiendo la convencion estandar de Pmod (CS, MOSI, MISO, SCK).
