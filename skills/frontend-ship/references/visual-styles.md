# Visual style recipes: glass panels and 3D tilt

Optional reference for the `frontend-ship` skill. Use these recipes only when
the user explicitly asks for a glassmorphic or 3D tilt look **and** the project
has no design system or tokens to follow. Otherwise, match the project's
existing look.

Every recipe must still:

- Meet WCAG 2.2 AA contrast (4.5:1 for normal text, 3:1 for large text, focus
  indicators, and control boundaries) against the **worst-case backdrop** that
  can show through, not only the backdrop in the mockup.
- Fall back to an opaque surface when `backdrop-filter` is unsupported, and when
  the user prefers reduced transparency or more contrast.
- Turn motion off under `prefers-reduced-motion: reduce`. Effects are decoration;
  nothing depends on them.
- Map the literal values below to the project's tokens if it has any.

## Glass panel

Illustrative CSS. The base rule is opaque; translucency is a progressive
enhancement.

```css
.glass-panel {
  background: rgb(15 23 42);
  color: rgb(248 250 252);
  border: 1px solid rgb(255 255 255 / 0.18);
  border-radius: 0.75rem;
}

.glass-panel .muted {
  color: rgb(203 213 225);
}

.glass-panel :focus-visible {
  outline: 2px solid rgb(147 197 253);
  outline-offset: 2px;
}

@supports ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px))) {
  .glass-panel {
    background: rgb(15 23 42 / 0.75);
    -webkit-backdrop-filter: blur(16px);
    backdrop-filter: blur(16px);
  }
}

/* Later in the source, so it overrides the enhancement above. A browser that
   does not support a media feature treats that query as false and keeps the
   glass. */
@media (prefers-reduced-transparency: reduce), (prefers-contrast: more) {
  .glass-panel {
    background: rgb(15 23 42);
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
}

@media (prefers-contrast: more) {
  .glass-panel {
    border-color: rgb(255 255 255 / 0.6);
  }
}

@media (forced-colors: active) {
  .glass-panel {
    border-color: CanvasText;
  }
}
```

Checked values for this recipe, at 0.75 opacity over a pure white backdrop
(the worst case for a dark panel): primary text 7.6:1, muted text 5.35:1, focus
ring 4.41:1. Over the opaque fallback they are higher. For a light variant,
`rgb(255 255 255 / 0.75)` with text `rgb(15 23 42)` and muted text
`rgb(51 65 85)` gives 9.73:1 and 5.65:1 over a black backdrop, and a focus ring
of `rgb(29 78 216)` gives 3.65:1.

If you change the opacity or colors, recompute. Browsers blend in sRGB by
default, so the backdrop-adjusted color is, per 0 to 255 channel:
composite = alpha × surface + (1 − alpha) × backdrop. Blur averages the
backdrop but does not make its lightest areas lighter, so test against the
lightest content that can scroll behind the panel. Automated checkers such as
axe usually mark text over translucent or blurred backgrounds as "needs review",
so this check is manual. A small helper (illustrative Python):

```python
def linear(c8):
    c = c8 / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (linear(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def over(surface, alpha, backdrop):
    """Composite a translucent surface over a backdrop, per 0-255 channel."""
    return tuple(alpha * s + (1 - alpha) * b for s, b in zip(surface, backdrop))


panel = over((15, 23, 42), 0.75, (255, 255, 255))  # worst case: white behind
print(round(contrast((248, 250, 252), panel), 2))  # 7.6
print(round(contrast((203, 213, 225), panel), 2))  # 5.35
```

Other rules for glass:

- Keep body text on the panel, never directly on a busy or animated backdrop.
- Limit blur to a few panels per view; large blurred areas are expensive to
  paint, especially while scrolling on low-end devices.
- Borders and shadows are decoration unless they are the only way to see a
  control's edge; then they need 3:1 contrast.

## 3D tilt card

A subtle pointer-driven tilt for cards with little text. Skip it for touch
input, reduced-motion users, and text-heavy content. Keyboard and screen reader
users get the same content without it.

```css
.tilt-card {
  transform: perspective(800px) rotateX(var(--tilt-x, 0deg)) rotateY(var(--tilt-y, 0deg));
  transition: transform 150ms ease-out;
}

@media (prefers-reduced-motion: reduce) {
  .tilt-card {
    transform: none;
    transition: none;
  }
}
```

```ts
// Illustrative. Returns a cleanup function; in React, call it from useEffect
// with a ref to the card element and return the cleanup.
export function attachTilt(card: HTMLElement, maxDegrees = 4): () => void {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let frame = 0;

  const reset = () => {
    cancelAnimationFrame(frame);
    card.style.removeProperty('--tilt-x');
    card.style.removeProperty('--tilt-y');
  };

  const onMove = (event: PointerEvent) => {
    if (event.pointerType === 'touch' || reducedMotion.matches) return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const rect = card.getBoundingClientRect();
      // Pointer position from -1 to 1 across the card.
      const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      const y = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      card.style.setProperty('--tilt-x', `${(-y * maxDegrees).toFixed(2)}deg`);
      card.style.setProperty('--tilt-y', `${(x * maxDegrees).toFixed(2)}deg`);
    });
  };

  card.addEventListener('pointermove', onMove);
  card.addEventListener('pointerleave', reset);
  return () => {
    card.removeEventListener('pointermove', onMove);
    card.removeEventListener('pointerleave', reset);
    reset();
  };
}
```

Other rules for tilt:

- Keep the angle small (a few degrees) and animate only `transform`.
- Never tilt on focus, scroll, or page load, and never use motion to convey
  information.
- If the card is a link or button, its target size, focus indicator, and
  accessible name follow the same rules as any other control.
