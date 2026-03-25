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
    lv_obj_t *eyes_row;
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
    lv_color_t bg_top;
    lv_color_t bg_bottom;
    lv_color_t cube_front;
    lv_color_t cube_top;
    lv_color_t cube_side;
    lv_color_t accent;
    lv_color_t text_dim;
    lv_color_t chip_bg;
    int ambient_opa;
    int cube_y;
    int cube_scale_pct;
    int eye_gap;
    int eye_w;
    int eye_h;
    int eye_y;
    int mouth_w;
    int mouth_h;
    int mouth_y;
    int mouth_radius;
    int pill_pct;
    const char *mood;
    const char *status_right;
} pose_t;

static const pose_t POSE_IDLE = {
    .bg_top = LV_COLOR_MAKE(0x06, 0x08, 0x0F),
    .bg_bottom = LV_COLOR_MAKE(0x0D, 0x16, 0x25),
    .cube_front = LV_COLOR_MAKE(0x1A, 0x1A, 0x2E),
    .cube_top = LV_COLOR_MAKE(0x2A, 0x2A, 0x46),
    .cube_side = LV_COLOR_MAKE(0x12, 0x12, 0x20),
    .accent = LV_COLOR_MAKE(0x00, 0xD4, 0xD2),
    .text_dim = LV_COLOR_MAKE(0x84, 0xA2, 0xB2),
    .chip_bg = LV_COLOR_MAKE(0x10, 0x2A, 0x36),
    .ambient_opa = 30,
    .cube_y = 0,
    .cube_scale_pct = 100,
    .eye_gap = 16,
    .eye_w = 18,
    .eye_h = 34,
    .eye_y = -6,
    .mouth_w = 18,
    .mouth_h = 8,
    .mouth_y = 22,
    .mouth_radius = 4,
    .pill_pct = 10,
    .mood = "IDLE",
    .status_right = "88%",
};

static const pose_t POSE_LISTEN = {
    .bg_top = LV_COLOR_MAKE(0x07, 0x10, 0x16),
    .bg_bottom = LV_COLOR_MAKE(0x0D, 0x24, 0x30),
    .cube_front = LV_COLOR_MAKE(0x1B, 0x1F, 0x30),
    .cube_top = LV_COLOR_MAKE(0x30, 0x36, 0x52),
    .cube_side = LV_COLOR_MAKE(0x15, 0x17, 0x24),
    .accent = LV_COLOR_MAKE(0x40, 0xFF, 0xF8),
    .text_dim = LV_COLOR_MAKE(0x7F, 0xB7, 0xC3),
    .chip_bg = LV_COLOR_MAKE(0x11, 0x38, 0x44),
    .ambient_opa = 48,
    .cube_y = -2,
    .cube_scale_pct = 102,
    .eye_gap = 18,
    .eye_w = 20,
    .eye_h = 38,
    .eye_y = -8,
    .mouth_w = 16,
    .mouth_h = 10,
    .mouth_y = 24,
    .mouth_radius = 5,
    .pill_pct = 18,
    .mood = "LISTEN",
    .status_right = "LIVE",
};

static const pose_t POSE_THINK = {
    .bg_top = LV_COLOR_MAKE(0x09, 0x0B, 0x12),
    .bg_bottom = LV_COLOR_MAKE(0x16, 0x13, 0x25),
    .cube_front = LV_COLOR_MAKE(0x18, 0x1A, 0x28),
    .cube_top = LV_COLOR_MAKE(0x26, 0x26, 0x42),
    .cube_side = LV_COLOR_MAKE(0x11, 0x13, 0x23),
    .accent = LV_COLOR_MAKE(0xB8, 0x98, 0xFF),
    .text_dim = LV_COLOR_MAKE(0xA5, 0x9C, 0xB8),
    .chip_bg = LV_COLOR_MAKE(0x2E, 0x1D, 0x49),
    .ambient_opa = 34,
    .cube_y = -3,
    .cube_scale_pct = 101,
    .eye_gap = 14,
    .eye_w = 18,
    .eye_h = 28,
    .eye_y = -6,
    .mouth_w = 16,
    .mouth_h = 6,
    .mouth_y = 24,
    .mouth_radius = 3,
    .pill_pct = 24,
    .mood = "THINK",
    .status_right = "SYNC",
};

static const pose_t POSE_SPEAK = {
    .bg_top = LV_COLOR_MAKE(0x07, 0x11, 0x1A),
    .bg_bottom = LV_COLOR_MAKE(0x09, 0x36, 0x40),
    .cube_front = LV_COLOR_MAKE(0x19, 0x20, 0x2B),
    .cube_top = LV_COLOR_MAKE(0x2E, 0x33, 0x49),
    .cube_side = LV_COLOR_MAKE(0x11, 0x18, 0x20),
    .accent = LV_COLOR_MAKE(0x40, 0xFF, 0xF8),
    .text_dim = LV_COLOR_MAKE(0x7E, 0xC6, 0xD1),
    .chip_bg = LV_COLOR_MAKE(0x13, 0x3A, 0x42),
    .ambient_opa = 60,
    .cube_y = -6,
    .cube_scale_pct = 104,
    .eye_gap = 16,
    .eye_w = 18,
    .eye_h = 34,
    .eye_y = -7,
    .mouth_w = 14,
    .mouth_h = 22,
    .mouth_y = 24,
    .mouth_radius = 8,
    .pill_pct = 82,
    .mood = "SPEAK",
    .status_right = "TALK",
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

static void style_rect(lv_obj_t *obj, lv_color_t bg, int radius, int border_width, lv_color_t border) {
    lv_obj_set_style_bg_color(obj, bg, 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(obj, border_width, 0);
    lv_obj_set_style_border_color(obj, border, 0);
    lv_obj_set_style_radius(obj, radius, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_clear_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
}

static lv_color_t mix_color(lv_color_t a, lv_color_t b, float t) {
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    uint8_t ar = a.ch.red * 255 / 31;
    uint8_t ag = a.ch.green * 255 / 63;
    uint8_t ab = a.ch.blue * 255 / 31;
    uint8_t br = b.ch.red * 255 / 31;
    uint8_t bg = b.ch.green * 255 / 63;
    uint8_t bb = b.ch.blue * 255 / 31;
    uint8_t rr = (uint8_t)(ar + (br - ar) * t);
    uint8_t rg = (uint8_t)(ag + (bg - ag) * t);
    uint8_t rb = (uint8_t)(ab + (bb - ab) * t);
    return lv_color_make(rr, rg, rb);
}

static int mix_int(int a, int b, float t) {
    return (int)lround((double)a + ((double)b - (double)a) * t);
}

static pose_t lerp_pose(const pose_t *a, const pose_t *b, float t) {
    pose_t p = *a;
    p.bg_top = mix_color(a->bg_top, b->bg_top, t);
    p.bg_bottom = mix_color(a->bg_bottom, b->bg_bottom, t);
    p.cube_front = mix_color(a->cube_front, b->cube_front, t);
    p.cube_top = mix_color(a->cube_top, b->cube_top, t);
    p.cube_side = mix_color(a->cube_side, b->cube_side, t);
    p.accent = mix_color(a->accent, b->accent, t);
    p.text_dim = mix_color(a->text_dim, b->text_dim, t);
    p.chip_bg = mix_color(a->chip_bg, b->chip_bg, t);
    p.ambient_opa = mix_int(a->ambient_opa, b->ambient_opa, t);
    p.cube_y = mix_int(a->cube_y, b->cube_y, t);
    p.cube_scale_pct = mix_int(a->cube_scale_pct, b->cube_scale_pct, t);
    p.eye_gap = mix_int(a->eye_gap, b->eye_gap, t);
    p.eye_w = mix_int(a->eye_w, b->eye_w, t);
    p.eye_h = mix_int(a->eye_h, b->eye_h, t);
    p.eye_y = mix_int(a->eye_y, b->eye_y, t);
    p.mouth_w = mix_int(a->mouth_w, b->mouth_w, t);
    p.mouth_h = mix_int(a->mouth_h, b->mouth_h, t);
    p.mouth_y = mix_int(a->mouth_y, b->mouth_y, t);
    p.mouth_radius = mix_int(a->mouth_radius, b->mouth_radius, t);
    p.pill_pct = mix_int(a->pill_pct, b->pill_pct, t);
    return p;
}

static void setup_ui(ui_t *ui) {
    lv_obj_t *screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, POSE_IDLE.bg_top, 0);
    lv_obj_set_style_bg_grad_color(screen, POSE_IDLE.bg_bottom, 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);

    ui->ambient = lv_obj_create(screen);
    lv_obj_set_size(ui->ambient, 160, 160);
    lv_obj_align(ui->ambient, LV_ALIGN_CENTER, 0, -6);
    style_rect(ui->ambient, POSE_IDLE.accent, 80, 0, POSE_IDLE.accent);
    lv_obj_set_style_bg_opa(ui->ambient, POSE_IDLE.ambient_opa, 0);

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
    lv_label_set_text(ui->status_right, "88%");
    lv_obj_set_style_text_font(ui->status_right, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->status_right, POSE_IDLE.text_dim, 0);
    lv_obj_align(ui->status_right, LV_ALIGN_TOP_RIGHT, -16, 10);

    ui->status_dot = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->status_dot, 8, 8);
    style_rect(ui->status_dot, POSE_IDLE.accent, 4, 0, POSE_IDLE.accent);
    lv_obj_align(ui->status_dot, LV_ALIGN_TOP_MID, 0, 16);

    ui->cube_wrap = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->cube_wrap, 150, 170);
    lv_obj_align(ui->cube_wrap, LV_ALIGN_CENTER, 0, -6);
    lv_obj_set_style_bg_opa(ui->cube_wrap, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ui->cube_wrap, 0, 0);
    lv_obj_set_style_pad_all(ui->cube_wrap, 0, 0);
    lv_obj_clear_flag(ui->cube_wrap, LV_OBJ_FLAG_SCROLLABLE);

    ui->cube = lv_obj_create(ui->cube_wrap);
    lv_obj_set_size(ui->cube, 130, 130);
    lv_obj_align(ui->cube, LV_ALIGN_CENTER, 0, 10);
    lv_obj_set_style_bg_opa(ui->cube, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ui->cube, 0, 0);
    lv_obj_clear_flag(ui->cube, LV_OBJ_FLAG_SCROLLABLE);

    ui->top = lv_obj_create(ui->cube);
    lv_obj_set_size(ui->top, 104, 28);
    lv_obj_align(ui->top, LV_ALIGN_TOP_MID, 2, 2);
    style_rect(ui->top, POSE_IDLE.cube_top, 16, 0, POSE_IDLE.cube_top);

    ui->side = lv_obj_create(ui->cube);
    lv_obj_set_size(ui->side, 34, 104);
    lv_obj_align(ui->side, LV_ALIGN_RIGHT_MID, -1, 8);
    style_rect(ui->side, POSE_IDLE.cube_side, 16, 0, POSE_IDLE.cube_side);

    ui->front = lv_obj_create(ui->cube);
    lv_obj_set_size(ui->front, 130, 130);
    lv_obj_align(ui->front, LV_ALIGN_CENTER, 0, 10);
    style_rect(ui->front, POSE_IDLE.cube_front, 16, 0, POSE_IDLE.cube_front);

    ui->edge_top = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_top, 106, 2);
    style_rect(ui->edge_top, POSE_IDLE.accent, 2, 0, POSE_IDLE.accent);
    lv_obj_align(ui->edge_top, LV_ALIGN_TOP_MID, 0, 0);

    ui->edge_bottom = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_bottom, 106, 2);
    style_rect(ui->edge_bottom, POSE_IDLE.accent, 2, 0, POSE_IDLE.accent);
    lv_obj_align(ui->edge_bottom, LV_ALIGN_BOTTOM_MID, 0, 0);

    ui->edge_left = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_left, 2, 106);
    style_rect(ui->edge_left, POSE_IDLE.accent, 2, 0, POSE_IDLE.accent);
    lv_obj_align(ui->edge_left, LV_ALIGN_LEFT_MID, 0, 0);

    ui->edge_right = lv_obj_create(ui->front);
    lv_obj_set_size(ui->edge_right, 2, 106);
    style_rect(ui->edge_right, POSE_IDLE.accent, 2, 0, POSE_IDLE.accent);
    lv_obj_align(ui->edge_right, LV_ALIGN_RIGHT_MID, 0, 0);

    ui->eyes_row = lv_obj_create(ui->front);
    lv_obj_set_size(ui->eyes_row, 80, 44);
    lv_obj_align(ui->eyes_row, LV_ALIGN_CENTER, 0, -4);
    lv_obj_set_style_bg_opa(ui->eyes_row, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ui->eyes_row, 0, 0);
    lv_obj_clear_flag(ui->eyes_row, LV_OBJ_FLAG_SCROLLABLE);

    ui->eye_left = lv_obj_create(ui->eyes_row);
    lv_obj_set_size(ui->eye_left, 18, 34);
    style_rect(ui->eye_left, lv_color_hex(0xF0F0F0), 12, 0, lv_color_hex(0xF0F0F0));
    lv_obj_align(ui->eye_left, LV_ALIGN_CENTER, -17, -2);

    ui->eye_right = lv_obj_create(ui->eyes_row);
    lv_obj_set_size(ui->eye_right, 18, 34);
    style_rect(ui->eye_right, lv_color_hex(0xF0F0F0), 12, 0, lv_color_hex(0xF0F0F0));
    lv_obj_align(ui->eye_right, LV_ALIGN_CENTER, 17, -2);

    ui->mouth = lv_obj_create(ui->front);
    lv_obj_set_size(ui->mouth, 16, 10);
    style_rect(ui->mouth, lv_color_hex(0xF0F0F0), 5, 0, lv_color_hex(0xF0F0F0));
    lv_obj_align(ui->mouth, LV_ALIGN_CENTER, 0, 26);

    ui->mood_chip = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->mood_chip, 70, 24);
    lv_obj_align(ui->mood_chip, LV_ALIGN_BOTTOM_MID, 0, -44);
    style_rect(ui->mood_chip, POSE_IDLE.chip_bg, 12, 1, POSE_IDLE.accent);

    ui->mood_label = lv_label_create(ui->mood_chip);
    lv_label_set_text(ui->mood_label, POSE_IDLE.mood);
    lv_obj_set_style_text_font(ui->mood_label, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->mood_label, lv_color_hex(0xD7F9FF), 0);
    lv_obj_center(ui->mood_label);

    ui->pill = lv_obj_create(ui->shell);
    lv_obj_set_size(ui->pill, 176, 18);
    lv_obj_align(ui->pill, LV_ALIGN_BOTTOM_MID, 0, -16);
    style_rect(ui->pill, lv_color_hex(0x0D1820), 9, 1, lv_color_hex(0x17303D));

    ui->pill_fill = lv_obj_create(ui->pill);
    lv_obj_set_size(ui->pill_fill, 12, 10);
    style_rect(ui->pill_fill, POSE_IDLE.accent, 5, 0, POSE_IDLE.accent);
    lv_obj_align(ui->pill_fill, LV_ALIGN_LEFT_MID, 4, 0);

    ui->footer = lv_label_create(ui->shell);
    lv_label_set_text(ui->footer, "LVGL voxel renderer preview");
    lv_obj_set_style_text_font(ui->footer, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(ui->footer, POSE_IDLE.text_dim, 0);
    lv_obj_align(ui->footer, LV_ALIGN_BOTTOM_MID, 0, 8);
}

static void apply_pose(ui_t *ui, const pose_t *pose, float eye_offset_x, float eye_offset_y, int blink_h, int mouth_boost) {
    lv_obj_t *screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, pose->bg_top, 0);
    lv_obj_set_style_bg_grad_color(screen, pose->bg_bottom, 0);

    lv_obj_set_style_bg_opa(ui->ambient, pose->ambient_opa, 0);
    lv_obj_set_style_bg_color(ui->ambient, pose->accent, 0);

    lv_label_set_text(ui->status_right, pose->status_right);
    lv_label_set_text(ui->mood_label, pose->mood);
    lv_obj_set_style_text_color(ui->status_right, pose->text_dim, 0);
    lv_obj_set_style_text_color(ui->footer, pose->text_dim, 0);
    lv_obj_set_style_text_color(ui->status_left, lv_color_mix(pose->accent, lv_color_hex(0xFFFFFF), LV_OPA_20), 0);

    lv_obj_set_style_bg_color(ui->front, pose->cube_front, 0);
    lv_obj_set_style_bg_color(ui->top, pose->cube_top, 0);
    lv_obj_set_style_bg_color(ui->side, pose->cube_side, 0);
    lv_obj_set_style_bg_color(ui->edge_top, pose->accent, 0);
    lv_obj_set_style_bg_color(ui->edge_bottom, pose->accent, 0);
    lv_obj_set_style_bg_color(ui->edge_left, pose->accent, 0);
    lv_obj_set_style_bg_color(ui->edge_right, pose->accent, 0);
    lv_obj_set_style_bg_color(ui->status_dot, pose->accent, 0);
    lv_obj_set_style_bg_color(ui->pill_fill, pose->accent, 0);
    lv_obj_set_style_bg_color(ui->mood_chip, pose->chip_bg, 0);
    lv_obj_set_style_border_color(ui->mood_chip, lv_color_mix(pose->accent, lv_color_hex(0xFFFFFF), LV_OPA_20), 0);
    lv_obj_set_style_text_color(ui->mood_label, lv_color_mix(pose->accent, lv_color_hex(0xFFFFFF), LV_OPA_10), 0);

    int cube_size = 130 * pose->cube_scale_pct / 100;
    lv_obj_align(ui->cube_wrap, LV_ALIGN_CENTER, 0, -6 + pose->cube_y);
    lv_obj_set_size(ui->cube, cube_size, cube_size);
    lv_obj_align(ui->cube, LV_ALIGN_CENTER, 0, 10);
    lv_obj_set_size(ui->front, cube_size, cube_size);
    lv_obj_align(ui->front, LV_ALIGN_CENTER, 0, 10);
    lv_obj_set_size(ui->top, (cube_size * 104) / 130, (cube_size * 28) / 130);
    lv_obj_align(ui->top, LV_ALIGN_TOP_MID, 2, 2);
    lv_obj_set_size(ui->side, (cube_size * 34) / 130, (cube_size * 104) / 130);
    lv_obj_align(ui->side, LV_ALIGN_RIGHT_MID, -1, 8);

    int edge_w = (cube_size * 106) / 130;
    int edge_h = (cube_size * 106) / 130;
    lv_obj_set_size(ui->edge_top, edge_w, 2);
    lv_obj_set_size(ui->edge_bottom, edge_w, 2);
    lv_obj_set_size(ui->edge_left, 2, edge_h);
    lv_obj_set_size(ui->edge_right, 2, edge_h);
    lv_obj_align(ui->edge_top, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_align(ui->edge_bottom, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_align(ui->edge_left, LV_ALIGN_LEFT_MID, 0, 0);
    lv_obj_align(ui->edge_right, LV_ALIGN_RIGHT_MID, 0, 0);

    int eye_h = blink_h > 0 ? blink_h : pose->eye_h;
    int eye_w = pose->eye_w;
    int eye_gap = pose->eye_gap;
    int lx = -((eye_gap / 2) + eye_w / 2) + (int)lround(eye_offset_x);
    int rx = ((eye_gap / 2) + eye_w / 2) + (int)lround(eye_offset_x);
    int ly = pose->eye_y + (int)lround(eye_offset_y);

    lv_obj_set_size(ui->eye_left, eye_w, eye_h);
    lv_obj_set_size(ui->eye_right, eye_w, eye_h);
    lv_obj_set_style_radius(ui->eye_left, LV_MIN(eye_w / 2 + 2, 14), 0);
    lv_obj_set_style_radius(ui->eye_right, LV_MIN(eye_w / 2 + 2, 14), 0);
    lv_obj_align(ui->eye_left, LV_ALIGN_CENTER, lx, ly);
    lv_obj_align(ui->eye_right, LV_ALIGN_CENTER, rx, ly);

    lv_obj_set_size(ui->mouth, pose->mouth_w, pose->mouth_h + mouth_boost);
    lv_obj_set_style_radius(ui->mouth, pose->mouth_radius, 0);
    lv_obj_align(ui->mouth, LV_ALIGN_CENTER, 0, pose->mouth_y);

    int pill_width = 8 + (pose->pill_pct * 164 / 100);
    lv_obj_set_size(ui->pill_fill, pill_width, 10);
    lv_obj_align(ui->pill_fill, LV_ALIGN_LEFT_MID, 4, 0);
}

static pose_t sample_pose(float t) {
    float cycle = fmodf(t, 1.0f);
    if (cycle < 0.25f) {
        return lerp_pose(&POSE_IDLE, &POSE_LISTEN, cycle / 0.25f);
    }
    if (cycle < 0.5f) {
        return lerp_pose(&POSE_LISTEN, &POSE_THINK, (cycle - 0.25f) / 0.25f);
    }
    if (cycle < 0.8f) {
        return lerp_pose(&POSE_THINK, &POSE_SPEAK, (cycle - 0.5f) / 0.3f);
    }
    return lerp_pose(&POSE_SPEAK, &POSE_IDLE, (cycle - 0.8f) / 0.2f);
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

    for (int i = 0; i < frames; i++) {
        float t = (float)i / (float)(frames > 1 ? frames - 1 : 1);
        float bounce = sinf(t * 6.28318f * 2.2f) * 2.5f;
        float gaze_x = sinf(t * 6.28318f * 1.3f) * 2.0f;
        float gaze_y = cosf(t * 6.28318f * 0.9f) * 1.3f;
        float blink_phase = fabsf(sinf(t * 6.28318f * 1.7f));
        int blink_h = blink_phase > 0.96f ? 6 : 0;
        int mouth_boost = (int)lroundf((sinf(t * 6.28318f * 3.1f) * 0.5f + 0.5f) * 6.0f);

        pose_t pose = sample_pose(t);
        pose.cube_y += (int)lroundf(bounce);
        apply_pose(&ui, &pose, gaze_x, gaze_y, blink_h, mouth_boost);

        lv_tick_inc(16);
        lv_timer_handler();

        if (write_frame(out_dir, i) != 0) {
            return 1;
        }
    }

    return 0;
}
