cmake_minimum_required(VERSION 3.16)
project(robot_mock_backend LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)
FetchContent_Declare(
  Crow
  GIT_REPOSITORY https://github.com/CrowCpp/Crow.git
  GIT_TAG v1.3.2
)
FetchContent_MakeAvailable(Crow)

add_executable(robot_mock_backend src/main.cpp)
target_link_libraries(robot_mock_backend PRIVATE Crow::Crow)

if(WIN32)
  target_link_libraries(robot_mock_backend PRIVATE ws2_32 mswsock)
endif()
