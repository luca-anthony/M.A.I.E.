import argparse
import sys

import pygame


def parse():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--display", type=int, default=0)
    parser.add_argument("--rotate", type=int, default=0)
    parser.add_argument("--flip", action="store_true")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--offset-x", type=int, default=0)
    parser.add_argument("--offset-y", type=int, default=0)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--raw", action="store_true")
    return parser.parse_args()


def main():
    args = parse()
    pygame.init()
    pygame.mouse.set_visible(False)
    pygame.display.set_caption("M.A.I.E. projection")
    if args.windowed:
        screen = pygame.display.set_mode((1280, 720))
    else:
        sizes = pygame.display.get_desktop_sizes()
        index = max(0, min(args.display, len(sizes) - 1))
        screen = pygame.display.set_mode(sizes[index], pygame.FULLSCREEN, display=index)
    image = pygame.image.load(args.image).convert()
    screen_w, screen_h = screen.get_size()
    if args.raw:
        image = pygame.transform.scale(image, (screen_w, screen_h))
        rect = image.get_rect(topleft=(0, 0))
    else:
        if args.flip:
            image = pygame.transform.flip(image, True, False)
        if args.rotate:
            image = pygame.transform.rotate(image, args.rotate)
        width, height = image.get_size()
        factor = min(screen_w / width, screen_h / height) * args.scale
        image = pygame.transform.smoothscale(image, (max(1, int(width * factor)), max(1, int(height * factor))))
        rect = image.get_rect(center=(screen_w // 2 + args.offset_x, screen_h // 2 + args.offset_y))
    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
        screen.fill((0, 0, 0))
        screen.blit(image, rect)
        pygame.display.flip()
        clock.tick(15)
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
