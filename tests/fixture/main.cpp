#include <stdint.h>
extern "C" {
volatile uint64_t initialized = UINT64_C(0x123456789abcdef0);
volatile uint64_t zeroed;
volatile uint64_t constructed;
#ifdef TEST_RETAINED
volatile uint64_t retained __attribute__((section(".retained")));
#endif
}
struct Startup {
    Startup() { constructed = initialized + zeroed; }
} startup;
int main() {
    for (;;) {
        asm volatile ("" : : "r"(initialized), "r"(zeroed), "r"(constructed));
    }
}
