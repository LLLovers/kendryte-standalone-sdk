find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME k210_sdk_contract
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/integration.py"
        --sdk "${K210_SDK_PATH}" --toolchain "${K210_TOOLCHAIN_PATH}")
set_tests_properties(k210_sdk_contract PROPERTIES TIMEOUT 180)
