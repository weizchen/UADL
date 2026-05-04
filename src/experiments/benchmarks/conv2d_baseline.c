// Phase D Benchmark: 2D Convolution (Gaussian blur, 3x3 kernel)
// Baseline — naive triple-nested loop, kernel in stack array, multiplies in
// the hot path. Stresses cache locality (image stride > L1 line) and exposes
// the no-MUL bottleneck for ISAs without the M extension.

#define W 16
#define H 16

int main() {
  volatile int *img = (volatile int *)400;
  volatile int *out = (volatile int *)(400 + W * H * 4);

  // Gaussian-style 3x3 kernel; sum = 16, normalize with >> 4.
  int kernel[9] = {1, 2, 1,
                   2, 4, 2,
                   1, 2, 1};

  // Initialize image with a deterministic pattern.
  for (int i = 0; i < W * H; i++) {
    img[i] = i;
  }

  // 3x3 convolution, no padding. Output dims = (W-2) x (H-2).
  for (int i = 0; i < H - 2; i++) {
    for (int j = 0; j < W - 2; j++) {
      int sum = 0;
      for (int ki = 0; ki < 3; ki++) {
        for (int kj = 0; kj < 3; kj++) {
          sum = sum + img[(i + ki) * W + (j + kj)] * kernel[ki * 3 + kj];
        }
      }
      out[i * (W - 2) + j] = sum >> 4;
    }
  }

  return out[0];
}
