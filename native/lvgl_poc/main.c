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
    lv_obj_t *device_shell;
    lv_obj_t *status_left;
    lv_obj_t *status_right;
    lv_obj_t *status_dot;
    lv_obj_t *cube_wrap;
    lv_obj_t *cube_front;
    lv_obj_t *cube_top;
    lv_obj_t *cube_side;
    lv_obj_t *eye_left;
    lv_obj_t *eye_right;
    lv_obj_t *mouth;
    lv_obj_t *mood_chip;
    lv_obj_t *mood_label;
    lv_obj_t *speaking_pill;
    lv_obj_t *speaking_fill;
    lv_obj_t *footer;
} ui_t;

typedef struct {
    const char *mood_label;
    const char *status_left;
    const char *status_right;
    lv_color_t shell_bg;
    lv_color_t shell_grad;
    lv_color_t cube_front;
    lv_color_t cube_top;
    lv_color_t cube_side;
    lv_color_t accent;
    lv_color_t text_dim;
    lv_color_t mood_bg;
    int cube_y;
    int cube_scale_pct;
    int eye_y;
    int eye_w;
    int eye_h;
    int eye_left_x;
    int eye_right_x;
    int mouth_w;
    int mouth_h;
    int mouth_y;
    int mouth_radius;
    int pill_fill_pct;
    int ambient_opa;
} frame_state_t;

static const frame_state_t FRAME_STATES[] = {
    {"IDLE",      "daemon", "88%", lv_color_hex(0x06080F), lv_color_hex(0x0D1625), lv_color_hex(0x141C28), lv_color_hex(0x1D2734), lv_color_hex(0x0E1520), lv_color_hex(0xF1F3F8), lv_color_hex(0x93A9B6), lv_color_hex(0x102A36), 0, 100, -8, 18, 34, -22, 22, 34, 10, 26, 5, 12, LV_OPA_20},
    {"BLINK",     "daemon", "88%", lv_color_hex(0x06080F), lv_color_hex(0x0D1625), lv_color_hex(0x141C28), lv_color_hex(0x1D2734), lv_color_hex(0x0E1520), lv_color_hex(0xF1F3F8), lv_color_hex(0x93A9B6), lv_color_hex(0x102A36), 0, 100, -8, 20, 8, -22, 22, 34, 8, 27, 4, 12, LV_OPA_18},
    {"LISTEN",    "daemon", "LIVE", lv_color_hex(0x071016), lv_color_hex(0x0D2430), lv_color_hex(0x14202B), lv_color_hex(0x1B2E3D), lv_color_hex(0x101B24), lv_color_hex(0xDDF8FF), lv_color_hex(0x7FB7C3), lv_color_hex(0x113844), -2, 103, -10, 20, 36, -23, 23, 36, 12, 24, 6, 18, LV_OPA_28},
    {"THINK",     "daemon", "sync", lv_color_hex(0x090B12), lv_color_hex(0x161325), lv_color_hex(0x171A24), lv_color_hex(0x22283A), lv_color_hex(0x121523), lv_color_hex(0xF0F2F8), lv_color_hex(0xA59CB8), lv_color_hex(0x2E1D49), -4, 101, -9, 18, 30, -24, 18, 30, 10, 25, 5, 20, LV_OPA_22},
    {"SPEAK",     "daemon", "talk", lv_color_hex(0x07111A), lv_color_hex(0x08323A), lv_color_hex(0x132029), lv_color_hex(0x1C313A), lv_color_hex(0x101A20), lv_color_hex(0xE8FCFF), lv_color_hex(0x7EC6D1), lv_color_hex(0x133A42), -6, 104, -8, 18, 34, -22, 22, 30, 18, 25, 9, 68, LV_OPA_40},
    {"SPEAK",     "daemon", "talk", lv_color_hex(0x07111A), lv_color_hex(0x0A3E49), lv_color_hex(0x15232C), lv_color_hex(0x1E3742), lv_color_hex(0x121B22), lv_color_hex(0xF3FEFF), lv_color_hex(0x84D6E0), lv_color_hex(0x174650), -7, 105, -8, 17, 35, -22, 22, 24, 26, 22, 11, 84, LV_OPA_46},
    {"SPEAK",     "daemon", "talk", lv_color_hex(0x07111A), lv_color_hex(0x093540), lv_color_hex(0x14222B), lv_color_hex(0x1D343E), lv_color_hex(0x101920), lv_color_hex(0xE8FCFF), lv_color_hex(0x7EC6D1), lv_color_hex(0x143C45), -5, 103, -8, 18, 33, -22, 22, 34, 14, 24, 7, 58, LV_OPA_36},
    {"IDLE",      "daemon", "88%", lv_color_hex(0x06080F), lv_color_hex(0x0D1625), lv_color_hex(0x141C28), lv_color_hex(0x1D2734), lv_color_hex(0x0E1520), lv_color_hex(0xF1F3F8), lv_color_hex(0x93A9B6), lv_color_hex(0x102A36), -2, 101, -8, 18, 34, -22, 22, 34, 10, 26, 5, 12, LV_OPA_20},
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
        uint8_t bytes[2] = {
            (uint8_t)((pixel >> 8) & 0xFF),
            (uint8_t)(pixel & 0xFF),
        };
        if (fwrite(bytes, 1, 2, fp) != 2) {
            fprintf(stderr, "Failed to write frame %d\n", index);
            fclose(fp);
            return 1;
        }
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
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x06080F), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(0x0D1625), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);

    ui->ambient = lv_obj_create(screen);
    lv_obj_set_size(ui->ambient, 190, 190);
    lv_obj_align(ui->ambient, LV_ALIGN_CENTER, 0, -4);
    style_rect(ui->ambient, lv_color_hex(0x1EC6D7), 95, 0, lv_color_hex(0x1EC6D7));
    lv_obj_set_style_bg_opa(ui->ambient, LV_OPA_20, 0);

    ui->device_shell = lv_obj_create(screen);
    lv_obj_set_size(ui->device_shell, 228, 268);
    lv_obj_center(ui->device_shell);
    style_rect(ui->device_shell, lv_color_hex(0x0A0D13), 28, 1, lv_color_hex(0x18242F));
    lv_obj_set_style_bg_grad_color(ui->device_shell, lv_color_hex(0x10161E), 0);
    lv_obj_set_style_bg_grad_dir(ui->device_shell, LV_GRAD_DIR_VER, 0);

    ui->status_left = lv_label_create(ui->device_shell);
    lv_label_set_text(ui->status_left, "daemon");
    lv_obj_set_style_text_font(ui->status_left, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->status_left, lv_color_hex(0xC8D2DB), 0);
    lv_obj_align(ui->status_left, LV_ALIGN_TOP_LEFT, 18, 14);

    ui->status_right = lv_label_create(ui->device_shell);
    lv_label_set_text(ui->status_right, "88%");
    lv_obj_set_style_text_font(ui->status_right, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->status_right, lv_color_hex(0x84A2B2), 0);
    lv_obj_align(ui->status_right, LV_ALIGN_TOP_RIGHT, -18, 14);

    ui->status_dot = lv_obj_create(ui->device_shell);
    lv_obj_set_size(ui->status_dot, 8, 8);
    style_rect(ui->status_dot, lv_color_hex(0x52F3FF), 4, 0, lv_color_hex(0x52F3FF));
    lv_obj_align(ui->status_dot, LV_ALIGN_TOP_MID, 0, 18);

    ui->cube_wrap = lv_obj_create(ui->device_shell);
    lv_obj_set_size(ui->cube_wrap, 150, 170);
    lv_obj_align(ui->cube_wrap, LV_ALIGN_CENTER, 0, -10);
    lv_obj_set_style_bg_opa(ui->cube_wrap, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ui->cube_wrap, 0, 0);
    lv_obj_set_style_pad_all(ui->cube_wrap, 0, 0);
    lv_obj_clear_flag(ui->cube_wrap, LV_OBJ_FLAG_SCROLLABLE);

    ui->cube_top = lv_obj_create(ui->cube_wrap);
    lv_obj_set_size(ui->cube_top, 92, 24);
    lv_obj_align(ui->cube_top, LV_ALIGN_TOP_MID, 0, 8);
    style_rect(ui->cube_top, lv_color_hex(0x1D2734), 16, 0, lv_color_hex(0x1D2734));

    ui->cube_side = lv_obj_create(ui->cube_wrap);
    lv_obj_set_size(ui->cube_side, 28, 102);
    lv_obj_align(ui->cube_side, LV_ALIGN_CENTER, 50, 10);
    style_rect(ui->cube_side, lv_color_hex(0x0E1520), 16, 0, lv_color_hex(0x0E1520));

    ui->cube_front = lv_obj_create(ui->cube_wrap);
    lv_obj_set_size(ui->cube_front, 116, 116);
    lv_obj_align(ui->cube_front, LV_ALIGN_CENTER, 0, 14);
    style_rect(ui->cube_front, lv_color_hex(0x141C28), 26, 2, lv_color_hex(0x2F4A5C));

    ui->eye_left = lv_obj_create(ui->cube_front);
    lv_obj_set_size(ui->eye_left, 18, 34);
    style_rect(ui->eye_left, lv_color_hex(0xF1F3F8), 10, 0, lv_color_hex(0xF1F3F8));
    lv_obj_align(ui->eye_left, LV_ALIGN_CENTER, -22, -8);

    ui->eye_right = lv_obj_create(ui->cube_front);
    lv_obj_set_size(ui->eye_right, 18, 34);
    style_rect(ui->eye_right, lv_color_hex(0xF1F3F8), 10, 0, lv_color_hex(0xF1F3F8));
    lv_obj_align(ui->eye_right, LV_ALIGN_CENTER, 22, -8);

    ui->mouth = lv_obj_create(ui->cube_front);
    lv_obj_set_size(ui->mouth, 34, 10);
    style_rect(ui->mouth, lv_color_hex(0xF1F3F8), 5, 0, lv_color_hex(0xF1F3F8));
    lv_obj_align(ui->mouth, LV_ALIGN_CENTER, 0, 26);

    ui->mood_chip = lv_obj_create(ui->device_shell);
    lv_obj_set_size(ui->mood_chip, 70, 24);
    lv_obj_align(ui->mood_chip, LV_ALIGN_BOTTOM_MID, 0, -52);
    style_rect(ui->mood_chip, lv_color_hex(0x102A36), 12, 1, lv_color_hex(0x1D4450));

    ui->mood_label = lv_label_create(ui->mood_chip);
    lv_label_set_text(ui->mood_label, "IDLE");
    lv_obj_set_style_text_font(ui->mood_label, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->mood_label, lv_color_hex(0xD7F9FF), 0);
    lv_obj_center(ui->mood_label);

    ui->speaking_pill = lv_obj_create(ui->device_shell);
    lv_obj_set_size(ui->speaking_pill, 176, 18);
    lv_obj_align(ui->speaking_pill, LV_ALIGN_BOTTOM_MID, 0, -22);
    style_rect(ui->speaking_pill, lv_color_hex(0x0D1820), 9, 1, lv_color_hex(0x17303D));

    ui->speaking_fill = lv_obj_create(ui->speaking_pill);
    lv_obj_set_size(ui->speaking_fill, 22, 10);
    style_rect(ui->speaking_fill, lv_color_hex(0x52F3FF), 5, 0, lv_color_hex(0x52F3FF));
    lv_obj_align(ui->speaking_fill, LV_ALIGN_LEFT_MID, 4, 0);

    ui->footer = lv_label_create(ui->device_shell);
    lv_label_set_text(ui->footer, "LVGL native renderer trial");
    lv_obj_set_style_text_font(ui->footer, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->footer, lv_color_hex(0x738795), 0);
    lv_obj_align(ui->footer, LV_ALIGN_BOTTOM_MID, 0, -4);
}

static void apply_frame(ui_t *ui, const frame_state_t *state) {
    lv_obj_t *screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, state->shell_bg, 0);
    lv_obj_set_style_bg_grad_color(screen, state->shell_grad, 0);

    lv_obj_set_style_bg_opa(ui->ambient, state->ambient_opa, 0);

    lv_label_set_text(ui->status_left, state->status_left);
    lv_label_set_text(ui->status_right, state->status_right);
    lv_label_set_text(ui->mood_label, state->mood_label);

    lv_obj_set_style_text_color(ui->status_right, state->text_dim, 0);
    lv_obj_set_style_text_color(ui->footer, state->text_dim, 0);
    lv_obj_set_style_text_color(ui->status_left, lv_color_mix(state->accent, lv_color_hex(0xFFFFFF), LV_OPA_20), 0);

    lv_obj_set_style_bg_color(ui->cube_front, state->cube_front, 0);
    lv_obj_set_style_border_color(ui->cube_front, lv_color_mix(state->accent, lv_color_hex(0x2F4A5C), LV_OPA_20), 0);
    lv_obj_set_style_bg_color(ui->cube_top, state->cube_top, 0);
    lv_obj_set_style_bg_color(ui->cube_side, state->cube_side, 0);
    lv_obj_set_style_bg_color(ui->mood_chip, state->mood_bg, 0);
    lv_obj_set_style_border_color(ui->mood_chip, lv_color_mix(state->accent, lv_color_hex(0x14323A), LV_OPA_35), 0);
    lv_obj_set_style_text_color(ui->mood_label, lv_color_mix(state->accent, lv_color_hex(0xFFFFFF), LV_OPA_10), 0);
    lv_obj_set_style_bg_color(ui->status_dot, state->accent, 0);
    lv_obj_set_style_bg_color(ui->speaking_fill, state->accent, 0);

    lv_obj_align(ui->cube_wrap, LV_ALIGN_CENTER, 0, -10 + state->cube_y);
    lv_obj_set_size(ui->cube_front, 116 * state->cube_scale_pct / 100, 116 * state->cube_scale_pct / 100);
    lv_obj_align(ui->cube_front, LV_ALIGN_CENTER, 0, 14);

    lv_obj_set_size(ui->eye_left, state->eye_w, state->eye_h);
    lv_obj_set_size(ui->eye_right, state->eye_w, state->eye_h);
    lv_obj_set_style_radius(ui->eye_left, LV_MIN(state->eye_w, state->eye_h) / 2 + 2, 0);
    lv_obj_set_style_radius(ui->eye_right, LV_MIN(state->eye_w, state->eye_h) / 2 + 2, 0);
    lv_obj_set_style_bg_color(ui->eye_left, lv_color_hex(0xF1F3F8), 0);
    lv_obj_set_style_bg_color(ui->eye_right, lv_color_hex(0xF1F3F8), 0);
    lv_obj_align(ui->eye_left, LV_ALIGN_CENTER, state->eye_left_x, state->eye_y);
    lv_obj_align(ui->eye_right, LV_ALIGN_CENTER, state->eye_right_x, state->eye_y);

    lv_obj_set_size(ui->mouth, state->mouth_w, state->mouth_h);
    lv_obj_set_style_radius(ui->mouth, state->mouth_radius, 0);
    lv_obj_set_style_bg_color(ui->mouth, lv_color_hex(0xF1F3F8), 0);
    lv_obj_align(ui->mouth, LV_ALIGN_CENTER, 0, state->mouth_y);

    int pill_width = 8 + (state->pill_fill_pct * 164 / 100);
    lv_obj_set_size(ui->speaking_fill, pill_width, 10);
    lv_obj_align(ui->speaking_fill, LV_ALIGN_LEFT_MID, 4, 0);
}

int main(int argc, char **argv) {
    const char *out_dir = argc > 1 ? argv[1] : "./lvgl_frames";
    int frames = argc > 2 ? atoi(argv[2]) : 24;
    if (frames < 1) {
        frames = 1;
    }

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

    int state_count = (int)(sizeof(FRAME_STATES) / sizeof(FRAME_STATES[0]));

    for (int i = 0; i < frames; i++) {
        int state_index = (i * state_count) / frames;
        if (state_index >= state_count) {
            state_index = state_count - 1;
        }

        apply_frame(&ui, &FRAME_STATES[state_index]);

        lv_tick_inc(16);
        lv_timer_handler();

        if (write_frame(out_dir, i) != 0) {
            return 1;
        }
    }

    return 0;
}
