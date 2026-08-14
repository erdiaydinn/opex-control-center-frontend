// EAY stable C ABI for interruptible sherpa-onnx VITS TTS.
//
// Production packaging requirement: this shim should be statically linked with the
// reviewed sherpa-onnx C API build, or every dynamic dependency must be independently
// attested. Hashing this shim alone is not sufficient to authorize drifting native
// dependencies.

#include <cstdint>
#include <cstring>
#include <new>

#include "sherpa-onnx/c-api/c-api.h"

extern "C" {

typedef int32_t (*eay_sherpa_tts_chunk_callback)(const float *samples,
                                                  int32_t n,
                                                  float progress,
                                                  void *user_data);

struct EaySherpaTtsHandle {
  const SherpaOnnxOfflineTts *tts;
  int32_t sample_rate;
};

struct EaySherpaTtsCallbackState {
  eay_sherpa_tts_chunk_callback callback;
  void *user_data;
  int32_t stopped;
};

static int32_t eay_sherpa_tts_callback_bridge(const float *samples,
                                               int32_t n,
                                               float progress,
                                               void *opaque) {
  auto *state = static_cast<EaySherpaTtsCallbackState *>(opaque);
  if (!state || !state->callback || !samples || n <= 0) {
    if (state) state->stopped = 1;
    return 0;
  }
  const int32_t keep_going =
      state->callback(samples, n, progress, state->user_data);
  if (keep_going == 0) {
    state->stopped = 1;
    return 0;
  }
  return 1;
}

int32_t eay_sherpa_tts_shim_abi_version() { return 1; }

void *eay_sherpa_tts_create_vits(const char *model_path,
                                  const char *tokens_path,
                                  const char *phonemizer_data_dir,
                                  int32_t num_threads,
                                  int32_t max_num_sentences) {
  if (!model_path || !*model_path || !tokens_path || !*tokens_path ||
      !phonemizer_data_dir || !*phonemizer_data_dir || num_threads < 1 ||
      max_num_sentences < 1) {
    return nullptr;
  }

  SherpaOnnxOfflineTtsConfig config;
  std::memset(&config, 0, sizeof(config));
  config.model.vits.model = model_path;
  config.model.vits.tokens = tokens_path;
  config.model.vits.data_dir = phonemizer_data_dir;
  config.model.vits.lexicon = "";
  config.model.vits.dict_dir = "";
  config.model.num_threads = num_threads;
  config.model.provider = "cpu";
  config.model.debug = 0;
  config.rule_fsts = "";
  config.rule_fars = "";
  config.max_num_sentences = max_num_sentences;

  const SherpaOnnxOfflineTts *tts = SherpaOnnxCreateOfflineTts(&config);
  if (!tts) return nullptr;
  const int32_t sample_rate = SherpaOnnxOfflineTtsSampleRate(tts);
  if (sample_rate <= 0) {
    SherpaOnnxDestroyOfflineTts(tts);
    return nullptr;
  }

  auto *handle = new (std::nothrow) EaySherpaTtsHandle{tts, sample_rate};
  if (!handle) {
    SherpaOnnxDestroyOfflineTts(tts);
    return nullptr;
  }
  return handle;
}

int32_t eay_sherpa_tts_sample_rate(void *opaque) {
  auto *handle = static_cast<EaySherpaTtsHandle *>(opaque);
  return handle ? handle->sample_rate : 0;
}

int32_t eay_sherpa_tts_generate(void *opaque,
                                 const char *text,
                                 int32_t sid,
                                 float speed,
                                 float silence_scale,
                                 eay_sherpa_tts_chunk_callback callback,
                                 void *user_data) {
  auto *handle = static_cast<EaySherpaTtsHandle *>(opaque);
  if (!handle || !handle->tts || !text || !*text || !callback || sid < 0 ||
      speed <= 0.0f || silence_scale < 0.0f) {
    return -1;
  }

  SherpaOnnxGenerationConfig generation;
  std::memset(&generation, 0, sizeof(generation));
  generation.sid = sid;
  generation.speed = speed;
  generation.silence_scale = silence_scale;

  EaySherpaTtsCallbackState state{callback, user_data, 0};
  const SherpaOnnxGeneratedAudio *audio = SherpaOnnxOfflineTtsGenerateWithConfig(
      handle->tts, text, &generation, eay_sherpa_tts_callback_bridge, &state);
  if (!audio) return -2;

  // The callback is the EAY data plane. The aggregate sherpa result is not copied or
  // persisted; release it immediately after generation completes/stops.
  SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
  return state.stopped ? 1 : 0;
}

void eay_sherpa_tts_destroy(void *opaque) {
  auto *handle = static_cast<EaySherpaTtsHandle *>(opaque);
  if (!handle) return;
  if (handle->tts) SherpaOnnxDestroyOfflineTts(handle->tts);
  handle->tts = nullptr;
  handle->sample_rate = 0;
  delete handle;
}

}  // extern "C"
