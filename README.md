RISC-V RV32I de ciclo unico, programable por UART -- Tiny Tapeout

Procesador RISC-V de 32 bits, arquitectura de ciclo unico (una instruccion por ciclo de reloj, sin segmentacion), que implementa el set de instrucciones RV32I completo. A diferencia de un diseño con memoria de programa pregrabada, este chip recibe el codigo maquina a ejecutar desde el exterior, en tiempo real, por UART -- no hay ninguna instruccion fija grabada en el silicio.

Incluye ademas un periferico SPI maestro (modo 0, 8 bits) mapeado en memoria, para que el software que se le cargue pueda comunicarse con dispositivos externos (memorias, displays, sensores) una vez en ejecucion.

📄 Lee la documentacion completa del proyecto (datasheet)

Como funciona

El chip arranca en modo LOAD, esperando recibir por UART un programa completo (el numero exacto de instrucciones de 32 bits depende de la configuracion, ver info.yaml). Al completar la carga, transiciona automaticamente a modo RUN y ejecuta el programa como cualquier procesador de ciclo unico convencional. El mismo canal UART sigue disponible durante la ejecucion para que el software transmita y reciba datos (por ejemplo, resultados de calculos), y un periferico SPI mapeado en memoria permite hablar con hardware externo.

Detalle tecnico completo, mapa de memoria, y pinout: ver docs/info.md.

Validacion

Antes de la sintesis, el diseño fue validado exhaustivamente en una FPGA (Basys3/Artix-7):

Las 37 instrucciones del set implementado, probadas individualmente y por categoria (aritmetica/logica, desplazamientos, comparaciones con y sin signo, saltos y branches, cargas/almacenamientos de byte/media palabra/palabra).
UART en tiempo real: carga de programas, y lectura/escritura interactiva desde el software en ejecucion (incluye una calculadora interactiva por teclado).
SPI maestro validado en loopback fisico.
Una prueba de estres (generacion iterativa de la serie de Fibonacci).

La misma bateria de pruebas se reproduce automaticamente en simulacion mediante cocotb (ver test/), tanto a nivel RTL como -- automaticamente, en cada build del GDS -- a nivel gate-level contra el netlist ya sintetizado.

Estructura del repositorio
src/ -- Verilog del procesador (tt_um_vanessa_riscv.v) y configuracion de sintesis (config.json).
test/ -- Testbench de cocotb.
docs/info.md -- Documentacion del proyecto (genera el datasheet).
info.yaml -- Metadatos del proyecto para Tiny Tapeout (pinout, reloj, tiles).
Sobre Tiny Tapeout

Este proyecto fue construido y enviado a fabricar a traves de Tiny Tapeout, un proyecto educativo que facilita fabricar tus propios diseños digitales y analogicos en un chip real.

Recursos
FAQ de Tiny Tapeout
Guia de diseño digital
Comunidad en Discord
