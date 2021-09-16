# CMake example 1: FindCUDAToolkit

FindCUDAToolkit is the recommended module for importing CUDA components into the CMake build system (3.17 and newer).

The path to the extraction location can be specified with `-DCUDAToolkit_ROOT=$PWD/extracted` or the `CUDAToolkit_ROOT` environmental variable

> **NOTE:** The minimum required components for the FindCUDAToolkit module are `cuda_cudart` and `cuda_nvcc`.

## Commands

```shell
mkdir extracted
cd extracted
tar -xf cuda_nvcc-linux-x86_64-*-archive.tar.xz
tar -xf cuda_nvcc-linux-x86_64-*-archive.tar.xz
mkdir cuda
rsync -av *-archive/ cuda/
cd ..
cmake .
```
