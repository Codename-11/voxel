/*
 * Voxel Boot Splash — minimal C program for early boot LCD display.
 *
 * Drives the WhisPlay HAT's ST7789 LCD via SPI and shows a splash image
 * ~3 seconds after power-on, before Python services start.
 *
 * Hardware:
 *   - SPI: /dev/spidev0.0 at 32MHz (ST7789 240x280 LCD)
 *   - DC:  GPIO 27 (data/command select)
 *   - RST: GPIO 4  (hardware reset)
 *   - BL:  GPIO 22 (backlight, active LOW)
 *
 * GPIO access via /sys/class/gpio (no external dependencies).
 * Splash frame loaded from /boot/voxel-splash.rgb565 (134,400 bytes).
 *
 * Build: gcc -O2 -Wall -o splash splash.c
 * Usage: /usr/local/bin/voxel-splash
 */

#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>

/* ── Pin assignments ─────────────────────────────────────────────────── */

#define PIN_DC   27   /* Data/Command select */
#define PIN_RST   4   /* Hardware reset */
#define PIN_BL   22   /* Backlight (active LOW) */

/* ── Display constants ───────────────────────────────────────────────── */

#define LCD_W       240
#define LCD_H       280
#define LCD_Y_OFS    20   /* ST7789 320-row panel, 280 visible with 20px offset */
#define FRAME_SIZE  (LCD_W * LCD_H * 2)  /* 134,400 bytes (RGB565) */

#define SPI_SPEED   32000000  /* 32 MHz */

/* ── Splash file path ────────────────────────────────────────────────── */

#define SPLASH_PATH "/boot/voxel-splash.rgb565"

/* ── SPI file descriptor (global for helper functions) ───────────────── */

static int spi_fd = -1;

/* ── GPIO helpers via /sys/class/gpio ────────────────────────────────── */

static int gpio_export(int pin)
{
    FILE *f = fopen("/sys/class/gpio/export", "w");
    if (!f) return -1;
    fprintf(f, "%d", pin);
    fclose(f);
    /* Brief delay for sysfs node to appear */
    usleep(50000);
    return 0;
}

static int gpio_direction(int pin, const char *dir)
{
    char path[64];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/direction", pin);
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    fprintf(f, "%s", dir);
    fclose(f);
    return 0;
}

static int gpio_write(int pin, int val)
{
    char path[64];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/value", pin);
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    fprintf(f, "%d", val);
    fclose(f);
    return 0;
}

static void gpio_unexport(int pin)
{
    FILE *f = fopen("/sys/class/gpio/unexport", "w");
    if (f) {
        fprintf(f, "%d", pin);
        fclose(f);
    }
}

/* ── Delay helpers ───────────────────────────────────────────────────── */

static void delay_ms(int ms)
{
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
}

/* ── SPI transfer ────────────────────────────────────────────────────── */

static int spi_write(const uint8_t *buf, size_t len)
{
    /* The kernel SPI driver has a max transfer size (usually 4096).
     * For large frame data, send in chunks. */
    const size_t CHUNK = 4096;
    size_t offset = 0;

    while (offset < len) {
        size_t n = len - offset;
        if (n > CHUNK) n = CHUNK;

        struct spi_ioc_transfer tr;
        memset(&tr, 0, sizeof(tr));
        tr.tx_buf = (unsigned long)(buf + offset);
        tr.len = n;
        tr.speed_hz = SPI_SPEED;
        tr.bits_per_word = 8;

        if (ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr) < 0)
            return -1;
        offset += n;
    }
    return 0;
}

/* ── ST7789 command / data ───────────────────────────────────────────── */

static void send_cmd(uint8_t cmd)
{
    gpio_write(PIN_DC, 0);
    spi_write(&cmd, 1);
}

static void send_data_byte(uint8_t data)
{
    gpio_write(PIN_DC, 1);
    spi_write(&data, 1);
}

static void send_data(const uint8_t *data, size_t len)
{
    gpio_write(PIN_DC, 1);
    spi_write(data, len);
}

/* ── ST7789 initialization sequence ──────────────────────────────────── */

static void lcd_init(void)
{
    /* Hardware reset */
    gpio_write(PIN_RST, 1);
    delay_ms(10);
    gpio_write(PIN_RST, 0);
    delay_ms(10);
    gpio_write(PIN_RST, 1);
    delay_ms(120);

    /* Software reset */
    send_cmd(0x01);  /* SWRESET */
    delay_ms(150);

    /* Sleep out */
    send_cmd(0x11);  /* SLPOUT */
    delay_ms(120);

    /* Color mode: RGB565 (16-bit) */
    send_cmd(0x3A);  /* COLMOD */
    send_data_byte(0x05);

    /* Memory data access control (no rotation) */
    send_cmd(0x36);  /* MADCTL */
    send_data_byte(0x00);

    /* Porch control */
    send_cmd(0xB2);
    {
        uint8_t porch[] = {0x0C, 0x0C, 0x00, 0x33, 0x33};
        send_data(porch, sizeof(porch));
    }

    /* Gate control */
    send_cmd(0xB7);
    send_data_byte(0x75);

    /* VCOM setting */
    send_cmd(0xBB);
    send_data_byte(0x22);

    /* LCM control */
    send_cmd(0xC0);
    send_data_byte(0x2C);

    /* VDV and VRH command enable */
    send_cmd(0xC2);
    send_data_byte(0x01);

    /* VRH set */
    send_cmd(0xC3);
    send_data_byte(0x13);

    /* VDV set */
    send_cmd(0xC4);
    send_data_byte(0x20);

    /* Frame rate control */
    send_cmd(0xC6);
    send_data_byte(0x0F);  /* 60 Hz */

    /* Power control 1 */
    send_cmd(0xD0);
    {
        uint8_t pwr[] = {0xA4, 0xA1};
        send_data(pwr, sizeof(pwr));
    }

    /* Display inversion on (required for ST7789 correct colors) */
    send_cmd(0x21);  /* INVON */

    /* Display on */
    send_cmd(0x29);  /* DISPON */
    delay_ms(20);
}

/* ── Set display window ──────────────────────────────────────────────── */

static void lcd_set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1)
{
    /* Column address set */
    send_cmd(0x2A);  /* CASET */
    {
        uint8_t col[] = {
            (uint8_t)(x0 >> 8), (uint8_t)(x0 & 0xFF),
            (uint8_t)(x1 >> 8), (uint8_t)(x1 & 0xFF),
        };
        send_data(col, 4);
    }

    /* Row address set (with Y offset for 240x280 in 320-row panel) */
    uint16_t r0 = y0 + LCD_Y_OFS;
    uint16_t r1 = y1 + LCD_Y_OFS;
    send_cmd(0x2B);  /* RASET */
    {
        uint8_t row[] = {
            (uint8_t)(r0 >> 8), (uint8_t)(r0 & 0xFF),
            (uint8_t)(r1 >> 8), (uint8_t)(r1 & 0xFF),
        };
        send_data(row, 4);
    }

    /* Memory write */
    send_cmd(0x2C);  /* RAMWR */
}

/* ── Main ────────────────────────────────────────────────────────────── */

int main(void)
{
    int ret = 0;

    /* ── Open SPI device ─────────────────────────────────────────────── */
    spi_fd = open("/dev/spidev0.0", O_RDWR);
    if (spi_fd < 0) {
        /* SPI not available — probably not on Pi hardware. Exit silently. */
        return 0;
    }

    uint32_t speed = SPI_SPEED;
    uint8_t mode = SPI_MODE_0;
    uint8_t bits = 8;

    if (ioctl(spi_fd, SPI_IOC_WR_MODE, &mode) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0 ||
        ioctl(spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0) {
        /* SPI config failed — exit silently */
        close(spi_fd);
        return 0;
    }

    /* ── Export and configure GPIO pins ───────────────────────────────── */
    int pins[] = {PIN_DC, PIN_RST, PIN_BL};
    int num_pins = sizeof(pins) / sizeof(pins[0]);

    for (int i = 0; i < num_pins; i++) {
        /* Export may fail if already exported — that's OK */
        gpio_export(pins[i]);
        if (gpio_direction(pins[i], "out") < 0) {
            /* If we can't set direction, bail silently */
            ret = 0;
            goto cleanup;
        }
    }

    /* Keep backlight OFF during init to avoid flash */
    gpio_write(PIN_BL, 1);  /* active LOW: 1 = off */

    /* ── Initialize the LCD ──────────────────────────────────────────── */
    lcd_init();

    /* ── Load and display splash frame ───────────────────────────────── */
    FILE *splash_file = fopen(SPLASH_PATH, "rb");
    if (!splash_file) {
        /* No splash file — fill with background color and show that.
         * BG = (10, 10, 15) → RGB565 big-endian. */
        uint16_t bg565 = ((10 & 0xF8) << 8) | ((10 & 0xFC) << 3) | (15 >> 3);
        /* Convert to big-endian */
        uint8_t bg_hi = (uint8_t)(bg565 >> 8);
        uint8_t bg_lo = (uint8_t)(bg565 & 0xFF);

        uint8_t *buf = malloc(FRAME_SIZE);
        if (!buf) goto backlight_on;

        for (int i = 0; i < LCD_W * LCD_H; i++) {
            buf[i * 2]     = bg_hi;
            buf[i * 2 + 1] = bg_lo;
        }

        lcd_set_window(0, 0, LCD_W - 1, LCD_H - 1);
        send_data(buf, FRAME_SIZE);
        free(buf);
    } else {
        /* Load the pre-rendered RGB565 frame */
        uint8_t *frame = malloc(FRAME_SIZE);
        if (!frame) {
            fclose(splash_file);
            goto backlight_on;
        }

        size_t read_bytes = fread(frame, 1, FRAME_SIZE, splash_file);
        fclose(splash_file);

        if (read_bytes < (size_t)FRAME_SIZE) {
            /* Partial read — pad remainder with background */
            memset(frame + read_bytes, 0, FRAME_SIZE - read_bytes);
        }

        lcd_set_window(0, 0, LCD_W - 1, LCD_H - 1);
        send_data(frame, FRAME_SIZE);
        free(frame);
    }

backlight_on:
    /* ── Turn on backlight ───────────────────────────────────────────── */
    gpio_write(PIN_BL, 0);  /* active LOW: 0 = on */

cleanup:
    /* Close SPI but do NOT unexport GPIOs — the image must persist on
     * the LCD until the Python display service takes over. Unexporting
     * would reset the backlight pin, turning the screen off. */
    if (spi_fd >= 0)
        close(spi_fd);

    return ret;
}
