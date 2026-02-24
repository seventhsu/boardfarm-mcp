# Makefile for GDB Test Firmware (Baremetal/Standalone)
# For STM32H755ZI (Cortex-M7)

# Toolchain
PREFIX = arm-none-eabi-
CC = $(PREFIX)gcc
LD = $(PREFIX)ld
OBJCOPY = $(PREFIX)objcopy
OBJDUMP = $(PREFIX)objdump
SIZE = $(PREFIX)size
GDB = $(PREFIX)gdb

# Target configuration
MCU = cortex-m7
TARGET = gdb_test

# Directories
BUILD_DIR = build
SRC_DIR = .

# Source files
SRCS = main.c
STARTUP = startup_stm32h755xx.s

# Compiler flags
CFLAGS = -mcpu=$(MCU) -mthumb -mfloat-abi=hard -mfpu=fpv5-d16
CFLAGS += -g -O0  # Debug symbols, no optimization
CFLAGS += -Wall -Wextra -Werror
CFLAGS += -DSTM32H755xx
CFLAGS += -nostdlib -nostartfiles
CFLAGS += -ffunction-sections -fdata-sections
CFLAGS += -fstack-usage

# Linker flags
LDFLAGS = -mcpu=$(MCU) -mthumb -mfloat-abi=hard -mfpu=fpv5-d16
LDFLAGS += -T linker_script.ld
LDFLAGS += -Wl,--gc-sections
LDFLAGS += -Wl,-Map=$(BUILD_DIR)/$(TARGET).map

# Include paths
INCLUDES = -I.

# Object files
OBJS = $(SRCS:%.c=$(BUILD_DIR)/%.o)
OBJS += $(BUILD_DIR)/startup_stm32h755xx.o

# Default target
all: $(BUILD_DIR)/$(TARGET).elf $(BUILD_DIR)/$(TARGET).bin $(BUILD_DIR)/$(TARGET).hex

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Compile C files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Compile assembly files
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.s | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

# Link ELF
$(BUILD_DIR)/$(TARGET).elf: $(OBJS) | $(BUILD_DIR)
	$(CC) $(LDFLAGS) $(OBJS) -o $@
	$(SIZE) $@

# Generate binary
$(BUILD_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O binary $< $@

# Generate hex
$(BUILD_DIR)/$(TARGET).hex: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

# Generate assembly listing
$(BUILD_DIR)/$(TARGET).lst: $(BUILD_DIR)/$(TARGET).elf
	$(OBJDUMP) -d $< > $@

# Debug target
debug: $(BUILD_DIR)/$(TARGET).elf
	$(GDB) $(BUILD_DIR)/$(TARGET).elf

# Flash target (using pyocd)
flash: $(BUILD_DIR)/$(TARGET).hex
	pyocd flash $(BUILD_DIR)/$(TARGET).hex --target stm32h755xi

# Clean
clean:
	rm -rf $(BUILD_DIR)

# Print info
info:
	@echo "Target: $(TARGET)"
	@echo "MCU: $(MCU)"
	@echo "Sources: $(SRCS)"
	@echo "Build dir: $(BUILD_DIR)"

.PHONY: all clean debug flash info
