# Makefile for STM32H755ZI-Q bare-metal blink test
# Uses Docker to provide ARM toolchain

TARGET = h755_blink

# Docker image with ARM toolchain
DOCKER_IMAGE = zephyrprojectrtos/zephyr-build:latest

# Source files
SRCS = main.c

# Compiler flags
CFLAGS = -mcpu=cortex-m7 -mthumb -O2 -Wall -g
CFLAGS += -ffunction-sections -fdata-sections
CFLAGS += -nostdlib -nodefaultlibs

# Linker flags
LDFLAGS = -T linker.ld -Wl,--gc-sections -nostdlib

# Toolchain (inside Docker)
CC = arm-zephyr-eabi-gcc
LD = arm-zephyr-eabi-ld
OBJCOPY = arm-zephyr-eabi-objcopy
OBJDUMP = arm-zephyr-eabi-objdump

# Build with Docker
.PHONY: all clean docker-build

all: docker-build

docker-build:
	@echo "Building in Docker container..."
	@docker run --rm \
		-v $(PWD):/workspace \
		-w /workspace \
		$(DOCKER_IMAGE) \
		sh -c '$(CC) $(CFLAGS) -c main.c -o main.o && \
		       $(CC) $(CFLAGS) $(LDFLAGS) main.o -o $(TARGET).elf && \
		       $(OBJCOPY) -O binary $(TARGET).elf $(TARGET).bin && \
		       $(OBJDUMP) -h -S $(TARGET).elf > $(TARGET).lst'
	@echo "Build complete: $(TARGET).bin"
	@ls -la $(TARGET).bin

clean:
	rm -f *.o *.elf *.bin *.lst

# Host-based build (requires local toolchain)
host-build:
	arm-none-eabi-gcc $(CFLAGS) -c main.c -o main.o
	arm-none-eabi-gcc $(CFLAGS) $(LDFLAGS) main.o -o $(TARGET).elf
	arm-none-eabi-objcopy -O binary $(TARGET).elf $(TARGET).bin
