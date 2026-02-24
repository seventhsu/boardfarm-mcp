# CMakeLists.txt for GDB Test Firmware
# Compatible with Zephyr build system

cmake_minimum_required(VERSION 3.20.0)

# Find Zephyr package
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(gdb_test)

# Source files
target_sources(app PRIVATE main.c)

# Add debug symbols
zephyr_compile_options(-g -O0)

# Enable debug info
set(CMAKE_BUILD_TYPE Debug)
