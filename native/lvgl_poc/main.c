#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lvgl.h"

#define WIDTH 240
#define HEIGHT 280
#define FRAME_PIXELS (WIDTH * HEIGHT)

static uint16_t framebuffer[FRAME_PIXELS];
static lv_color_t draw_buf_pixels[WIDTH * 24];

typedef struct {
    lv_obj_t *ambient;
    lv_obj_t *shell;
    lv_obj_t *status_left;
    lv_obj_t *status_right;
    lv_obj_t *status_dot;
    lv_obj_t *cube_wrap;
    lv_obj_t *cube;
    lv_obj_t *front;
    lv_obj_t *top;
    lv_obj_t *side;
    lv_obj_t *edge_top;
    lv_obj_t *edge_bottom;
    lv_obj_t *edge_left;
    lv_obj_t *edge_right;
    lv_obj_t *eye_left;
    lv_obj_t *eye_right;
    lv_obj_t *mouth;
    lv_obj_t *mood_chip;
    lv_obj_t *mood_label;
    lv_obj_t *pill;
    lv_obj_t *pill_fill;
    lv_obj_t *footer;
} ui_t;

typedef struct {
    const char *label;
    const char *status_right;
    lv_color_t bg_top;
    lv_color_t bg_bottom;
    lv_color_t cube_front;
    lv_color_t cube_top;
    lv_color_t cube_side;
    lv_color_t accent;
    lv_color_t text_dim;
    lv_color_t chip_bg;
    int ambient_opa;
    int cube_base_y;
    int cube_scale_pct;
    int eye_gap;
    int eye_w;
    int eye_left_h;
    int eye_right_h;
    int eye_base_y;
    int mouth_base_w;
    int mouth_base_h;
    int mouth_base_y;
    int mouth_radius;
    int pill_pct;
    float bounce_amp;
    float gaze_amp_x;
    float gaze_amp_y;
    float speak_amp;
    int blink_frame;
} mood_spec_t;

static const mood_spec_t MOODS[] = {
    {"IDLE",   "88%",  LV_COLOR_MAKE(0x06,0x08,0x0F), LV_COLOR_MAKE(0x0D,0x16,0x25), LV_COLOR_MAKE(0x1A,0x1A,0x2E), LV_COLOR_MAKE(0x2A,0x2A,0x46), LV_COLOR_MAKE(0x12,0x12,0x20), LV_COLOR_MAKE(0x00,0xD4,0xD2), LV_COLOR_MAKE(0x84,0xA2,0xB2), LV_COLOR_MAKE(0x10,0x2A,0x36), 26, 0, 100, 16, 18, 34, 34, -6, 18, 8, 22, 4, 10, 2.0f, 1.5f, 1.0f, 0.0f, 2},
    {"HAPPY",  "88%",  LV_COLOR_MAKE(0x08,0x0B,0x12), LV_COLOR_MAKE(0x13,0x22,0x28), LV_COLOR_MAKE(0x1C,0x1E,0x30), LV_COLOR_MAKE(0x2F,0x31,0x4C), LV_COLOR_MAKE(0x14,0x16,0x22), LV_COLOR_MAKE(0x52,0xF3,0xFF), LV_COLOR_MAKE(0x98,0xB7,0xC4), LV_COLOR_MAKE(0x12,0x34,0x3F), 36, -2, 102, 18, 22, 24, 24, -8, 30, 6, 22, 3, 16, 3.0f, 1.0f, 0.6f, 0.0f, -1},
    {"CURIOUS","SCAN", LV_COLOR_MAKE(0x07,0x0D,0x14), LV_COLOR_MAKE(0x12,0x1D,0x30), LV_COLOR_MAKE(0x1A,0x1C,0x2E), LV_COLOR_MAKE(0x2C,0x2F,0x48), LV_COLOR_MAKE(0x13,0x15,0x22), LV_COLOR_MAKE(0x7A,0xEE,0xFF), LV_COLOR_MAKE(0x88,0xB9,0xC9), LV_COLOR_MAKE(0x14,0x30,0x46), 34, -1, 101, 18, 20, 40, 36, -8, 14, 10, 24, 5, 20, 2.0f, 3.0f, 1.8f, 0.0f, -1},
    {"THINK",  "SYNC", LV_COLOR_MAKE(0x09,0x0B,0x12), LV_COLOR_MAKE(0x16,0x13,0x25), LV_COLOR_MAKE(0x18,0x1A,0x28), LV_COLOR_MAKE(0x26,0x26,0x42), LV_COLOR_MAKE(0x11,0x13,0x23), LV_COLOR_MAKE(0xB8,0x98,0xFF), LV_COLOR_MAKE(0xA5,0x9C,0xB8), LV_COLOR_MAKE(0x2E,0x1D,0x49), 30, -3, 101, 14, 18, 34, 18, -6, 16, 6, 24, 3, 24, 1.0f, 1.5f, 0.8f, 0.0f, -1},
    {"LISTEN", "LIVE", LV_COLOR_MAKE(0x07,0x10,0x16), LV_COLOR_MAKE(0x0D,0x24,0x30), LV_COLOR_MAKE(0x1B,0x1F,0x30), LV_COLOR_MAKE(0x30,0x36,0x52), LV_COLOR_MAKE(0x15,0x17,0x24), LV_COLOR_MAKE(0x40,0xFF,0xF8), LV_COLOR_MAKE(0x7F,0xB7,0xC3), LV_COLOR_MAKE(0x11,0x38,0x44), 42, -2, 103, 18, 20, 38, 38, -8, 12, 10, 24, 5, 22, 2.0f, 1.2f, 0.6f, 0.0f, -1},
    {"SPEAK",  "TALK", LV_COLOR_MAKE(0x07,0x11,0x1A), LV_COLOR_MAKE(0x09,0x36,0x40), LV_COLOR_MAKE(0x19,0x20,0x2B), LV_COLOR_MAKE(0x2E,0x33,0x49), LV_COLOR_MAKE(0x11,0x18,0x20), LV_COLOR_MAKE(0x40,0xFF,0xF8), LV_COLOR_MAKE(0x7E,0xC6,0xD1), LV_COLOR_MAKE(0x13,0x3A,0x42), 58, -5, 104, 16, 18, 34, 34, -7, 14, 10, 24, 7, 82, 3.5f, 1.0f, 0.5f, 1.0f, -1},
};

static void flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_p) {
    for (int y = area->y1; y <= area->y2; y++) {
        int width = area->x2 - area->x1 + 1;
        uint16_t *dst = &framebuffer[y * WIDTH + area->x1];
        const lv_color_t *src = color_p + (y - area->y1) * width;
        for (int x = 0; x < width; x++) {
            dst[x] = src[x].full;
        }
    }
    lv_disp_flush_ready(drv);
}

static int ensure_dir(const char *path) {
    char command[1024];
    snprintf(command, sizeof(command), "mkdir -p \"%s\"", path);
    return system(command);
}

static int write_frame(const char *dir, int index) {
    char path[1024];
    snprintf(path, sizeof(path), "%s/frame-%03d.rgb565", dir, index);
    FILE *fp = fopen(path, "wb");
    if (!fp) {
        fprintf(stderr, "Failed to open %s: %s\n", path, strerror(errno));
        return 1;
    }
    for (size_t i = 0; i < FRAME_PIXELS; i++) {
        uint16_t pixel = framebuffer[i];
        uint8_t bytes[2] = {(uint8_t)((pixel >> 8) & 0xFF), (uint8_t)(pixel & 0xFF)};
        if (fwrite(bytes, 1, 2, fp) != 2) {
            fprintf(stderr, "Failed to write frame %d\n", index);
            fclose(fp);
            return 1;
        }
    }
    fclose(fp);
    return 0;
}

static int write_manifest(const char *dir, const char **labels, int frames) {
    char path[1024];
    snprintf(path, sizeof(path), "%s/manifest.txt", dir);
    FILE *fp = fopen(path, "w");
    if (!fp) return 1;
    for (int i = 0; i < frames; i++) {
        fprintf(fp, "frame-%03d.rgb565 %s\n", i, labels[i]);
    }
    fclose(fp);
    return 0;
}

static void style_rect(lv_obj_t *obj, lv_color_t bg, int radius, int border_width, lv_color_t border) {
    lv_obj_set_style_bg_color(obj, bg, 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(obj, border_width, 0);
    lv_obj_set_style_border_color(obj, border, 0);
    lv_obj_set_style_radius(obj, radius, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_clear_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
}

static void setup_ui(ui_t *ui) {
    lv_obj_t *screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, MOODS[0].bg_top, 0);
    lv_obj_set_style_bg_grad_color(screen, MOODS[0].bg_bottom, 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);

    ui->ambient = lv_obj_create(screen);
    lv_obj_set_size(ui->ambient, 160, 160);
    lv_obj_align(ui->ambient, LV_ALIGN_CENTER, 0, -4);
    style_rect(ui->ambient, MOODS[0].accent, 80, 0, MOODS[0].accent);
    lv_obj_set_style_bg_opa(ui->ambient, MOODS[0].ambient_opa, 0);

    ui->shell = lv_obj_create(screen);
    lv_obj_set_size(ui->shell, 236, 280);
    lv_obj_align(ui->shell, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_bg_opa(ui->shell, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ui->shell, 0, 0);
    lv_obj_set_style_pad_all(ui->shell, 0, 0);
    lv_obj_clear_flag(ui->shell, LV_OBJ_FLAG_SCROLLABLE);

    ui->status_left = lv_label_create(ui->shell);
    lv_label_set_text(ui->status_left, "daemon");
    lv_obj_set_style_text_font(ui->status_left, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->status_left, lv_color_hex(0xE2EEF6), 0);
    lv_obj_align(ui->status_left, LV_ALIGN_TOP_LEFT, 16, 10);

    ui->status_right = lv_label_create(ui->shell);
    lv_label_set_text(ui->status_right, MOODS[0].status_right);
    lv_obj_set_style_text_font(ui->status_right, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->status_right, MOODS[0].text_dim, 0);
    lv_obj_align(ui->status_right, LV_ALIGN_TOP_RIGHT, -16, 10);

    ui->status_dot = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->status_dot, 8, 8);
    style_rect(ui->status_dot, MOODS[0].accent, 4, 0, MOODS[0].accent);
    lv_obj_align(ui->status_dot, LV_ALIGN_TOP_MID, 0, 16);

    ui->cube_wrap = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->cube_wrap, 150, 170);
    lv_obj_align(ui->cube_wrap, LV_ALIGN_CENTER, 0, -8);
    lv_obj_set_style_bg_opa(ui->cube_wrap, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ui->cube_wrap, 0, 0);
    lv_obj_set_style_pad_all(ui->cube_wrap, 0, 0);
    lv_obj_clear_flag(ui->cube_wrap, LV_OBJ_FLAG_SCROLLABLE);

    ui->cube = lv_obj_create(ui->cube_wrap);
    lv_obj_set_size(ui->cube, 130, 130);
    lv_obj_align(ui->cube, LV_ALIGN_CENTER, 0, 12);
    lv_obj_set_style_bg_opa(ui->cube, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ui->cube, 0, 0);
    lv_obj_clear_flag(ui->cube, LV_OBJ_FLAG_SCROLLABLE);

    ui->top = lv_obj_create(ui->cube);
    lv_obj_set_size(ui->top, 104, 28);
    lv_obj_align(ui->top, LV_ALIGN_TOP_MID, 2, 2);
    style_rect(ui->top, MOODS[0].cube_top, 16, 0, MOODS[0].cube_top);

    ui->side = lv_obj_create(ui->cube);
    lv_obj_set_size(ui->side, 34, 104);
    lv_obj_align(ui->side, LV_ALIGN_RIGHT_MID, -1, 8);
    style_rect(ui->side, MOODS[0].cube_side, 16, 0, MOODS[0].cube_side);

    ui->front = lv_obj_create(ui->cube);
    lv_obj_set_size(ui->front, 130, 130);
    lv_obj_align(ui->front, LV_ALIGN_CENTER, 0, 12);
    style_rect(ui->front, MOODS[0].cube_front, 16, 0, MOODS[0].cube_front);

    ui->edge_top = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_top, 106, 2);
    style_rect(ui->edge_top, MOODS[0].accent, 2, 0, MOODS[0].accent);
    lv_obj_align(ui->edge_top, LV_ALIGN_TOP_MID, 0, 0);
    ui->edge_bottom = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_bottom, 106, 2);
    style_rect(ui->edge_bottom, MOODS[0].accent, 2, 0, MOODS[0].accent);
    lv_obj_align(ui->edge_bottom, LV_ALIGN_BOTTOM_MID, 0, 0);
    ui->edge_left = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_left, 2, 106);
    style_rect(ui->edge_left, MOODS[0].accent, 2, 0, MOODS[0].accent);
    lv_obj_align(ui->edge_left, LV_ALIGN_LEFT_MID, 0, 0);
    ui->edge_right = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_right, 2, 106);
    style_rect(ui->edge_right, MOODS[0].accent, 2, 0, MOODS[0].accent);
    lv_obj_align(ui->edge_right, LV_ALIGN_RIGHT_MID, 0, 0);

    ui->eye_left = lv_obj_create(ui->front);
    style_rect(ui->eye_left, lv_color_hex(0xF0F0F0), 12, 0, lv_color_hex(0xF0F0F0));
    ui->eye_right = lv_obj_create(ui->front);
    style_rect(ui->eye_right, lv_color_hex(0xF0F0F0), 12, 0, lv_color_hex(0xF0F0F0));

    ui->mouth = lv_obj_create(ui->front);
    style_rect(ui->mouth, lv_color_hex(0xF0F0F0), 5, 0, lv_color_hex(0xF0F0F0));

    ui->mood_chip = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->mood_chip, 76, 24);
    lv_obj_align(ui->mood_chip, LV_ALIGN_BOTTOM_MID, 0, -42);
    style_rect(ui->mood_chip, MOODS[0].chip_bg, 12, 1, MOODS[0].accent);
    ui->mood_label = lv_label_create(ui->mood_chip);
    lv_label_set_text(ui->mood_label, MOODS[0].label);
    lv_obj_set_style_text_font(ui->mood_label, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->mood_label, lv_color_hex(0xD7F9FF), 0);
    lv_obj_center(ui->mood_label);

    ui->pill = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->pill, 176, 18);
    lv_obj_align(ui->pill, LV_ALIGN_BOTTOM_MID, 0, -16);
    style_rect(ui->pill, lv_color_hex(0x0D1820), 9, 1, lv_color_hex(0x17303D));
    ui->pill_fill = lv_obj_create(ui->pill);
    lv_obj_set_size(ui->pill_fill, 12, 10);
    style_rect(ui->pill_fill, MOODS[0].accent, 5, 0, MOODS[0].accent);
    lv_obj_align(ui->pill_fill, LV_ALIGN_LEFT_MID, 4, 0);

    ui->footer = lv_label_create(ui->shell);
    lv_label_set_text(ui->footer, "interactive mood preview");
    lv_obj_set_style_text_font(ui->footer, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->footer, MOODS[0].text_dim, 0);
    lv_obj_align(ui->footer, LV_ALIGN_BOTTOM_MID, 0, 6);
}

static void apply_pose(ui_t *ui, const mood_spec_t *mood, float phase) {
    lv_obj_t *screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, mood->bg_top, 0);
    lv_obj_set_style_bg_grad_color(screen, mood->bg_bottom, 0);

    float bounce = sinf(phase * 6.28318f) * mood->bounce_amp;
    float gaze_x = sinf(phase * 6.28318f * 0.85f) * mood->gaze_amp_x;
    float gaze_y = cosf(phase * 6.28318f * 0.63f) * mood->gaze_amp_y;
    float speak = mood->speak_amp > 0.0f ? (sinf(phase * 6.28318f * 2.4f) * 0.5f + 0.5f) : 0.0f;

    int eye_left_h = mood->eye_left_h;
    int eye_right_h = mood->eye_right_h;
    if (mood->blink_frame >= 0 && ((int)lroundf(phase * 3.0f) % 4) == mood->blink_frame) {
        eye_left_h = 6;
        eye_right_h = 6;
    }

    int cube_size = 130 * mood->cube_scale_pct / 100;
    lv_obj_set_style_bg_opa(ui->ambient, mood->ambient_opa, 0);
    lv_obj_set_style_bg_color(ui->ambient, mood->accent, 0);
    lv_obj_set_style_bg_color(ui->status_dot, mood->accent, 0);
    lv_obj_set_style_bg_color(ui->edge_top, mood->accent, 0);
    lv_obj_set_style_bg_color(ui->edge_bottom, mood->accent, 0);
    lv_obj_set_style_bg_color(ui->edge_left, mood->accent, 0);
    lv_obj_set_style_bg_color(ui->edge_right, mood->accent, 0);
    lv_obj_set_style_bg_color(ui->pill_fill, mood->accent, 0);
    lv_obj_set_style_bg_color(ui->front, mood->cube_front, 0);
    lv_obj_set_style_bg_color(ui->top, mood->cube_top, 0);
    lv_obj_set_style_bg_color(ui->side, mood->cube_side, 0);
    lv_obj_set_style_bg_color(ui->mood_chip, mood->chip_bg, 0);
    lv_obj_set_style_border_color(ui->mood_chip, lv_color_mix(mood->accent, lv_color_hex(0xFFFFFF), LV_OPA_20), 0);
    lv_obj_set_style_text_color(ui->status_right, mood->text_dim, 0);
    lv_obj_set_style_text_color(ui->footer, mood->text_dim, 0);

    lv_label_set_text(ui->status_right, mood->status_right);
    lv_label_set_text(ui->mood_label, mood->label);

    lv_obj_align(ui->cube_wrap, LV_ALIGN_CENTER, 0, -8 + mood->cube_base_y + (int)lroundf(bounce));
    lv_obj_set_size(ui->cube, cube_size, cube_size);
    lv_obj_align(ui->cube, LV_ALIGN_CENTER, 0, 12);
    lv_obj_set_size(ui->front, cube_size, cube_size);
    lv_obj_align(ui->front, LV_ALIGN_CENTER, 0, 12);

    int top_w = (cube_size * 104) / 130;
    int top_h = (cube_size * 28) / 130;
    lv_obj_set_size(ui->top, top_w, top_h);
    lv_obj_align(ui->top, LV_ALIGN_TOP_MID, 2, 2);
    lv_obj_set_size(ui->side, (cube_size * 34) / 130, (cube_size * 104) / 130);
    lv_obj_align(ui->side, LV_ALIGN_RIGHT_MID, -1, 8);

    int edge_w = (cube_size * 106) / 130;
    int edge_h = (cube_size * 106) / 130;
    lv_obj_set_size(ui->edge_top, edge_w, 2);
    lv_obj_set_size(ui->edge_bottom, edge_w, 2);
    lv_obj_set_size(ui->edge_left, 2, edge_h);
    lv_obj_set_size(ui->edge_right, 2, edge_h);

    int eye_w = mood->eye_w;
    int left_x = -(mood->eye_gap / 2) - eye_w / 2 + (int)lroundf(gaze_x);
    int right_x = (mood->eye_gap / 2) + eye_w / 2 + (int)lroundf(gaze_x);
    int eye_y = mood->eye_base_y + (int)lroundf(gaze_y);
    lv_obj_set_size(ui->eye_left, eye_w, eye_left_h);
    lv_obj_set_size(ui->eye_right, eye_w, eye_right_h);
    lv_obj_set_style_radius(ui->eye_left, LV_MIN(eye_w / 2 + 2, 14), 0);
    lv_obj_set_style_radius(ui->eye_right, LV_MIN(eye_w / 2 + 2, 14), 0);
    lv_obj_align(ui->eye_left, LV_ALIGN_CENTER, left_x, eye_y);
    lv_obj_align(ui->eye_right, LV_ALIGN_CENTER, right_x, eye_y);

    int mouth_h = mood->mouth_base_h + (int)lroundf(speak * mood->speak_amp * 10.0f);
    int mouth_w = mood->mouth_base_w - (int)lroundf(speak * mood->speak_amp * 4.0f);
    lv_obj_set_size(ui->mouth, mouth_w, mouth_h);
    lv_obj_set_style_radius(ui->mouth, mood->mouth_radius, 0);
    lv_obj_align(ui->mouth, LV_ALIGN_CENTER, 0, mood->mouth_base_y);

    int pill_width = 8 + (mood->pill_pct * 164 / 100);
    lv_obj_set_size(ui->pill_fill, pill_width, 10);
    lv_obj_align(ui->pill_fill, LV_ALIGN_LEFT_MID, 4, 0);
}

int main(int argc, char **argv) {
    const char *out_dir = argc > 1 ? argv[1] : "./lvgl_frames";
    int frames = argc > 2 ? atoi(argv[2]) : 24;
    if (frames < 1) frames = 1;

    if (ensure_dir(out_dir) != 0) {
        fprintf(stderr, "Failed to create output dir %s\n", out_dir);
        return 1;
    }

    memset(framebuffer, 0, sizeof(framebuffer));
    lv_init();

    lv_disp_draw_buf_t draw_buf;
    lv_disp_draw_buf_init(&draw_buf, draw_buf_pixels, NULL, WIDTH * 24);
    lv_disp_drv_t disp_drv;
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = WIDTH;
    disp_drv.ver_res = HEIGHT;
    disp_drv.flush_cb = flush_cb;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);

    ui_t ui;
    memset(&ui, 0, sizeof(ui));
    setup_ui(&ui);

    const int mood_count = (int)(sizeof(MOODS) / sizeof(MOODS[0]));
    const char **labels = malloc(sizeof(char *) * (size_t)frames);
    if (!labels) return 1;

    for (int i = 0; i < frames; i++) {
        int mood_index = (i * mood_count) / frames;
        if (mood_index >= mood_count) mood_index = mood_count - 1;
        int start = (mood_index * frames) / mood_count;
        int end = ((mood_index + 1) * frames) / mood_count;
        int span = end - start;
        if (span < 1) span = 1;
        float phase = (float)(i - start) / (float)span;

        apply_pose(&ui, &MOODS[mood_index], phase);
        labels[i] = MOODS[mood_index].label;

        lv_tick_inc(16);
        lv_timer_handler();

        if (write_frame(out_dir, i) != 0) {
            free(labels);
            return 1;
        }
    }

    if (write_manifest(out_dir, labels, frames) != 0) {
        free(labels);
        return 1;
    }

    free(labels);
    return 0;
}
