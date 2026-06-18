# Module 5 — Derived State (Cheat Sheet)

> Computing what the screen shows from the atoms in state, instead of storing it.
> Implemented as getters in `app/static/app.js`. Anchored to Angular.

---

## 1. Derive, don't store

To get "the cocktails visible for the active tab," two options:

**A — store it.** A `filteredCocktails: []` field, reassigned every time `activeCategory` or the
data changes.
**B — derive it.** A getter that filters on read; nothing stored.

**Pick B. A's failure isn't extra work — it's silent lying.** `filteredCocktails` would
*duplicate* info already in `cocktails` + `activeCategory`. The moment any code path changes a
dependency and forgets to recompute, the stored array goes **stale** and the screen contradicts
the real state — no error, it just lies. That's the single-source-of-truth violation again.
Derived state makes disagreement *impossible* (one source).

---

## 2. The tool: a getter (not a function with args)

```js
get visibleCocktails() {
  const base = this.availableCocktails;
  switch (this.activeCategory) {
    case 'all':
    case 'cocktails':     return base;
    case 'non-alcoholic': return base.filter(c => c.tags.some(t => ['Non-Alcoholic','Mocktail','NA'].includes(t)));
    case 'thc':           return base.filter(c => c.tags.some(t => ['THC','Cannabis'].includes(t)));
    default:              return [];   // beverage-only tabs
  }
}
```
Accessed in the template like a **property**, no parens: `x-for="c in visibleCocktails"`.
It reads `this.activeCategory`/`this.cocktails` **directly** (no arguments) — and *that's what
makes it reactive* (see §3).

**Angular equivalents:** a component `get`, a `computed()` signal, or an RxJS
`combineLatest(...).pipe(map(...))`. Alpine just uses a plain getter + the dependency tracker.

---

## 3. Why it stays current (the Module 1 payoff)

1. The template reads `visibleCocktails` inside an **effect** (the `x-for`'s effect).
2. Running it runs the getter, which **reads** `activeCategory` + `cocktails`.
3. Those reads fire the **get trap** → Alpine records "this effect depends on those."
4. Later `activeCategory` changes → **set trap** → re-runs the effect → getter recomputes →
   grid re-renders.

You don't keep it in sync — **the reactivity engine does**, because reading state inside the
getter wires up the dependencies. *That's why it must read state, not take an argument* — the
reads are what register the dependency.

**Gotcha (scale-OK here):** an Alpine getter is **not cached/memoized** like Vue's `computed` —
it re-runs on every access. Irrelevant for dozens of items; would matter for tens of thousands.

---

## 4. Composition — pipelines of single-responsibility getters

Getters can read other getters, and reactivity threads through the chain **transitively** (the
get traps fire for the whole call chain, registering all deps against the same effect). So layer
each concern:

```js
get availableCocktails() {                 // Layer 1: MODE/availability
  return this.hostMode ? this.cocktails : this.cocktails.filter(c => c.available);
}
get visibleCocktails() {                   // Layer 2: CATEGORY, built on Layer 1
  const base = this.availableCocktails;    // ← getter reading a getter
  ...
}
```
Change `hostMode` → `availableCocktails` recomputes → `visibleCocktails` recomputes → re-render,
all automatic. (Same as chaining Angular `computed()`s or RxJS `pipe`s.)

Inline (`if (!host)` at the top of one getter) also works for 2 filters; composition is the
scalable/clean choice as filters multiply (search, tags, sort). Scale judgment.

**Principle:** store the *atoms* (`cocktails`, `activeCategory`, `hostMode`); everything the
screen shows is *derived* from them, layer by layer; nothing downstream is stored, so nothing
can fall out of sync.

---

## 5. The cocktails ↔ beverages asymmetry

`visibleGroups` (beverages) is **simpler** than `visibleCocktails`:

- **Category is intrinsic to a beverage** — it's the *group* it lives in. Filter at the **group
  level** (`this.beverages.filter(g => wanted.includes(g.name))`); you don't reach into products
  or variants. (The `groups → products → children` nesting is a *rendering* concern, not a filter
  concern. group = category/"shelf"; parent product = a brand like High Noon with `children` flavors.)
- **No availability layer.** `/api/beverages` already returns only in-stock items for everyone,
  so beverages have *one* filter (category); cocktails have *two* (availability + category).

Deep reason: **mode changes the *set* of cocktails (host sees unavailable too), but only the
*detail* of beverages** (same set, host just sees stock/notes). Availability is *derived* for
cocktails (computed from ingredient stock) vs a *server-side fact* for beverages (`amount > 0`).
