#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    unsigned char *data;
    size_t length;
    size_t capacity;
    size_t width;
    size_t head;
    bool fixed;
} cuco_buffer;

static inline void cuco_error(const char *message)
{
    fprintf(stderr, "Cuco: %s\n", message);
    exit(EXIT_FAILURE);
}

static inline cuco_buffer *cuco_check(cuco_buffer *buffer)
{
    if (buffer == NULL)
        cuco_error("referência nula");
    return buffer;
}

static inline cuco_buffer *cuco_create(uintmax_t capacity, bool fixed, size_t width)
{
    if (!fixed)
        capacity = 8;
    if (capacity == 0 || capacity > (uintmax_t)PTRDIFF_MAX / width)
        cuco_error("capacidade inválida");

    cuco_buffer *buffer = malloc(sizeof *buffer);
    if (buffer == NULL)
        cuco_error("falha ao alocar coleção");
    *buffer = (cuco_buffer){NULL, 0, (size_t)capacity, width, 0, fixed};
    buffer->data = malloc(buffer->capacity * width);
    if (buffer->data == NULL) {
        free(buffer);
        cuco_error("falha ao alocar elementos");
    }
    return buffer;
}

static inline unsigned char *cuco_at(cuco_buffer *buffer, size_t index)
{
    size_t slot = (buffer->head + index) % buffer->capacity;
    return buffer->data + slot * buffer->width;
}

static inline unsigned char *cuco_element(cuco_buffer *buffer, uintmax_t index)
{
    if (index >= cuco_check(buffer)->length)
        cuco_error("índice inválido ou coleção vazia");
    return cuco_at(buffer, (size_t)index);
}

static inline bool cuco_reserve_one(cuco_buffer *buffer)
{
    if (cuco_check(buffer)->length < buffer->capacity)
        return true;
    if (buffer->fixed || buffer->capacity > (size_t)PTRDIFF_MAX / buffer->width / 2)
        return false;

    size_t capacity = buffer->capacity * 2;
    unsigned char *data = malloc(capacity * buffer->width);
    if (data == NULL)
        return false;

    size_t tail = buffer->capacity - buffer->head;
    memcpy(data, cuco_at(buffer, 0), tail * buffer->width);
    if (buffer->head != 0)
        memcpy(data + tail * buffer->width, buffer->data, buffer->head * buffer->width);
    free(buffer->data);
    buffer->data = data;
    buffer->capacity = capacity;
    buffer->head = 0;
    return true;
}

static inline bool cuco_append(cuco_buffer *buffer, const void *value)
{
    if (!cuco_reserve_one(buffer))
        return false;
    memcpy(cuco_at(buffer, buffer->length), value, buffer->width);
    buffer->length++;
    return true;
}

static inline bool cuco_insert(cuco_buffer *buffer, uintmax_t index, const void *value)
{
    if (index > cuco_check(buffer)->length)
        cuco_error("índice inválido");
    if (!cuco_reserve_one(buffer))
        return false;
    unsigned char *slot = cuco_at(buffer, (size_t)index);
    memmove(slot + buffer->width, slot, (buffer->length - (size_t)index) * buffer->width);
    memcpy(slot, value, buffer->width);
    buffer->length++;
    return true;
}

static inline void cuco_remove(cuco_buffer *buffer, uintmax_t index, void *result)
{
    unsigned char *slot = cuco_element(buffer, index);
    memcpy(result, slot, buffer->width);
    buffer->length--;
    if (index < buffer->length)
        memmove(slot, slot + buffer->width, (buffer->length - (size_t)index) * buffer->width);
}

static inline void cuco_destroy(cuco_buffer *buffer)
{
    if (buffer != NULL) {
        free(buffer->data);
        free(buffer);
    }
}
