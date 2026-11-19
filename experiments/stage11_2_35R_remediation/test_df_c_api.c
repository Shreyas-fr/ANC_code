#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

typedef void DFState;

extern DFState* df_create(const char* path, float atten_lim, const char* log_level);
extern size_t df_get_frame_length(DFState* st);
extern float df_process_frame(DFState* st, float* input, float* output);
extern void df_free(DFState* st);

int main(int argc, char** argv) {
    const char* model_path = (argc > 1) ? argv[1] : "models/dfn3_step500_tract.tar.gz";
    printf("Loading DFN3 model from: %s\n", model_path);

    DFState* df = df_create(model_path, 100.0f, NULL);
    if (!df) {
        fprintf(stderr, "Failed to create DFState!\n");
        return 1;
    }

    size_t frame_len = df_get_frame_length(df);
    printf("DFN3 frame length: %zu samples\n", frame_len);

    float* in_buf = (float*)calloc(frame_len, sizeof(float));
    float* out_buf = (float*)calloc(frame_len, sizeof(float));

    // Process a dummy silence frame
    float snr = df_process_frame(df, in_buf, out_buf);
    printf("Successfully processed 1 frame! Local SNR: %.2f dB\n", snr);

    free(in_buf);
    free(out_buf);
    df_free(df);
    printf("Cleanly freed DFState!\n");
    return 0;
}

