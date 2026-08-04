cmake_minimum_required(VERSION 3.16)

project(yk_can_cpp VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Header-only library: all SDK code lives in include/ykcan/*.hpp.
add_library(ykcan INTERFACE)
target_include_directories(ykcan INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
if(WIN32)
  target_link_libraries(ykcan INTERFACE ws2_32)
endif()

function(ykcan_add_exe target src)
  add_executable(${target} ${src})
  target_link_libraries(${target} PRIVATE ykcan)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /permissive-)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra)
  endif()
endfunction()

ykcan_add_exe(ykcan_ctl src/main.cpp)
ykcan_add_exe(ykcan_selftest examples/selftest.cpp)
ykcan_add_exe(ykcan_decode_hex examples/decode_hex.cpp)
ykcan_add_exe(ykcan_monitor examples/monitor_feedback.cpp)
ykcan_add_exe(ykcan_basic_moves examples/basic_moves.cpp)

# Optional offline test runner registered with CTest.
enable_testing()
add_test(NAME selftest COMMAND ykcan_selftest)
set_tests_properties(selftest PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
