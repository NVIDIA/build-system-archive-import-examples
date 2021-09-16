load("@rules_cc//cc:defs.bzl", "cc_library")
load("@bazel_tools//tools/build_defs/pkg:pkg.bzl", "pkg_tar")

pkg_tar(
    name = "libnvjpeg-include",
    package_dir = "/usr/local/cuda/include",
    srcs = ["@tarball//:include/nvjpeg.h"],
    mode = "0755",
)

pkg_tar(
    name = "libnvjpeg-lib64",
    package_dir = "/usr/local/cuda/lib64",
    srcs = ["@tarball//:lib/libnvjpeg.so"],
    mode = "0755",
)

pkg_tar(
    name = "hello_pkg",
    extension = "tar.gz",
    deps = [
        ":libnvjpeg-include",
        ":libnvjpeg-lib64",
    ],
)
