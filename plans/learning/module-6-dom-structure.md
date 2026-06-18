# Module 6 — DOM Structure & the Card Grid (Cheat Sheet)

> Semantic HTML skeleton + the Alpine directives that render the grid from state.
> Implemented in `app/static/index.html` (+ `app.js`). Anchored to Angular.

---

## 1. Semantic HTML vs `<div>` — meaning, not appearance

By default `<header>/<nav>/<main>/<section>/<article>` **render identically to a `<div>`.** The
value is **meaning** that the toolchain reads:

> `<div>` is the `object` of HTML (generic box). Semantic tags are the **strongly-typed**
> version — same pixels, but the meaning is machine-readable.

Who reads it: **screen readers** (build landmarks — "skip to main", navigate by region),
**other devs** (self-documenting), **CSS** (target `article` for the print stylesheet),
**browsers/crawlers** (implicit ARIA roles).

| Tag | Meaning | Test |
|---|---|---|
| `<header>` | intro/banner of its nearest section | "the intro area of something?" |
| `<main>` | THE unique page content; **exactly one**; excludes nav/header/footer | "the one point of the page?" |
| `<section>` | thematic grouping, usually with a heading — "a chapter" | "belong together under one theme?" |
| `<article>` | **self-contained** unit that stands alone | "could I syndicate it?" — a drink card: yes |

`<section>` vs `<article>`: article is *independently meaningful* (a card/post); section is a
thematic chunk *of* something larger (the "Cocktails" grouping).

---

## 2. Layout rules learned

- **`<header>`/`<nav>` are siblings of `<main>`, not inside it.** `<main>` holds *only* the
  unique content (the card grid). This is what makes "skip to main content" work.
- **Headings are an outline, not font sizes.** One `<h1>` per page (page title), `<h2>` per
  section, `<h3>` per card — nested by *importance*, not size (size is CSS's job).
- **Tabs are controls, not headings** → `<button>`, not `<h1>`. A heading *labels* content; a
  tab *does* something.
- **The tab bar IS the filter** — no separate "Filter by…" panel. `<section>`s group cards;
  they aren't filter controls.

a11y niceties used: `alt=""` on the logo (decorative — the `<h1>` already says the name; empty
alt = "skip me", *missing* alt = reads the filename); `aria-label` on `<nav>`; `aria-labelledby`
on `<section>` pointing at its `<h2>` id; `<meta name="viewport">` (mobile-first — without it
phones render desktop-width).

---

## 3. `x-for` = `*ngFor`, and the `<template>` reveal

Render one element per item with `x-for` — which **must** sit on a `<template>` wrapping the
repeated element:
```html
<template x-for="c in visibleCocktails" :key="c.id">
  <article>
    <h3 x-text="c.name"></h3>
    <p x-text="c.tags.join(' · ')"></p>
  </article>
</template>
```
- **Why `<template>`?** Its contents are inert; Alpine uses it as a **stamp**, cloning the inner
  element per item. **`*ngFor` does the same** — it desugars to `<ng-template ngFor>`. The
  asterisk *is* a hidden template; Alpine just makes you write it.
- **`c in visibleCocktails`** — `c` is the loop var (your `let c of …`).
- **`:key="c.id"`** = Angular's **`trackBy`** — stable identity so the framework reuses/reorders
  DOM nodes instead of rebuilding. Use the stable unique id.
- **`:` = `x-bind:`** shorthand (`:key`, `:class`, `:aria-expanded`, …).
- **Nested loops** work: `groups → products → children` is three nested `<template x-for>`s.

---

## 4. Wiring it up — the 3 pieces behind `x-data="app()"`

For `x-for="c in visibleCocktails"` to resolve, all three must be present:
1. **Alpine loaded** (a `<script>`) — without it, `x-*` attributes are inert.
2. **`app()` defined** in `app.js`, **loaded before Alpine** — Alpine evaluates `x-data="app()"`
   on boot; `app` must already exist. Pattern: sync `app.js` first, then `defer` Alpine.
3. **`x-data="app()"` on a wrapper** (`<body>`) — establishes the reactive scope.

```html
<head>
  <script src="/app.js"></script>                                   <!-- 1st: defines app() -->
  <script defer src="https://unpkg.com/alpinejs@3/dist/cdn.min.js"></script> <!-- 2nd: boots -->
</head>
<body x-data="app()"> … </body>
```

The whole reactive chain in 4 lines of HTML: tap a tab → `activeCategory` changes →
`visibleCocktails` getter recomputes → `x-for` re-stamps → grid updates. Modules 1, 3–6 together.

---

## 5. Static-mount path gotcha (debugging note)

`main.py`: `app.mount("/", StaticFiles(directory="static", html=True))` mounts the **directory**
`static/` onto the **URL root `/`**. So `static/app.js` is served at **`/app.js`**, not
`/static/app.js`. The mount *name* ("static") is just an internal label, not the URL prefix.

> A file's **disk path** and its **served URL** are independent. Reference the URL the server
> exposes, not the folder it lives in. (Symptom of getting it wrong: blank logo + no tabs/cards
> + zero backend calls, because `app.js` 404s → `app()` undefined → Alpine never inits.)
