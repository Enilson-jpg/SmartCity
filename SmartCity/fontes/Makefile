CC      = gcc
CFLAGS  = -Wall -Wextra -pthread
LIBS    = -lprotobuf-c

PROTO_OBJ = cidade.pb-c.o

TARGETS = sensor_temperatura \
          sensor_qualidade_ar \
          camera \
          poste \
          semaforo

.PHONY: all clean proto

all: $(TARGETS)

# Compila o objeto protobuf uma vez e reutiliza em todos os binários
$(PROTO_OBJ): cidade.pb-c.c cidade.pb-c.h
	$(CC) $(CFLAGS) -c cidade.pb-c.c -o $(PROTO_OBJ)

sensor_temperatura: sensor_temperatura.c $(PROTO_OBJ)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)

sensor_qualidade_ar: sensor_qualidade_ar.c $(PROTO_OBJ)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)

camera: camera.c $(PROTO_OBJ)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)

poste: postes.c $(PROTO_OBJ)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)

semaforo: semaforo.c $(PROTO_OBJ)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)

# Regenera os arquivos .pb-c a partir do .proto
proto:
	protoc-c --proto_path=../proto --c_out=. ../proto/cidade.proto

clean:
	rm -f $(TARGETS) $(PROTO_OBJ)