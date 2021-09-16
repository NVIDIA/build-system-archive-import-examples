cmake_minimum_required (VERSION 3.17)
project (CUDA)
set(CUDAToolkit_ROOT "${CMAKE_BINARY_DIR}/extracted/cuda")
find_package(CUDAToolkit)
