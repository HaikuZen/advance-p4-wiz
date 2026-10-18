/* digit_prep.c - what MNIST did to its scans, done to a finger drawing: the ink
 * cropped, scaled (area average, aspect kept) so its longer side is 20 px, then
 * placed in 28x28 with its centre of mass in the middle. */
#include "digit_prep.h"
#include <math.h>
#include <string.h>

#define BOX 20

bool digit_prep(const uint8_t *ink, int w, int h, uint8_t out[DIGIT_IN * DIGIT_IN])
{
    int x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++)
            if (ink[y * w + x]) {
                if (x < x0) x0 = x;
                if (x > x1) x1 = x;
                if (y < y0) y0 = y;
                if (y > y1) y1 = y;
            }
    memset(out, 0, DIGIT_IN * DIGIT_IN);
    if (x1 < 0) return false;

    int bw = x1 - x0 + 1, bh = y1 - y0 + 1, side = bw > bh ? bw : bh;
    int tw = (bw * BOX + side / 2) / side, th = (bh * BOX + side / 2) / side;
    if (tw < 1) tw = 1;
    if (th < 1) th = 1;

    /* each target pixel = the share of inked source pixels under it */
    uint8_t box[BOX * BOX];
    float mass = 0, mx = 0, my = 0;
    for (int ty = 0; ty < th; ty++) {
        int sy0 = y0 + ty * bh / th, sy1 = y0 + (ty + 1) * bh / th;
        if (sy1 == sy0) sy1++;
        for (int tx = 0; tx < tw; tx++) {
            int sx0 = x0 + tx * bw / tw, sx1 = x0 + (tx + 1) * bw / tw;
            if (sx1 == sx0) sx1++;
            int n = 0;
            for (int sy = sy0; sy < sy1; sy++)
                for (int sx = sx0; sx < sx1; sx++)
                    n += ink[sy * w + sx] != 0;
            int v = n * 255 / ((sy1 - sy0) * (sx1 - sx0));
            box[ty * BOX + tx] = (uint8_t)v;
            mass += v; mx += v * tx; my += v * ty;
        }
    }

    /* shift so the centre of mass (of pixel centres) lands on the 28x28 centre */
    int ox = (int)lroundf(DIGIT_IN / 2.0f - (mx / mass + 0.5f));
    int oy = (int)lroundf(DIGIT_IN / 2.0f - (my / mass + 0.5f));
    for (int ty = 0; ty < th; ty++)
        for (int tx = 0; tx < tw; tx++) {
            int x = tx + ox, y = ty + oy;
            if (x >= 0 && x < DIGIT_IN && y >= 0 && y < DIGIT_IN) out[y * DIGIT_IN + x] = box[ty * BOX + tx];
        }
    return true;
}
