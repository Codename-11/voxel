#include <errno.h>
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

    if (fwrite(framebuffer, sizeof(uint16_t), FRAME_PIXELS, fp) != FRAME_PIXELS) {
        fprintf(stderr, "Failed to write frame %d\n", index);
        fclose(fp);
        return 1;
    }

    fclose(fp);
    return 0;
}

static void setup_ui(lv_obj_t **bar_out, lv_obj_t **status_out, lv_obj_t **badge_out) {
    lv_obj_t *screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x070A10), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(0x0C2430), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);

    lv_obj_t *card = lv_obj_create(screen);
    lv_obj_set_size(card, 208, 220);
    lv_obj_center(card);
    lv_obj_set_style_radius(card, 18, 0);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x111821), 0);
    lv_obj_set_style_border_color(card, lv_color_hex(0x48E8FF), 0);
    lv_obj_set_style_border_width(card, 2, 0);
    lv_obj_set_style_pad_all(card, 16, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *title = lv_label_create(card);
    lv_label_set_text(title, "VOXEL");
    lv_obj_set_style_text_font(title, &lv_font_montserrat_18, 0);
    lv_obj_set_style_text_color(title, lv_color_hex(0xE8FCFF), 0);
    lv_obj_align(title, LV_ALIGN_TOP_LEFT, 0, 0);

    lv_obj_t *subtitle = lv_label_create(card);
    lv_label_set_text(subtitle, "LVGL PoC");
    lv_obj_set_style_text_font(subtitle, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(subtitle, lv_color_hex(0x88C7D1), 0);
    lv_obj_align_to(subtitle, title, LV_ALIGN_OUT_BOTTOM_LEFT, 0, 8);

    lv_obj_t *face = lv_obj_create(card);
    lv_obj_set_size(face, 110, 110);
    lv_obj_align(face, LV_ALIGN_CENTER, 0, -8);
    lv_obj_set_style_radius(face, 22, 0);
    lv_obj_set_style_bg_color(face, lv_color_hex(0x0B1218), 0);
    lv_obj_set_style_border_width(face, 0, 0);
    lv_obj_clear_flag(face, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *eye_l = lv_obj_create(face);
    lv_obj_set_size(eye_l, 18, 32);
    lv_obj_align(eye_l, LV_ALIGN_CENTER, -22, -10);
    lv_obj_set_style_radius(eye_l, 9, 0);
    lv_obj_set_style_bg_color(eye_l, lv_color_hex(0x72F3FF), 0);
    lv_obj_set_style_border_width(eye_l, 0, 0);
    lv_obj_clear_flag(eye_l, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *eye_r = lv_obj_create(face);
    lv_obj_set_size(eye_r, 18, 32);
    lv_obj_align(eye_r, LV_ALIGN_CENTER, 22, -10);
    lv_obj_set_style_radius(eye_r, 9, 0);
    lv_obj_set_style_bg_color(eye_r, lv_color_hex(0x72F3FF), 0);
    lv_obj_set_style_border_width(eye_r, 0, 0);
    lv_obj_clear_flag(eye_r, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *mouth = lv_obj_create(face);
    lv_obj_set_size(mouth, 36, 10);
    lv_obj_align(mouth, LV_ALIGN_CENTER, 0, 24);
    lv_obj_set_style_radius(mouth, 5, 0);
    lv_obj_set_style_bg_color(mouth, lv_color_hex(0x72F3FF), 0);
    lv_obj_set_style_border_width(mouth, 0, 0);
    lv_obj_clear_flag(mouth, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *bar = lv_bar_create(card);
    lv_obj_set_size(bar, 176, 10);
    lv_obj_align(bar, LV_ALIGN_BOTTOM_MID, 0, -28);
    lv_bar_set_range(bar, 0, 100);
    lv_obj_set_style_bg_color(bar, lv_color_hex(0x1D2A32), LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar, lv_color_hex(0x48E8FF), LV_PART_INDICATOR);
    lv_obj_set_style_radius(bar, 5, LV_PART_MAIN);
    lv_obj_set_style_radius(bar, 5, LV_PART_INDICATOR);

    lv_obj_t *status = lv_label_create(card);
    lv_label_set_text(status, "Booting renderer...");
    lv_obj_set_style_text_font(status, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(status, lv_color_hex(0x9EB7BE), 0);
    lv_obj_align(status, LV_ALIGN_BOTTOM_LEFT, 0, -4);

    lv_obj_t *badge = lv_label_create(card);
    lv_label_set_text(badge, "SYNC 00");
    lv_obj_set_style_text_font(badge, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(badge, lv_color_hex(0x48E8FF), 0);
    lv_obj_align(badge, LV_ALIGN_TOP_RIGHT, 0, 4);

    *bar_out = bar;
    *status_out = status;
    *badge_out = badge;
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

    lv_obj_t *bar = NULL;
    lv_obj_t *status = NULL;
    lv_obj_t *badge = NULL;
    setup_ui(&bar, &status, &badge);

    for (int i = 0; i < frames; i++) {
        char status_text[64];
        char badge_text[32];
        int value = (i * 100) / (frames - 1 == 0 ? 1 : frames - 1);

        snprintf(status_text, sizeof(status_text), "Frame %02d of %02d", i + 1, frames);
        snprintf(badge_text, sizeof(badge_text), "SYNC %02d", i);

        lv_bar_set_value(bar, value, LV_ANIM_OFF);
        lv_label_set_text(status, status_text);
        lv_label_set_text(badge, badge_text);

        lv_tick_inc(16);
        lv_timer_handler();

        if (write_frame(out_dir, i) != 0) {
            return 1;
        }
    }

    return 0;
}
