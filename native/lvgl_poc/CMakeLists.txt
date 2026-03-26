cmake_minimum_required(VERSION 3.16)

project(voxel_lvgl_poc C)

include(FetchContent)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(LV_CONF_PATH ${CMAKE_CURRENT_SOURCE_DIR}/lv_conf.h CACHE STRING "" FORCE)
set(LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)
set(LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)

if(DEFINED LVGL_SOURCE_DIR AND EXISTS "${LVGL_SOURCE_DIR}/CMakeLists.txt")
  add_subdirectory(${LVGL_SOURCE_DIR} ${CMAKE_BINARY_DIR}/lvgl-build)
else()
  FetchContent_Declare(
    lvgl
    GIT_REPOSITORY https://github.com/lvgl/lvgl.git
    GIT_TAG v8.3.11
  )

  FetchContent_MakeAvailable(lvgl)
endif()

add_executable(voxel_lvgl_poc main.c)
target_link_libraries(voxel_lvgl_poc PRIVATE lvgl::lvgl)

if(UNIX AND NOT APPLE)
  target_link_libraries(voxel_lvgl_poc PRIVATE m)
endif()
