cmake_minimum_required(VERSION 3.10)
project(SVSPubSubEvaluation)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_FLAGS "-pedantic -Wall -Werror -Wextra -Wno-unused-parameter -Wno-unused-variable -Wno-unused-but-set-variable -Wno-error=unused-variable -Wno-error=unused-but-set-variable -fdiagnostics-color -Wno-error=deprecated-declarations")

find_package(PkgConfig REQUIRED)

# Check if NDN-CXX is installed
pkg_check_modules(NDN_CXX REQUIRED libndn-cxx)
#include_directories(${NDN_CXX_INCLUDE_DIRS})

pkg_check_modules(NDN_SVS REQUIRED libndn-svs)
#include_directories(${NDN_SVS_INCLUDE_DIRS})

# Check if Boost and all components are installed
FIND_PACKAGE(Boost 1.65 COMPONENTS system thread program_options filesystem iostreams REQUIRED)

add_executable(SVSClient svs-client.cpp)
target_link_libraries(SVSClient
        PUBLIC
        ${NDN_CXX_LIBRARIES} ${NDN_SVS_LIBRARIES}
        )
target_include_directories(SVSClient
        PUBLIC
        ${CMAKE_CURRENT_BINARY_DIR}
        ${NDN_CXX_INCLUDE_DIRS} ${NDN_SVS_INCLUDE_DIRS}
        )