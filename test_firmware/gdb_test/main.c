/* GDB Test Firmware for STM32H755ZI
 * 
 * This test program includes:
 * - Multiple functions for call stack testing
 * - Local and global variables
 * - Loops for breakpoint testing
 * - Debug symbols (compile with -g)
 */

#include <stdint.h>
#include <stdbool.h>

// Global variables for testing
volatile uint32_t g_counter = 0;
volatile uint32_t g_iterations = 0;
volatile int g_result = 0;
static int s_private_var = 42;

// Test structure
struct TestStruct {
    int a;
    int b;
    int sum;
};

static struct TestStruct g_test_data = {10, 20, 0};

// Function prototypes
void delay_loop(uint32_t count);
int add_numbers(int a, int b);
int multiply_numbers(int a, int b);
int calculate_result(int x, int y, int z);
void update_global(void);
void test_struct_operations(void);
void infinite_loop(void);

// Simple delay function for timing tests
void delay_loop(uint32_t count) {
    volatile uint32_t i;
    for (i = 0; i < count; i++) {
        // Prevent optimization
        __asm__("nop");
    }
}

// Basic arithmetic function
int add_numbers(int a, int b) {
    int result = a + b;
    return result;
}

// Another arithmetic function
int multiply_numbers(int a, int b) {
    int product = a * b;
    return product;
}

// More complex function with multiple locals
int calculate_result(int x, int y, int z) {
    int temp1 = add_numbers(x, y);
    int temp2 = multiply_numbers(temp1, z);
    int final = temp2 + s_private_var;
    return final;
}

// Function to update global variables
void update_global(void) {
    g_counter++;
    g_iterations += 10;
    g_result = (int)g_counter + (int)g_iterations;
}

// Function with structure operations
void test_struct_operations(void) {
    struct TestStruct local;
    local.a = g_test_data.a;
    local.b = g_test_data.b;
    local.sum = add_numbers(local.a, local.b);
    g_test_data.sum = local.sum;
}

// Infinite loop for debugging pause/resume tests
void infinite_loop(void) {
    uint32_t local_counter = 0;
    
    while (1) {
        local_counter++;
        g_counter = local_counter;
        
        // Call function to create call stack depth
        update_global();
        
        // Small delay
        delay_loop(1000);
        
        // Reset counter periodically
        if (local_counter > 1000000) {
            local_counter = 0;
        }
    }
}

// Main entry point
int main(void) {
    // Initialize system
    int local_var = 5;
    int result = 0;
    
    // Initial setup breakpoint location
    __asm__("nop");  // Breakpoint here for initial stop
    
    // Test basic arithmetic
    result = add_numbers(local_var, 10);
    g_result = result;
    
    // Test nested function calls
    result = calculate_result(1, 2, 3);
    g_result = result;
    
    // Test structure operations
    test_struct_operations();
    
    // Main loop with multiple breakpoints possible
    while (1) {
        // Location for breakpoint testing inside loop
        update_global();
        
        // Different code paths for step testing
        if (g_counter % 2 == 0) {
            result = add_numbers((int)g_counter, 1);
        } else {
            result = multiply_numbers((int)g_counter, 2);
        }
        
        g_result = result;
        
        // Variable timing delay
        delay_loop(g_iterations + 1000);
    }
    
    return 0;  // Never reached
}
