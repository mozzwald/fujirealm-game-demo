/* Force-included when building src/render.c for tools/render_tests.c.
 *
 * Points the two framebuffer page constants at the test's own buffers. Nothing
 * else needs redirecting: render.c no longer reads any hardware register to
 * find them (see the FB_PAGE_0 comment there for why that mattered). */
#ifndef RENDER_TEST_HOOKS_H
#define RENDER_TEST_HOOKS_H

extern unsigned char test_page_0[];
extern unsigned char test_page_1[];
#define FB_PAGE_0 test_page_0
#define FB_PAGE_1 test_page_1

#endif
