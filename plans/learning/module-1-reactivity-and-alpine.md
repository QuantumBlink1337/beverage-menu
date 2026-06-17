# Module 1 — Reactivity & Why Alpine (Cheat Sheet)

> Earned knowledge from the frontend architecture quiz. Anchored against Angular,
> since that's the framework I (Matt) use at work. Covers: how reactivity works,
> why Alpine fits this project, and the framework/SPA vocabulary.

---

## 1. Reactivity is *library code*, not the JS engine

When `user.name = 'Grace'` updates the screen with no DOM code from you, **the JS
engine is not doing that.** V8 has no concept of a component, template, or binding.
The update is done by **plain JavaScript that the framework ships** — code someone
wrote. There is no magic layer, only code running as part of your app.

The term for this is **change detection**.

---

## 2. Two strategies for change detection

| | How it detects change | Model |
|---|---|---|
| **Angular (default)** | Re-evaluates **every** binding in the component tree and compares to last value (dirty-checking). Pinged by **Zone.js**, which monkey-patches `setTimeout`, `fetch`, event handlers, Promises to signal "something async happened, re-check." | **Pull** — "I don't know what changed, so re-check everything." |
| **Alpine / Vue** | **Intercepts the write itself** via a `Proxy` and notifies exactly the DOM that depends on that value. | **Push** — "the write tells me precisely what to update." |

The big fork: **sweep-everything vs. intercept-the-write.**
This is *why* Angular has `ChangeDetectionStrategy.OnPush` and "zoneless" — they shrink
the brute-force sweep. Alpine never sweeps, so it never needs them.

---

## 3. The JS feature that makes interception possible

To run code automatically when `obj.prop = x` happens, JS gives you two tools.
(Same shape as a C# property setter raising `INotifyPropertyChanged`.)

**Getters/setters** (Vue 2 era) — per-property, defined ahead of time, can't catch new keys:

```js
const data = { _name: 'Ada' };
Object.defineProperty(data, 'name', {
  get() { return this._name; },
  set(value) { this._name = value; /* run my code here */ }
});
```

**`Proxy`** (Vue 3 / Alpine) — wrap the whole object once, "traps" intercept *everything*:

```js
const data = new Proxy({ name: 'Ada' }, {
  get(target, key)        { /* record dependency */  return target[key]; },
  set(target, key, value) { /* notify dependents */  target[key] = value; return true; }
});
```

**Alpine hands your `x-data` object to a Proxy exactly like this.** The `set` trap,
instead of `console.log`, re-runs the DOM updates that depend on the changed key.

---

## 4. Dependency tracking — the heart of it

Why intercept *reads* (`get`)? Because that's how Alpine learns **which DOM depends on which property**, so it never has to sweep.

For `<p x-text="user.name"></p>`:

1. **(Load)** Wrap `x-data` in a Proxy — get + set traps now active. *(Precondition for everything below.)*
2. **(Load)** Wrap each directive in an **effect** — e.g. `() => el.textContent = user.name`.
3. **(Load)** Run each effect **once**, in "recording mode" (`currentEffect = thisEffect`).
   During the run, reading `user.name` fires the **get trap**, which records:
   *"`user.name` is depended on by `thisEffect`."* → this is **dependency tracking** (Vue calls it `track`).
   The single run does double duty: sets initial DOM **and** records dependencies.
4. **(Write, later)** `user.name = 'Grace'` fires the **set trap**, which looks up
   *"who depends on `user.name`?"* → re-runs **only** those effects (Vue calls it `trigger`).

**Whole engine:** `get` trap records dependencies while effects run; `set` trap
re-runs exactly the dependent effects. No tick, no sweep, no render-thread involvement.

---

## 5. The dependency map: many-to-many, real-time

Built **during** the effect runs (not a separate step), and **re-derived on every run**
(so conditional reads stay correct). Keyed by property:

```js
// for: <span x-text="count"></span>
//      <span x-text="count + ' ' + label"></span>
dependencyMap = {
  count: Set{ effect_A, effect_B },   // both spans read count
  label: Set{ effect_B },             // only 2nd span reads label
}
```

- A property → many effects. An effect → many properties. **Many-to-many.**
- Write `count` → opens *only* the `count` bucket → re-runs A and B.
- Write `label` → opens *only* the `label` bucket → re-runs B only. A is untouched.
- The `label` bucket is never even *consulted* when `count` changes — **keyed lookup.**

---

## 6. The robustness trade-off (reactivity gotchas)

Fine-grained tracking is precise but can **miss** a dependency → UI silently goes stale
("I changed the data, why didn't it update?"). Classic causes:

- **Destructuring** reactive state into a plain local (`let { count } = state`) — reads
  the value once, disconnects from the proxy.
- Mutating something the proxy never wrapped (deeply nested non-reactive object).

Angular's brute-force sweep **cannot** miss an update — it re-reads everything anyway.
So: **sweeping is dumb but robust; fine-grained is precise but has edge cases.**
(Note: you still never wire dependencies *manually* in either — both auto-track. The
gap only shows up in those edge cases.)

---

## 7. Why Alpine for *this* project

Match the justification to the **scale** of the problem.

- The change-detection speed edge is **real but irrelevant here** — too little DOM for a
  sweep to matter. Don't justify Alpine on runtime speed for a menu.

The decisive reasons are about **shipping and fit**:

1. **No build step → operational simplicity (the big one).** Angular = npm, TS compiler,
   bundler, `node_modules`, CI build stage, Docker build layer. Alpine = one `<script>` tag.
   FastAPI just serves three flat files from `static/`.
2. **Tiny payload → fast first paint (the real mobile win).** Alpine ≈ 15KB gzipped vs.
   hundreds of KB for a shipped Angular app. Guest scans a QR on cellular and wants the
   menu *now*. The mobile advantage is **download/parse size**, not change detection.
3. **Right-sized complexity.** Interactivity is "switch a tab, expand a card." Angular's
   components/modules/DI/routing/RxJS are machinery for large apps — overhead with no payoff here.

---

## 8. What you give up (structural downsides — all scale with app size)

1. **No real component model** — no props/slots/encapsulation. Reuse = copy HTML.
2. **No template type safety** — directive expressions are strings; rename a property and
   nothing warns you the HTML is broken.
3. **Awkward cross-page state sharing** — `Alpine.store()` is primitive vs. Angular services/RxJS.
4. **Thin testing & tooling** — no real component test harness, limited devtools.

**Synthesis:** every downside is a function of *scale*, and this project has none of it
(one card template, a few state fields, one page, one dev). The weaknesses are invisible
at this size; the strengths are exactly what this size needs. *That's* "right tool for the job."
If it grew into a multi-page ordering platform with accounts/carts, the calculus flips
toward React/Angular — knowing **where that line is** is the real skill.

---

## 9. Vocabulary scaffold

**Framework spectrum:**

```
vanilla JS  →  Alpine  →  Vue / Svelte  →  Angular / React
  (nothing)    (micro)      (mid)            (full SPA frameworks)
```

Alpine is a **micro-framework** / "the jQuery for the modern web" — gives you reactivity +
declarative directives in HTML, and deliberately stops (no router, no components, no build,
no virtual DOM). Mental model: **mostly-static HTML, lightly enhanced** — *not* a JS app that
renders the page. If you want Alpine to *own* the whole rendering pipeline, you've outgrown it.

**SPA vs MPA:**

| | Pages | Navigation | First paint |
|---|---|---|---|
| **MPA** | many HTML docs | server reload | fast |
| **SPA** | one shell | JS client-side routing (History API) | slow (boot first) |
| **Static + sprinkles** | one real page | none needed | fast ← **this project** |

This project is *literally one page* but **not an SPA** in the framework sense: an SPA is
defined by JS replacing multi-page navigation with client-side routing. This site has **one
view** — switching tabs is *filtering in place*, not navigation. So it gets single-page
simplicity without any SPA complexity.

**TypeScript note:** TS is a *compile-time* layer that erases before runtime; reactivity is a
*runtime* thing — orthogonal. Vue has first-class TS. Alpine's inline HTML expressions are
*strings* → **no type checking** on them (a real downside vs. Angular templates). This project
has **no build step → plain JS, no TS.** Escape hatch without a build: **JSDoc `@typedef`
comments** give editor-level type checking on `.js` files.
