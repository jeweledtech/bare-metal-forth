/* Test harness for code generation */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "floored_div.h"
#include "codegen_floored_x64.c"

int main() {
    uint8_t buf[128];
    size_t len;
    
    printf("x86-64 Floored Division Code Generation Test\n");
    printf("=============================================\n\n");
    
    /* Test floored div */
    len = emit_floored_div_x64(buf, sizeof(buf));
    printf("x64 floored div: %zu bytes\n", len);
    printf("  Hex: ");
    for (size_t i = 0; i < len; i++) printf("%02x ", buf[i]);
    printf("\n\n");
    
    /* Test floored mod */
    len = emit_floored_mod_x64(buf, sizeof(buf));
    printf("x64 floored mod: %zu bytes\n", len);
    printf("  Hex: ");
    for (size_t i = 0; i < len; i++) printf("%02x ", buf[i]);
    printf("\n\n");
    
    /* Test floored divmod */
    len = emit_floored_divmod_x64(buf, sizeof(buf));
    printf("x64 floored divmod: %zu bytes\n", len);
    printf("  Hex: ");
    for (size_t i = 0; i < len; i++) printf("%02x ", buf[i]);
    printf("\n\n");
    
    printf("Code generation successful!\n");
    return 0;
}
