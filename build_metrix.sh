#!/bin/bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

boost_prefix=${BOOST_PREFIX:-$(brew --prefix boost 2>/dev/null || true)}
if [[ -z "$boost_prefix" || ! -f "$boost_prefix/include/boost/version.hpp" ]]; then
  echo "Boost est introuvable. Installe Boost (par exemple : brew install boost) ou définis BOOST_PREFIX." >&2
  exit 1
fi
for component in program_options log filesystem; do
  if [[ ! -f "$boost_prefix/lib/libboost_${component}.a" ]]; then
    echo "Bibliothèque Boost statique manquante : $boost_prefix/lib/libboost_${component}.a" >&2
    exit 1
  fi
done

build_metrix() (
  name=$1; cc=$2; cxx=$3
  dir="metrix-simulator/build-$name"
  export CC="$(command -v "$cc")"
  export CXX="$(command -v "$cxx")"
  if [[ -z "$CC" || -z "$CXX" ]]; then
    echo "Compilateur introuvable : $cc ou $cxx" >&2
    exit 1
  fi

  cxx_flags=${CXXFLAGS:-}
  link_flags=
  if [[ "$name" == clang ]]; then
    gcc_cxx=$(command -v g++-16)
    gcc_install_dir=${CLANG_GCC_INSTALL_DIR:-$(dirname "$("$gcc_cxx" -print-libgcc-file-name)")}
    gcc_install_dir=$(realpath "$gcc_install_dir")
    gcc_lib_dir=$(realpath "$gcc_install_dir/../../..")
    gcc_include_dir="$(brew --prefix gcc)/include/c++/$("$gcc_cxx" -dumpversion)"
    gcc_target_include_dir="$gcc_include_dir/$("$gcc_cxx" -dumpmachine)"
    brew_prefix=$(brew --prefix)
    if [[ ! -f "$gcc_lib_dir/libstdc++.so" || ! -d "$gcc_target_include_dir" ]]; then
      echo "Installation C++ de GCC 16 introuvable pour clang++." >&2
      exit 1
    fi
    cxx_flags="${cxx_flags:+$cxx_flags }--gcc-install-dir=$gcc_install_dir"
    cxx_flags="$cxx_flags -isystem $gcc_include_dir -isystem $gcc_target_include_dir"
    cxx_flags="$cxx_flags -isystem $brew_prefix/opt/glibc/include"
    link_flags="-L$brew_prefix/opt/glibc/lib -L$gcc_lib_dir"
    link_flags="$link_flags -Wl,--dynamic-linker=$brew_prefix/lib/ld.so"
    link_flags="$link_flags -Wl,-rpath,$brew_prefix/lib/gcc/current -Wl,-rpath,$brew_prefix/lib"
  fi

  simulator_cxx_flags="${cxx_flags:+$cxx_flags }-Wno-error=unused-but-set-variable"

  cmake -S metrix-simulator/external -B "$dir/external" \
    -DCMAKE_C_COMPILER="$CC" \
    -DCMAKE_CXX_COMPILER="$CXX" \
    -DCMAKE_CXX_FLAGS="$cxx_flags" \
    -DCMAKE_EXE_LINKER_FLAGS="$link_flags" \
    -DCMAKE_SHARED_LINKER_FLAGS="$link_flags" \
    -DCMAKE_BUILD_TYPE=Release
  cmake --build "$dir/external" --parallel 2

  cmake -S metrix-simulator -B "$dir" \
    -DCMAKE_C_COMPILER="$CC" \
    -DCMAKE_CXX_COMPILER="$CXX" \
    -DCMAKE_CXX_FLAGS="$simulator_cxx_flags" \
    -DCMAKE_EXE_LINKER_FLAGS="$link_flags" \
    -DCMAKE_SHARED_LINKER_FLAGS="$link_flags" \
    -DBoost_ROOT="$boost_prefix" \
    -DCMAKE_BUILD_TYPE=Release
  cmake --build "$dir" --parallel 2
  # ctest --test-dir "$dir" --output-on-failure
)

case ${1:-all} in
  gcc16) build_metrix gcc16 gcc-16 g++-16 ;;
  clang) build_metrix clang clang clang++ ;;
  all)
    build_metrix gcc16 gcc-16 g++-16
    build_metrix clang clang clang++
    ;;
  *)
    echo "Usage : $0 [gcc16|clang|all]" >&2
    exit 2
    ;;
esac
