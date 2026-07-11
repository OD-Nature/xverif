#ifndef XDEBUG_CORE_NPI_DECOMPILE_COMPAT_H
#define XDEBUG_CORE_NPI_DECOMPILE_COMPAT_H

#include "npi.h"

namespace xdebug_core {
namespace detail {

// Newer Verdi releases expose the extended five-argument overload. Verdi 2018
// only exposes decompile(npiHandle, bool). Prefer the extended form when the
// installed header supports it and let overload substitution select the
// legacy form otherwise.
template <typename Decompiler>
auto decompile_npi_impl(Decompiler& decompiler, npiHandle handle, int)
    -> decltype(decompiler.decompile(handle, true, false, false, true)) {
    return decompiler.decompile(handle, true, false, false, true);
}

template <typename Decompiler>
const char* decompile_npi_impl(Decompiler& decompiler, npiHandle handle, long) {
    return decompiler.decompile(handle, true);
}

}  // namespace detail

template <typename Decompiler>
const char* decompile_npi(Decompiler& decompiler, npiHandle handle) {
    return detail::decompile_npi_impl(decompiler, handle, 0);
}

}  // namespace xdebug_core

#endif
