#include "uarths.h"
volatile unsigned constructed;
struct Startup { Startup() { constructed = 42; } } startup;
int main() { uarths_init(); uarths_puts(constructed == 42 ? "C++ ready\n" : "Constructor failed\n"); for (;;) {} }
