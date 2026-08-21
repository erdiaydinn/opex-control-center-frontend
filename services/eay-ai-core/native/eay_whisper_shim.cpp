// EAY stable C ABI shim for whisper.cpp.
//
// Production builds must link whisper.cpp statically into this shared-library artifact
// so the SHA-256 attested by voice_runtime_attestation covers the exact Whisper code
// that executes. Do not use a dynamically drifting libwhisper beside this shim.

#include "whisper.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <new>
#include <string>
#include <vector>

#if defined(_WIN32)
#define EAY_EXPORT __declspec(dllexport)
#else
#define EAY_EXPORT __attribute__((visibility("default")))
#endif

namespace {

struct eay_whisper_handle {
    whisper_context * ctx = nullptr;
    int threads = 1;
};

static void wipe_floats(std::vector<float> & values) {
    volatile float * ptr = values.empty() ? nullptr : values.data();
    for (std::size_t i = 0; i < values.size(); ++i) {
        ptr[i] = 0.0f;
    }
}

}  // namespace

extern "C" {

EAY_EXPORT int eay_whisper_shim_abi_version() {
    return 1;
}

EAY_EXPORT const char * eay_whisper_upstream_version() {
    return whisper_version();
}

EAY_EXPORT void * eay_whisper_create(const char * model_path, int threads) {
    if (model_path == nullptr || model_path[0] == '\0' || threads < 1 || threads > 64) {
        return nullptr;
    }

    whisper_context_params params = whisper_context_default_params();
    // The deployment manifest describes local execution. GPU backends can be added as
    // a separately attested runtime later; this first executable path is CPU-only.
    params.use_gpu = false;

    whisper_context * ctx = whisper_init_from_file_with_params(model_path, params);
    if (ctx == nullptr) {
        return nullptr;
    }

    eay_whisper_handle * handle = new (std::nothrow) eay_whisper_handle();
    if (handle == nullptr) {
        whisper_free(ctx);
        return nullptr;
    }
    handle->ctx = ctx;
    handle->threads = threads;
    return handle;
}

EAY_EXPORT int eay_whisper_transcribe_pcm16(
    void * opaque_handle,
    const int16_t * pcm16,
    int sample_count,
    const char * language,
    char * output_utf8,
    int output_capacity
) {
    if (opaque_handle == nullptr || pcm16 == nullptr || sample_count <= 0 ||
        language == nullptr || language[0] == '\0' || output_utf8 == nullptr || output_capacity < 2) {
        return -1;
    }
    if (sample_count > 16000 * 120) {
        return -2;
    }
    if (whisper_lang_id(language) < 0) {
        return -3;
    }

    auto * handle = static_cast<eay_whisper_handle *>(opaque_handle);
    if (handle->ctx == nullptr) {
        return -4;
    }

    std::vector<float> pcmf32(static_cast<std::size_t>(sample_count));
    for (int i = 0; i < sample_count; ++i) {
        pcmf32[static_cast<std::size_t>(i)] = static_cast<float>(pcm16[i]) / 32768.0f;
    }

    whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    params.n_threads = handle->threads;
    params.translate = false;
    params.no_context = true;
    params.no_timestamps = true;
    params.print_special = false;
    params.print_progress = false;
    params.print_realtime = false;
    params.print_timestamps = false;
    params.language = language;
    params.detect_language = false;

    const int inference_code = whisper_full(handle->ctx, params, pcmf32.data(), sample_count);
    if (inference_code != 0) {
        wipe_floats(pcmf32);
        return -5;
    }

    std::string text;
    const int segments = whisper_full_n_segments(handle->ctx);
    for (int i = 0; i < segments; ++i) {
        const char * segment = whisper_full_get_segment_text(handle->ctx, i);
        if (segment != nullptr) {
            text.append(segment);
        }
    }
    wipe_floats(pcmf32);

    if (text.size() + 1 > static_cast<std::size_t>(output_capacity)) {
        return -6;
    }
    std::memcpy(output_utf8, text.data(), text.size());
    output_utf8[text.size()] = '\0';
    return 0;
}

EAY_EXPORT void eay_whisper_destroy(void * opaque_handle) {
    if (opaque_handle == nullptr) {
        return;
    }
    auto * handle = static_cast<eay_whisper_handle *>(opaque_handle);
    if (handle->ctx != nullptr) {
        whisper_free(handle->ctx);
        handle->ctx = nullptr;
    }
    delete handle;
}

}  // extern "C"
